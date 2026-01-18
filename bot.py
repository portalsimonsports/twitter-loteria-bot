# bot.py — Portal SimonSports — Publicador Automático (X, Facebook, Telegram, Discord, Pinterest)
# Rev: 2026-01-18b — COFRE ONLY + FIX grid limits (add_cols) + roda TODAS as redes alvo
# - NÃO usa .env (não chama load_dotenv)
# - ÚNICA credencial fora do Cofre: GOOGLE_SERVICE_JSON via GitHub Actions (secret)
# - Planilhas (principal + Cofre) são abertas via Service Account
# - Redes sociais (tokens/keys/ids/webhooks/chat_ids) SOMENTE via Cofre
# - Sem filtro de data; publica quando a coluna da rede estiver VAZIA
# - Cria colunas "Publicado_<REDE>" se não existirem (e AUMENTA colunas da aba automaticamente)
# - Texto inclui TODOS os canais ativos do Cofre (ordem crescente) — usado apenas como bloco de links (não ativa rede)
# - TARGET_NETWORKS (env/vars) define a ordem/redes a processar (default: todas suportadas)
# - Se a rede NÃO tiver credenciais no Cofre, apenas registra no log e segue para a próxima (não falha execução)
# - X_SKIP_DUP_CHECK no Cofre (opcional) controla check de duplicidade (evita 401)

import os, re, io, glob, json, time, base64, pytz, tweepy, requests
import datetime as dt
from threading import Thread
from collections import defaultdict
from typing import Optional, Dict, List, Tuple

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Imagem oficial (layout aprovado)
from app.imaging import gerar_imagem_loteria

TZ = pytz.timezone("America/Sao_Paulo")

# ============================================================
# REGRAS "COFRE ONLY"
# ============================================================
# 1) NÃO carregar .env (NÃO usar load_dotenv).
# 2) ÚNICA coisa "externa" ao Cofre:
#    - GOOGLE_SERVICE_JSON (GitHub Actions Secret) para acessar Google Sheets.
# 3) IDs/tokens/keys/webhooks/chat_ids/board_id etc. SOMENTE no Cofre.
#
# Config não-secreta (pode vir como GitHub "Variables"):
# - COFRE_SHEET_ID  (ID da planilha Cofre)
# - COFRE_ABA_CRED  (default: Credenciais_Rede)
# - COFRE_ABA_CANAIS(default: Redes_Sociais_Canais)
# - SHEET_TAB       (default: ImportadosBlogger2)
# - TARGET_NETWORKS (default: X,FACEBOOK,TELEGRAM,DISCORD,PINTEREST)
#
# OBS: a planilha PRINCIPAL (GOOGLE_SHEET_ID) vem do Cofre.
# ============================================================

# ---------------- Config (não-secreta) ----------------
COFRE_SHEET_ID   = (os.getenv("COFRE_SHEET_ID", "") or "").strip()
COFRE_ABA_CRED   = (os.getenv("COFRE_ABA_CRED", "Credenciais_Rede") or "Credenciais_Rede").strip()
COFRE_ABA_CANAIS = (os.getenv("COFRE_ABA_CANAIS", "Redes_Sociais_Canais") or "Redes_Sociais_Canais").strip()

SHEET_TAB = (os.getenv("SHEET_TAB", "ImportadosBlogger2") or "ImportadosBlogger2").strip()

# Redes alvo (ordem). Mesmo sem credenciais, o bot "roda" e só pula a publicação.
TARGET_NETWORKS = (os.getenv("TARGET_NETWORKS", "X,FACEBOOK,TELEGRAM,DISCORD,PINTEREST") or "").strip()

DRY_RUN = (os.getenv("DRY_RUN", "false").strip().lower() == "true")

ENABLE_KEEPALIVE = (os.getenv("ENABLE_KEEPALIVE", "false").strip().lower() == "true")
KEEPALIVE_PORT   = int(os.getenv("KEEPALIVE_PORT", "8080"))

USE_KIT_IMAGE_FIRST = (os.getenv("USE_KIT_IMAGE_FIRST", "false").strip().lower() == "true")
KIT_OUTPUT_DIR      = (os.getenv("KIT_OUTPUT_DIR", "output") or "output").strip()
PUBLIC_BASE_URL     = (os.getenv("PUBLIC_BASE_URL", "") or "").strip()

MAX_PUBLICACOES_RODADA = int(os.getenv("MAX_PUBLICACOES_RODADA", "30"))
PAUSA_ENTRE_POSTS      = float(os.getenv("PAUSA_ENTRE_POSTS", "2.5"))

# ---------------- colunas planilha principal ----------------
COL_LOTERIA, COL_CONCURSO, COL_DATA, COL_NUMEROS, COL_URL = 1, 2, 3, 4, 5
COL_URL_IMAGEM, COL_IMAGEM = 6, 7

# P e Q continuam existindo como fallback "antigo" de canais (se não houver canais no Cofre)
COL_TG_DICAS  = 16  # P
COL_TG_PORTAL = 17  # Q

# Status por rede (índices fixos antigos, se existirem).
# Se a coluna não existir, o bot cria "Publicado_<REDE>".
COL_STATUS_REDES = {
    "X": 8,
    "FACEBOOK": 15,
    "TELEGRAM": 10,
    "DISCORD": 13,
    "PINTEREST": 14
}

# ---------------- utilidades ----------------
def _detect_origem():
    if os.getenv("BOT_ORIGEM"): return os.getenv("BOT_ORIGEM").strip()
    if os.getenv("GITHUB_ACTIONS"): return "GitHub"
    if os.getenv("REPL_ID") or os.getenv("REPLIT_DB_URL"): return "Replit"
    if os.getenv("RENDER"): return "Render"
    return "Local"

BOT_ORIGEM = _detect_origem()

def _log(*a): print(f"[{dt.datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}]", *a, flush=True)
def _now():   return dt.datetime.now(TZ)
def _ts_br(): return _now().strftime("%d/%m/%Y %H:%M")

def _safe_len(row, idx): return len(row) >= idx

def _strip_invisible(s: str) -> str:
    if s is None: return ""
    s = str(s)
    for ch in ["\u200B","\u200C","\u200D","\uFEFF","\u2060"]:
        s = s.replace(ch,"")
    return s.strip()

def _is_empty_status(v): return _strip_invisible(v) == ""

def _row_has_min_payload(row) -> bool:
    loteria = _strip_invisible(row[COL_LOTERIA-1]) if _safe_len(row, COL_LOTERIA) else ""
    numeros = _strip_invisible(row[COL_NUMEROS-1]) if _safe_len(row, COL_NUMEROS) else ""
    url     = _strip_invisible(row[COL_URL-1])     if _safe_len(row, COL_URL)     else ""
    if not (loteria and numeros and url): return False
    if not re.match(r"^https?://[^ ]+\.[^ ]+", url): return False
    if not re.search(r"\d", numeros): return False
    return True

# ============================================================
# COFRE (cache)
# ============================================================
_cofre_cache: Dict[str, Dict] = {}  # "creds" map + "canais_list" lista

_COOL_REDE = {
    "GOOGLE":    ["GOOGLE", "PLANILHAS GOOGLE", "PLANILHAS_GOOGLE", "PLANILHAS"],
    "X":         ["X", "TWITTER"],
    "FACEBOOK":  ["FACEBOOK", "META_FACEBOOK", "META"],
    "TELEGRAM":  ["TELEGRAM", "TG"],
    "DISCORD":   ["DISCORD"],
    "PINTEREST": ["PINTEREST"]
}

def _match_rede(key_rede: str, target: str) -> bool:
    kr = (key_rede or "").strip().upper()
    tg = (target or "").strip().upper()
    return kr == tg or kr.replace("_"," ") == tg.replace("_"," ") or kr in _COOL_REDE.get(tg, [])

def _cofre_get(key: Tuple[str,str], default: Optional[str]=None) -> Optional[str]:
    """Busca (REDE, CHAVE) aceitando sinônimos de rede. Retorna string ou default."""
    rede, chave = (key[0] or "").upper(), (key[1] or "").upper()
    m = _cofre_cache.get("creds", {})
    v = m.get((rede, chave))
    if v: return v
    for (r,k), val in m.items():
        if k == chave and _match_rede(r, rede):
            return val
    return default

def _cofre_get_many(prefix: Tuple[str,str]) -> List[Tuple[int,str]]:
    rede, pref = (prefix[0] or "").upper(), (prefix[1] or "").upper()
    m = _cofre_cache.get("creds", {})
    out=[]
    for (r,k),v in m.items():
        if _match_rede(r, rede) and k.startswith(pref):
            mm = re.search(rf"^{re.escape(pref)}(\d+)$", k)
            if mm:
                out.append((int(mm.group(1)), v))
    out.sort(key=lambda x: x[0])
    return out

# ============================================================
# GOOGLE AUTH (somente via GOOGLE_SERVICE_JSON no Actions)
# ============================================================
def _gs_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    sa_json_env = (os.getenv("GOOGLE_SERVICE_JSON", "") or "").strip()
    if not sa_json_env:
        raise RuntimeError(
            "Credencial Google ausente: defina GOOGLE_SERVICE_JSON (GitHub Actions Secret). "
            "Não usamos service_account.json nem .env."
        )
    try:
        info = json.loads(sa_json_env)
    except Exception as e:
        raise RuntimeError(f"GOOGLE_SERVICE_JSON inválido (não é JSON). Erro: {e}")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scopes)
    return gspread.authorize(creds)

def _open_cofre_ws(tab: str):
    if not COFRE_SHEET_ID:
        raise RuntimeError("COFRE_SHEET_ID não definido (GitHub Variables).")
    sh = _gs_client().open_by_key(COFRE_SHEET_ID)
    return sh.worksheet(tab)

def _cofre_load():
    # Credenciais (Credenciais_Rede)
    creds_ws = _open_cofre_ws(COFRE_ABA_CRED)
    creds_map = {}
    allv = creds_ws.get_all_values()
    for r in allv[1:]:
        rede  = _strip_invisible(r[0]) if len(r)>0 else ""
        chave = _strip_invisible(r[2]) if len(r)>2 else ""
        valor = _strip_invisible(r[3]) if len(r)>3 else ""
        if rede and chave and valor:
            creds_map[(rede.upper(), chave.upper())] = valor
    _cofre_cache["creds"] = creds_map

    # Canais (Redes_Sociais_Canais) — SOMENTE para bloco de links no texto (não define redes ativas)
    canais_ws = _open_cofre_ws(COFRE_ABA_CANAIS)
    canais_list = []
    vals = canais_ws.get_all_values()
    for r in vals[1:]:
        ativo = _strip_invisible(r[0]).lower() if len(r)>0 else ""
        ordem = _strip_invisible(r[1]) if len(r)>1 else ""
        rede  = _strip_invisible(r[2]) if len(r)>2 else ""
        tipo  = _strip_invisible(r[3]).upper() if len(r)>3 else ""
        nome  = _strip_invisible(r[4]) if len(r)>4 else ""
        url   = _strip_invisible(r[5]) if len(r)>5 else ""
        if ativo == "sim" and url:
            try:
                o = int(ordem) if ordem else 9999
            except Exception:
                o = 9999
            canais_list.append({"ordem": o, "rede": rede, "tipo": tipo, "nome": (nome or tipo or rede), "url": url})
    canais_list.sort(key=lambda x: x["ordem"])
    _cofre_cache["canais_list"] = canais_list

def _open_ws_principal():
    # A planilha principal vem do Cofre (GOOGLE_SHEET_ID)
    sid = _cofre_get(("GOOGLE", "GOOGLE_SHEET_ID"), "") or ""
    if not sid:
        raise RuntimeError("No Cofre, informe (Rede=GOOGLE, Chave=GOOGLE_SHEET_ID) com o ID da planilha principal.")
    sh = _gs_client().open_by_key(sid)
    return sh.worksheet(SHEET_TAB)

def _ensure_cols(ws, min_cols: int):
    """Garante que a aba tenha pelo menos min_cols colunas (FIX do erro 'exceeds grid limits')."""
    try:
        cur = ws.col_count
    except Exception:
        # fallback: tenta inferir pelo header
        cur = len(ws.row_values(1))
    if cur >= min_cols:
        return
    add = min_cols - cur
    _log(f"[Planilha] Aumentando colunas: {cur} -> {min_cols} (+{add})")
    ws.add_cols(add)

def _ensure_status_column(ws, rede: str, env_col: Optional[int]) -> int:
    # Mantém compat com índices fixos, mas cria se não existir
    if env_col and isinstance(env_col, int) and env_col > 0:
        return env_col

    header = ws.row_values(1)
    target = f"Publicado_{rede}"

    for i, h in enumerate(header, start=1):
        if h and h.strip().lower() == target.lower():
            return i

    col = len(header) + 1

    # FIX: se col ultrapassar o grid, adiciona colunas antes de escrever (evita S1 > max_columns)
    _ensure_cols(ws, col)

    ws.update_cell(1, col, target)
    _log(f"[Planilha] Criada coluna: {target} (col {col})")
    return col

def marcar_publicado(ws, rownum, rede, value=None):
    col = COL_STATUS_REDES.get(rede, None)
    if not col:
        col = _ensure_status_column(ws, rede, None)
        COL_STATUS_REDES[rede] = col

    # FIX extra: se índice fixo apontar para coluna que não existe no grid, expande
    _ensure_cols(ws, col)

    value = value or f"Publicado {rede} via {BOT_ORIGEM} em {_ts_br()}"
    ws.update_cell(rownum, col, value)

# ============================================================
# TEXT MODE + FLAGS (somente via Cofre)
# ============================================================
VALID_TEXT_MODES = {"IMAGE_ONLY", "TEXT_AND_IMAGE", "TEXT_ONLY"}

def _cofre_bool(rede: str, chave: str, default: bool=False) -> bool:
    v = (_cofre_get((rede, chave), "") or "").strip().lower()
    if v in ("1","true","sim","yes","y","on"): return True
    if v in ("0","false","nao","não","no","n","off"): return False
    return default

def _cofre_text_mode(rede: str, default: str="TEXT_AND_IMAGE") -> str:
    v = (_cofre_get((rede, "TEXT_MODE"), "") or "").strip().upper()
    if v in VALID_TEXT_MODES: return v
    return default

# ============================================================
# IMAGEM
# ============================================================
_LOTERIA_SLUGS = {
    "mega-sena":"mega-sena","quina":"quina","lotofacil":"lotofacil","lotofácil":"lotofacil",
    "lotomania":"lotomania","timemania":"timemania","dupla sena":"dupla-sena","dupla-sena":"dupla-sena",
    "federal":"federal","loteria federal":"federal","dia de sorte":"dia-de-sorte","dia-de-sorte":"dia-de-sorte",
    "super sete":"super-sete","super-sete":"super-sete","loteca":"loteca",
}

def _slugify(s:str)->str:
    s=(s or "").lower()
    s=re.sub(r"[áàâãä]","a",s); s=re.sub(r"[éèêë]","e",s); s=re.sub(r"[íìîï]","i",s)
    s=re.sub(r"[óòôõö]","o",s); s=re.sub(r"[úùûü]","u",s); s=re.sub(r"[ç]","c",s)
    s=re.sub(r"[^a-z0-9- ]+","",s); s=re.sub(r"\s+","-",s).strip("-")
    return s

def _guess_slug(name:str)->str:
    p=(name or "").lower()
    for k,v in _LOTERIA_SLUGS.items():
        if k in p: return v
    return _slugify(name or "loteria")

def _try_load_kit_image(row):
    if not USE_KIT_IMAGE_FIRST: return None
    try:
        loteria=row[COL_LOTERIA-1] if _safe_len(row,COL_LOTERIA) else ""
        concurso=row[COL_CONCURSO-1] if _safe_len(row,COL_CONCURSO) else ""
        data_br=row[COL_DATA-1] if _safe_len(row,COL_DATA) else ""
        slug=_guess_slug(loteria)

        pats=[]
        if concurso:
            pats += [
                os.path.join(KIT_OUTPUT_DIR, f"*{slug}*{_slugify(concurso)}*.jp*g"),
                os.path.join(KIT_OUTPUT_DIR, f"{slug}-{_slugify(concurso)}*.jp*g")
            ]
        if data_br:
            pats.append(os.path.join(KIT_OUTPUT_DIR, f"*{slug}*{_slugify(data_br)}*.jp*g"))
        pats.append(os.path.join(KIT_OUTPUT_DIR, f"{slug}*.jp*g"))

        for pat in pats:
            files = sorted(glob.glob(pat))
            if files:
                with open(files[0], "rb") as f:
                    buf = io.BytesIO(f.read())
                    buf.seek(0)
                    return buf
        return None
    except Exception as e:
        _log(f"[KIT] erro: {e}")
        return None

def _build_image_from_row(row):
    buf=_try_load_kit_image(row)
    if buf: return buf
    loteria  = row[COL_LOTERIA-1]  if _safe_len(row,COL_LOTERIA)  else "Loteria"
    concurso = row[COL_CONCURSO-1] if _safe_len(row,COL_CONCURSO) else "0000"
    data_br  = row[COL_DATA-1]     if _safe_len(row,COL_DATA)     else _now().strftime("%d/%m/%Y")
    numeros  = row[COL_NUMEROS-1]  if _safe_len(row,COL_NUMEROS)  else ""
    url_res  = row[COL_URL-1]      if _safe_len(row,COL_URL)      else ""
    return gerar_imagem_loteria(str(loteria), str(concurso), str(data_br), str(numeros), str(url_res))

# ============================================================
# TEXTO (canais do Cofre)
# ============================================================
def _build_canais_block_for(rede_alvo: str, max_chars: int = None) -> str:
    canais = _cofre_cache.get("canais_list", [])
    if not canais:
        return ""
    lines = ["Inscreva-se nos nossos canais"]
    for ch in canais:
        nome = ch.get("nome") or ch.get("tipo") or ch.get("rede") or "Canal"
        url  = ch.get("url") or ""
        if not url: continue
        lines += [nome, url, ""]
    txt = "\n".join([s for s in lines if s is not None]).strip()

    if max_chars and len(txt) > max_chars:
        header = "Inscreva-se nos nossos canais\n"
        rest = txt[len(header):].split("\n")
        pairs = []
        i=0
        while i < len(rest):
            name = rest[i] if i < len(rest) else ""
            url  = rest[i+1] if i+1 < len(rest) else ""
            pairs.append((name,url))
            i += 3 if i+2 < len(rest) and rest[i+2]=="" else 2
        out = header
        for (name,url) in pairs:
            candidate = f"{out}{name}\n{url}\n\n"
            if len(candidate) <= max_chars:
                out = candidate
            else:
                break
        return out.strip()

    return txt

def montar_texto_publicacao(row, rede_alvo: str) -> str:
    url = (_strip_invisible(row[COL_URL-1]) if _safe_len(row,COL_URL) else "")
    head = f"Resultado completo aqui >>>>\n{url}\n\n".strip()

    canais_block = ""
    canais_list = _cofre_cache.get("canais_list", [])
    if canais_list:
        if rede_alvo == "X":
            canais_block = _build_canais_block_for(rede_alvo, max_chars=275 - len(head) - 1)
        else:
            canais_block = _build_canais_block_for(rede_alvo)
    else:
        # fallback antigo (P/Q) se Cofre não tiver canais
        dicas  = (_strip_invisible(row[COL_TG_DICAS-1])  if _safe_len(row,COL_TG_DICAS)  else "")
        portal = (_strip_invisible(row[COL_TG_PORTAL-1]) if _safe_len(row,COL_TG_PORTAL) else "")
        if dicas or portal:
            parts = ["Inscreva-se nos nossos canais"]
            if dicas:  parts += ["Dicas Esportivas", dicas, ""]
            if portal: parts += ["Portal SimonSports", portal, ""]
            canais_block = "\n".join([p for p in parts if p]).strip()

    text = head + ("\n" + canais_block if canais_block else "")
    if rede_alvo == "X" and len(text) > 275:
        text = text[:275]
    return text.strip()

# ============================================================
# COLETA
# ============================================================
def coleta_candidatos_para(ws, rede: str):
    linhas = ws.get_all_values()
    if len(linhas) <= 1:
        _log(f"[{rede}] Planilha sem dados.")
        return []

    if rede not in COL_STATUS_REDES or not COL_STATUS_REDES[rede]:
        COL_STATUS_REDES[rede] = _ensure_status_column(ws, rede, None)

    col_status = COL_STATUS_REDES.get(rede)

    data = linhas[1:]
    cand=[]
    for rindex, row in enumerate(data, start=2):
        status_val = row[col_status-1] if len(row) >= col_status else ""
        if not _is_empty_status(status_val):
            continue
        if not _row_has_min_payload(row):
            continue
        cand.append((rindex, row))

    _log(f"[{rede}] Candidatas: {len(cand)}/{len(data)}")
    return cand

# ============================================================
# X (somente Cofre)
# ============================================================
def _x_creds(idx:int) -> Dict[str,str]:
    return {
        "api_key":       _cofre_get(("X", f"TWITTER_API_KEY_{idx}"), ""),
        "api_secret":    _cofre_get(("X", f"TWITTER_API_SECRET_{idx}"), ""),
        "access_token":  _cofre_get(("X", f"TWITTER_ACCESS_TOKEN_{idx}"), ""),
        "access_secret": _cofre_get(("X", f"TWITTER_ACCESS_SECRET_{idx}"), ""),
    }

class XAccount:
    def __init__(self, label, api_key, api_secret, access_token, access_secret):
        self.label = label
        self.client_v2 = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret
        )
        auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
        self.api_v1 = tweepy.API(auth)
        try:
            me = self.client_v2.get_me()
            self.user_id = me.data.id if me and me.data else None
            self.handle = "@" + (me.data.username if me and me.data else label)
        except Exception:
            self.user_id = None
            self.handle = f"@{label}"

def _build_x_accounts():
    accs=[]
    def ok(d): return all(d.get(k) for k in ("api_key","api_secret","access_token","access_secret"))

    tw1 = _x_creds(1)
    if ok(tw1): accs.append(XAccount("ACC1", **tw1))
    else: _log("Conta X ACC1 incompleta (Cofre).")

    tw2 = _x_creds(2)
    if ok(tw2): accs.append(XAccount("ACC2", **tw2))

    return accs  # pode voltar vazio; nesse caso apenas não publica X

_recent_tweets_cache = defaultdict(set)
_postados_nesta_execucao = defaultdict(set)

def _x_skip_dup_check() -> bool:
    return _cofre_bool("X", "X_SKIP_DUP_CHECK", default=True)

def _x_post_in_all_accounts() -> bool:
    return _cofre_bool("X", "X_POST_IN_ALL_ACCOUNTS", default=True)

def _x_post_with_image() -> bool:
    return _cofre_bool("X", "POST_X_WITH_IMAGE", default=True)

def x_load_recent_texts(acc, max_results=50):
    if _x_skip_dup_check():
        return set()
    try:
        resp = acc.client_v2.get_users_tweets(
            id=acc.user_id,
            max_results=min(max_results, 100),
            tweet_fields=["text"]
        )
        out=set()
        if resp and resp.data:
            for tw in resp.data:
                t=(tw.text or "").strip()
                if t: out.add(t)
        _recent_tweets_cache[acc.label] = set(list(out)[-50:])
        return _recent_tweets_cache[acc.label]
    except Exception as e:
        _log(f"[{acc.handle}] warning: tweets recentes: {e}")
        return set()

def x_is_dup(acc, text):
    if _x_skip_dup_check():
        return False
    t=(text or "").strip()
    return bool(t and (t in _recent_tweets_cache[acc.label] or t in _postados_nesta_execucao[acc.label]))

def x_upload_media_if_any(acc, row):
    if not _x_post_with_image() or DRY_RUN:
        return None
    try:
        buf=_build_image_from_row(row)
        media=acc.api_v1.media_upload(filename="resultado.png", file=buf)
        return [media.media_id_string]
    except Exception as e:
        _log(f"[{acc.handle}] Erro imagem: {e}")
        return None

def publicar_em_x(ws, candidatos):
    contas=_build_x_accounts()
    if not contas:
        _log("[X] Sem credenciais válidas no Cofre. Pulando publicação em X.")
        return 0

    for acc in contas:
        _recent_tweets_cache[acc.label] = x_load_recent_texts(acc, 50)
        _log(f"[X] Conta: {acc.handle}")

    publicados=0
    limite=min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode_cfg = _cofre_text_mode("X", default="TEXT_AND_IMAGE")

    for rownum, row in candidatos[:limite]:
        texto_full = montar_texto_publicacao(row, "X")
        mode = mode_cfg
        texto_para = "" if mode=="IMAGE_ONLY" else texto_full

        ok_all=True
        if _x_post_in_all_accounts():
            for acc in contas:
                media_ids = x_upload_media_if_any(acc, row)
                try:
                    if DRY_RUN:
                        _log(f"[X][{acc.handle}] DRY_RUN")
                    else:
                        if texto_para and x_is_dup(acc, texto_para):
                            _log(f"[X][{acc.handle}] SKIP duplicado.")
                        else:
                            resp = acc.client_v2.create_tweet(
                                text=(texto_para or None) if mode!="IMAGE_ONLY" else None,
                                media_ids=media_ids if _x_post_with_image() else None
                            )
                            if texto_para:
                                _postados_nesta_execucao[acc.label].add(texto_para)
                                _recent_tweets_cache[acc.label].add(texto_para)
                            _log(f"[X][{acc.handle}] OK → {resp.data['id']}")
                except Exception as e:
                    _log(f"[X][{acc.handle}] erro: {e}")
                    ok_all=False
                time.sleep(0.7)
        else:
            acc=contas[0]
            media_ids = x_upload_media_if_any(acc, row)
            try:
                if DRY_RUN:
                    _log(f"[X][{acc.handle}] DRY_RUN")
                else:
                    if texto_para and x_is_dup(acc, texto_para):
                        _log(f"[X][{acc.handle}] SKIP duplicado.")
                    else:
                        resp = acc.client_v2.create_tweet(
                            text=(texto_para or None) if mode!="IMAGE_ONLY" else None,
                            media_ids=media_ids if _x_post_with_image() else None
                        )
                        if texto_para:
                            _postados_nesta_execucao[acc.label].add(texto_para)
                            _recent_tweets_cache[acc.label].add(texto_para)
                        _log(f"[X][{acc.handle}] OK → {resp.data['id']}")
            except Exception as e:
                _log(f"[X][{acc.handle}] erro: {e}")
                ok_all=False

        if ok_all and not DRY_RUN:
            marcar_publicado(ws, rownum, "X")
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[X] Publicados: {publicados}")
    return publicados

# ============================================================
# FACEBOOK (somente Cofre)
# ============================================================
def _fb_pairs_from_cofre():
    # Aceita PAGE_ID_1, PAGE_ID_2... e PAGE_ACCESS_TOKEN_1... (ou PAGE_TOKEN_1...)
    ids   = _cofre_get_many(("FACEBOOK","PAGE_ID_"))
    toks1 = _cofre_get_many(("FACEBOOK","PAGE_ACCESS_TOKEN_"))
    toks2 = _cofre_get_many(("FACEBOOK","PAGE_TOKEN_"))
    mp = {n:v for n,v in ids}
    mt = {n:v for n,v in toks1} if toks1 else {n:v for n,v in toks2}
    out=[]
    for n in sorted(set(mp)&set(mt)):
        if mp[n] and mt[n]:
            out.append((mp[n], mt[n]))
    return out

def _fb_post_text(pid, token, message, link=None):
    url=f"https://graph.facebook.com/v19.0/{pid}/feed"
    data={"message":message,"access_token":token}
    if link: data["link"]=link
    r=requests.post(url, data=data, timeout=25)
    r.raise_for_status()
    return r.json().get("id")

def _fb_post_photo(pid, token, caption, image_bytes):
    url=f"https://graph.facebook.com/v19.0/{pid}/photos"
    files={"source":("resultado.png", image_bytes, "image/png")}
    data={"caption":caption,"published":"true","access_token":token}
    r=requests.post(url, data=data, files=files, timeout=40)
    r.raise_for_status()
    return r.json().get("id")

def publicar_em_facebook(ws, candidatos):
    pairs = _fb_pairs_from_cofre()
    if not pairs:
        _log("[FACEBOOK] Sem credenciais no Cofre (PAGE_ID_n + PAGE_ACCESS_TOKEN_n). Pulando Facebook.")
        return 0

    mode = _cofre_text_mode("FACEBOOK", default="TEXT_AND_IMAGE")
    post_with_image = _cofre_bool("FACEBOOK", "POST_FB_WITH_IMAGE", default=True)

    publicados=0
    limite=min(MAX_PUBLICACOES_RODADA, len(candidatos))

    for rownum, row in candidatos[:limite]:
        base = montar_texto_publicacao(row, "FACEBOOK")
        msg = "" if mode=="IMAGE_ONLY" else base
        url_post = _strip_invisible(row[COL_URL-1]) if _safe_len(row,COL_URL) else ""

        ok_any=False
        for pid, ptok in pairs:
            try:
                if DRY_RUN:
                    _log(f"[Facebook][{pid}] DRY_RUN")
                    ok=True
                else:
                    if post_with_image:
                        buf=_build_image_from_row(row)
                        fb_id=_fb_post_photo(pid, ptok, msg, buf.getvalue())
                    else:
                        fb_id=_fb_post_text(pid, ptok, msg, link=url_post or None)
                    _log(f"[Facebook][{pid}] OK → {fb_id}")
                    ok=True
            except Exception as e:
                _log(f"[Facebook][{pid}] erro: {e}")
                ok=False
            ok_any = ok_any or ok
            time.sleep(0.7)

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "FACEBOOK")
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Facebook] Publicados: {publicados}")
    return publicados

# ============================================================
# TELEGRAM (somente Cofre)
# ============================================================
def _tg_token_from_cofre():
    return (_cofre_get(("TELEGRAM","BOT_TOKEN"), "") or "").strip()

def _tg_chat_ids_from_cofre():
    # CHAT_ID_1, CHAT_ID_2...
    return [v for _,v in _cofre_get_many(("TELEGRAM","CHAT_ID_")) if v]

def _tg_send_photo(token, chat_id, caption, image_bytes):
    url=f"https://api.telegram.org/bot{token}/sendPhoto"
    files={"photo":("resultado.png", image_bytes, "image/png")}
    data={"chat_id":chat_id,"caption":caption}
    r=requests.post(url, data=data, files=files, timeout=40)
    r.raise_for_status()
    return r.json().get("result",{}).get("message_id")

def _tg_send_text(token, chat_id, text):
    url=f"https://api.telegram.org/bot{token}/sendMessage"
    data={"chat_id":chat_id,"text":text,"disable_web_page_preview":False}
    r=requests.post(url, data=data, timeout=25)
    r.raise_for_status()
    return r.json().get("result",{}).get("message_id")

def publicar_em_telegram(ws, candidatos):
    token = _tg_token_from_cofre()
    chats = _tg_chat_ids_from_cofre()
    if not token or not chats:
        _log("[TELEGRAM] Sem credenciais no Cofre (BOT_TOKEN + CHAT_ID_n). Pulando Telegram.")
        return 0

    mode = _cofre_text_mode("TELEGRAM", default="TEXT_AND_IMAGE")
    post_with_image = _cofre_bool("TELEGRAM", "POST_TG_WITH_IMAGE", default=True)

    publicados=0
    limite=min(MAX_PUBLICACOES_RODADA, len(candidatos))

    for rownum, row in candidatos[:limite]:
        base = montar_texto_publicacao(row, "TELEGRAM")
        msg = "" if mode=="IMAGE_ONLY" else base
        url_post=_strip_invisible(row[COL_URL-1]) if _safe_len(row,COL_URL) else ""

        ok_any=False
        for chat_id in chats:
            try:
                if DRY_RUN:
                    _log(f"[Telegram][{chat_id}] DRY_RUN")
                    ok=True
                else:
                    if post_with_image:
                        buf=_build_image_from_row(row)
                        msg_id=_tg_send_photo(token, chat_id, msg, buf.getvalue())
                    else:
                        final_msg = msg
                        if url_post and final_msg:
                            final_msg = f"{final_msg}\n{url_post}"
                        elif url_post and not final_msg:
                            final_msg = url_post
                        msg_id=_tg_send_text(token, chat_id, final_msg or "")
                    _log(f"[Telegram][{chat_id}] OK → {msg_id}")
                    ok=True
            except Exception as e:
                _log(f"[Telegram][{chat_id}] erro: {e}")
                ok=False

            ok_any = ok_any or ok
            time.sleep(0.5)

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "TELEGRAM")
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Telegram] Publicados: {publicados}")
    return publicados

# ============================================================
# DISCORD (somente Cofre)
# ============================================================
def _discord_webhooks_from_cofre():
    # WEBHOOK_1, WEBHOOK_2...
    return [v for _,v in _cofre_get_many(("DISCORD","WEBHOOK_")) if v]

def _discord_send(webhook_url, content=None, image_bytes=None):
    data={"content":content or ""}
    files=None
    if image_bytes:
        files={"file":("resultado.png", image_bytes, "image/png")}
    r=requests.post(webhook_url, data=data, files=files, timeout=30)
    r.raise_for_status()
    return True

def publicar_em_discord(ws, candidatos):
    hooks = _discord_webhooks_from_cofre()
    if not hooks:
        _log("[DISCORD] Sem credenciais no Cofre (WEBHOOK_n). Pulando Discord.")
        return 0

    mode = _cofre_text_mode("DISCORD", default="TEXT_AND_IMAGE")
    post_with_image = _cofre_bool("DISCORD", "POST_DISCORD_WITH_IMAGE", default=True)

    publicados=0
    limite=min(MAX_PUBLICACOES_RODADA, len(candidatos))

    for rownum, row in candidatos[:limite]:
        base = montar_texto_publicacao(row, "DISCORD")
        msg = "" if mode=="IMAGE_ONLY" else base
        url_post=_strip_invisible(row[COL_URL-1]) if _safe_len(row,COL_URL) else ""

        ok_any=False
        try:
            if DRY_RUN:
                for wh in hooks:
                    _log(f"[Discord] DRY_RUN → {wh[-18:]}")
                ok_any=True
            else:
                img_bytes=None
                if post_with_image:
                    buf=_build_image_from_row(row)
                    img_bytes=buf.getvalue()

                for wh in hooks:
                    payload = msg
                    if url_post and payload:
                        payload = f"{payload}\n{url_post}"
                    elif url_post and not payload:
                        payload = url_post
                    _discord_send(wh, content=(payload or None), image_bytes=img_bytes)
                    _log(f"[Discord] OK → {wh[-18:]}")
                ok_any=True
        except Exception as e:
            _log(f"[Discord] erro: {e}")
            ok_any=False

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "DISCORD")
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Discord] Publicados: {publicados}")
    return publicados

# ============================================================
# PINTEREST (somente Cofre)
# ============================================================
def _pin_token_from_cofre():
    return (_cofre_get(("PINTEREST","ACCESS_TOKEN"), "") or "").strip()

def _pin_board_from_cofre():
    return (_cofre_get(("PINTEREST","BOARD_ID"), "") or "").strip()

def _pinterest_create_pin(token, board_id, title, description, link, image_bytes=None, image_url=None):
    url="https://api.pinterest.com/v5/pins"
    headers={"Authorization":f"Bearer {token}"}
    payload={
        "board_id": board_id,
        "title": (title or "")[:100],
        "description": (description or "")[:500]
    }
    if link:
        payload["link"]=link

    if image_bytes is not None:
        payload["media_source"]={
            "source_type":"image_base64",
            "content_type":"image/png",
            "data": base64.b64encode(image_bytes).decode("utf-8")
        }
    elif image_url:
        payload["media_source"]={"source_type":"image_url","url":image_url}
    else:
        raise ValueError("Pinterest: informe image_bytes ou image_url.")

    r=requests.post(url, headers=headers, json=payload, timeout=40)
    r.raise_for_status()
    return r.json().get("id")

def publicar_em_pinterest(ws, candidatos):
    token = _pin_token_from_cofre()
    board = _pin_board_from_cofre()
    if not (token and board):
        _log("[PINTEREST] Sem credenciais no Cofre (ACCESS_TOKEN + BOARD_ID). Pulando Pinterest.")
        return 0

    mode = _cofre_text_mode("PINTEREST", default="TEXT_AND_IMAGE")
    post_with_image = _cofre_bool("PINTEREST", "POST_PINTEREST_WITH_IMAGE", default=True)

    publicados=0
    limite=min(MAX_PUBLICACOES_RODADA, len(candidatos))

    for rownum, row in candidatos[:limite]:
        loteria = row[COL_LOTERIA-1] if _safe_len(row,COL_LOTERIA) else "Loteria"
        concurso= row[COL_CONCURSO-1] if _safe_len(row,COL_CONCURSO) else "0000"
        title=f"{loteria} — Concurso {concurso}"

        desc_full = montar_texto_publicacao(row, "PINTEREST")
        desc = "" if mode=="IMAGE_ONLY" else desc_full
        url_post=_strip_invisible(row[COL_URL-1]) if _safe_len(row,COL_URL) else ""

        try:
            if DRY_RUN:
                _log(f"[Pinterest] DRY_RUN: {title}")
                ok=True
            else:
                if post_with_image:
                    buf=_build_image_from_row(row)
                    pin_id=_pinterest_create_pin(token, board, title, desc, url_post, image_bytes=buf.getvalue())
                else:
                    pin_id=_pinterest_create_pin(token, board, title, desc, url_post, image_url=url_post or None)
                _log(f"[Pinterest] OK → {pin_id}")
                ok=True
        except Exception as e:
            _log(f"[Pinterest] erro: {e}")
            ok=False

        if ok and not DRY_RUN:
            marcar_publicado(ws, rownum, "PINTEREST")
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Pinterest] Publicados: {publicados}")
    return publicados

# ============================================================
# REDES ALVO (NÃO depende do Cofre para "ativar" rede)
# ============================================================
_SUPPORTED = ["X","FACEBOOK","TELEGRAM","DISCORD","PINTEREST"]

def _parse_target_networks() -> List[str]:
    raw = (TARGET_NETWORKS or "").strip()
    if not raw:
        return list(_SUPPORTED)
    parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
    # normaliza sinônimos
    norm=[]
    for p in parts:
        if p in ("TWITTER",): p="X"
        if p in ("META",): p="FACEBOOK"
        if p not in _SUPPORTED:
            _log(f"[Config] Rede ignorada (não suportada): {p}")
            continue
        norm.append(p)
    return norm or list(_SUPPORTED)

# ============================================================
# Keepalive
# ============================================================
def iniciar_keepalive():
    try:
        from flask import Flask
    except ImportError:
        _log("Flask não instalado; keepalive desativado.")
        return None

    app=Flask(__name__)

    @app.route("/")
    @app.route("/ping")
    def raiz():
        return "ok", 200

    def run():
        port=int(os.getenv("PORT", KEEPALIVE_PORT))
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    th=Thread(target=run, daemon=True)
    th.start()
    _log(f"Keepalive em 0.0.0.0:{os.getenv('PORT', KEEPALIVE_PORT)}")
    return th

def _print_config_summary(redes_alvo):
    _log("=== Config ===",
         f"TAB={SHEET_TAB} | COFRE_SHEET_ID={COFRE_SHEET_ID or '(vazio)'} | DRY_RUN={DRY_RUN}")
    _log("Redes alvo (Config):", ", ".join(redes_alvo) if redes_alvo else "(nenhuma)")
    _log("Canais Cofre (texto):", len(_cofre_cache.get("canais_list", [])))

# ============================================================
# MAIN
# ============================================================
def main():
    _log("Start", f"Origem={BOT_ORIGEM} | DRY_RUN={DRY_RUN} | KIT_FIRST={USE_KIT_IMAGE_FIRST}")

    keepalive_thread = iniciar_keepalive() if ENABLE_KEEPALIVE else None

    try:
        _cofre_load()

        redes_alvo = _parse_target_networks()
        _print_config_summary(redes_alvo)

        ws=_open_ws_principal()

        for rede in redes_alvo:
            rede = rede.upper()

            cand = coleta_candidatos_para(ws, rede)
            if not cand:
                _log(f"[{rede}] Nenhuma candidata.")
                continue

            if rede=="X":
                publicar_em_x(ws, cand)
            elif rede=="FACEBOOK":
                publicar_em_facebook(ws, cand)
            elif rede=="TELEGRAM":
                publicar_em_telegram(ws, cand)
            elif rede=="DISCORD":
                publicar_em_discord(ws, cand)
            elif rede=="PINTEREST":
                publicar_em_pinterest(ws, cand)
            else:
                _log(f"[{rede}] não suportada.")

        _log("Concluído.")

    except Exception as e:
        _log(f"[FATAL] {e}")
        raise
    finally:
        if ENABLE_KEEPALIVE and keepalive_thread:
            time.sleep(1)

if __name__=="__main__":
    main()