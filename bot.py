# bot.py — Portal SimonSports — Publicador Automático (X, Facebook, Telegram, Discord, Pinterest)
# Rev: 2026-01-17a — COFRE-ONLY para credenciais + bootstrap (cria placeholders faltantes e NÃO publica)
# - Lê Cofre (Credenciais_Rede / Redes_Sociais_Canais) como FONTE ÚNICA de credenciais das redes
# - .env fica apenas para CONFIG operacional (ex.: COFRE_SHEET_ID, aba, flags, limites) — NUNCA para tokens/chaves
# - Se faltar credencial no Cofre: cria linha placeholder (Valor vazio) e encerra com erro (fail-fast)
# - Sem filtro de data; publica quando a coluna da rede estiver VAZIA
# - Cria colunas "Publicado_<REDE>" se não existirem
# - Texto inclui TODOS os links ativos do Cofre (ordem crescente)
# - X_SKIP_DUP_CHECK controla o check de duplicidade (evita 401)

import os, re, io, glob, json, time, base64, pytz, tweepy, requests
import datetime as dt
from threading import Thread
from collections import defaultdict
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Imagem oficial (layout aprovado)
from app.imaging import gerar_imagem_loteria

load_dotenv()
TZ = pytz.timezone("America/Sao_Paulo")

# ---------------- ENV (APENAS CONFIG OPERACIONAL) ----------------
# IMPORTANTE: credenciais/tokens/chaves das redes NÃO são lidos do env.
SHEET_TAB = (os.getenv("SHEET_TAB", "ImportadosBlogger2") or "ImportadosBlogger2").strip()

COFRE_SHEET_ID   = (os.getenv("COFRE_SHEET_ID", "") or "").strip()
COFRE_ABA_CRED   = (os.getenv("COFRE_ABA_CRED", "Credenciais_Rede") or "Credenciais_Rede").strip()
COFRE_ABA_CANAIS = (os.getenv("COFRE_ABA_CANAIS", "Redes_Sociais_Canais") or "Redes_Sociais_Canais").strip()

TARGET_NETWORKS = [
    s.strip().upper()
    for s in (os.getenv("TARGET_NETWORKS", "X,FACEBOOK,TELEGRAM,DISCORD,PINTEREST") or "X").split(",")
    if s.strip()
]

DRY_RUN = (os.getenv("DRY_RUN", "false").strip().lower() == "true")

GLOBAL_TEXT_MODE      = (os.getenv("GLOBAL_TEXT_MODE", "") or "").strip().upper()
X_TEXT_MODE           = (os.getenv("X_TEXT_MODE", "") or "").strip().upper()
FACEBOOK_TEXT_MODE    = (os.getenv("FACEBOOK_TEXT_MODE", "") or "").strip().upper()
TELEGRAM_TEXT_MODE    = (os.getenv("TELEGRAM_TEXT_MODE", "") or os.getenv("MODO_TEXTO_TELEGRAM", "") or "").strip().upper()
DISCORD_TEXT_MODE     = (os.getenv("DISCORD_TEXT_MODE", "") or "").strip().upper()
PINTEREST_TEXT_MODE   = (os.getenv("PINTEREST_TEXT_MODE", "") or "").strip().upper()
VALID_TEXT_MODES      = {"IMAGE_ONLY", "TEXT_AND_IMAGE", "TEXT_ONLY"}

def get_text_mode(rede: str) -> str:
    specific = {
        "X": X_TEXT_MODE,
        "FACEBOOK": FACEBOOK_TEXT_MODE,
        "TELEGRAM": TELEGRAM_TEXT_MODE,
        "DISCORD": DISCORD_TEXT_MODE,
        "PINTEREST": PINTEREST_TEXT_MODE,
    }.get(rede, "")
    mode = (specific or GLOBAL_TEXT_MODE or "TEXT_AND_IMAGE").upper()
    return mode if mode in VALID_TEXT_MODES else "TEXT_AND_IMAGE"

# X (somente flags de comportamento via env)
X_POST_IN_ALL_ACCOUNTS  = (os.getenv("X_POST_IN_ALL_ACCOUNTS", "true").strip().lower() == "true")
POST_X_WITH_IMAGE       = (os.getenv("POST_X_WITH_IMAGE", "true").strip().lower() == "true")
COL_STATUS_X            = int(os.getenv("COL_STATUS_X", "8"))
X_REPLY_WITH_LINK_BELOW = False  # manter compat
X_SKIP_DUP_CHECK        = (os.getenv("X_SKIP_DUP_CHECK", "true").strip().lower() == "true")

# Facebook (somente flags/coluna via env)
POST_FB_WITH_IMAGE  = (os.getenv("POST_FB_WITH_IMAGE", "true").strip().lower() == "true")
COL_STATUS_FACEBOOK = int(os.getenv("COL_STATUS_FACEBOOK", "15"))

# Telegram (somente flags/coluna via env)
POST_TG_WITH_IMAGE  = (os.getenv("POST_TG_WITH_IMAGE", "true").strip().lower() == "true")
COL_STATUS_TELEGRAM = int(os.getenv("COL_STATUS_TELEGRAM", "10"))

# Discord (somente coluna via env)
COL_STATUS_DISCORD = int(os.getenv("COL_STATUS_DISCORD", "13"))

# Pinterest (somente coluna/flag via env)
COL_STATUS_PINTEREST      = int(os.getenv("COL_STATUS_PINTEREST", "14"))
POST_PINTEREST_WITH_IMAGE = (os.getenv("POST_PINTEREST_WITH_IMAGE", "true").strip().lower() == "true")

# KIT
USE_KIT_IMAGE_FIRST = (os.getenv("USE_KIT_IMAGE_FIRST", "false").strip().lower() == "true")
KIT_OUTPUT_DIR      = (os.getenv("KIT_OUTPUT_DIR", "output") or "output").strip()
PUBLIC_BASE_URL     = (os.getenv("PUBLIC_BASE_URL", "") or "").strip()

# Keepalive
ENABLE_KEEPALIVE = (os.getenv("ENABLE_KEEPALIVE", "false").strip().lower() == "true")
KEEPALIVE_PORT   = int(os.getenv("KEEPALIVE_PORT", "8080"))

# Limites
MAX_PUBLICACOES_RODADA = int(os.getenv("MAX_PUBLICACOES_RODADA", "30"))
PAUSA_ENTRE_POSTS      = float(os.getenv("PAUSA_ENTRE_POSTS", "2.5"))

def _detect_origem():
    if os.getenv("BOT_ORIGEM"): return os.getenv("BOT_ORIGEM").strip()
    if os.getenv("GITHUB_ACTIONS"): return "GitHub"
    if os.getenv("REPL_ID") or os.getenv("REPLIT_DB_URL"): return "Replit"
    if os.getenv("RENDER"): return "Render"
    return "Local"

BOT_ORIGEM = _detect_origem()

# ---------------- colunas planilha principal ----------------
COL_LOTERIA, COL_CONCURSO, COL_DATA, COL_NUMEROS, COL_URL = 1, 2, 3, 4, 5
COL_URL_IMAGEM, COL_IMAGEM = 6, 7
# P e Q continuam EXISTINDO, mas agora são apenas fallback (para canais, se Cofre não tiver)
COL_TG_DICAS  = 16  # P
COL_TG_PORTAL = 17  # Q

COL_STATUS_REDES = {
    "X": COL_STATUS_X,
    "FACEBOOK": COL_STATUS_FACEBOOK,
    "TELEGRAM": COL_STATUS_TELEGRAM,
    "DISCORD": COL_STATUS_DISCORD,
    "PINTEREST": COL_STATUS_PINTEREST
}

# ---------------- credenciais das redes (COFRE ONLY) ----------------
# estes globals são preenchidos EXCLUSIVAMENTE pelo Cofre
SHEET_ID = ""  # sempre vem do Cofre (GOOGLE_SHEET_ID)
FB_PAGE_IDS: List[str] = []
FB_PAGE_TOKENS: List[str] = []
TG_BOT_TOKEN: str = ""
TG_CHAT_IDS: List[str] = []
DISCORD_WEBHOOKS: List[str] = []
PINTEREST_ACCESS_TOKEN: str = ""
PINTEREST_BOARD_ID: str = ""

# ---------------- utils ----------------
def _log(*a): print(f"[{dt.datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}]", *a, flush=True)
def _now():   return dt.datetime.now(TZ)
def _ts_br(): return _now().strftime("%d/%m/%Y %H:%M")

def _safe_len(row, idx): return len(row) >= idx

def _strip_invisible(s: str) -> str:
    if s is None: return ""
    s = str(s)
    for ch in ["\u200B","\u200C","\u200D","\uFEFF","\u2060"]:
        s = s.replace(ch, "")
    return s.strip()

def _is_empty_status(v): return _strip_invisible(v) == ""

def _row_has_min_payload(row) -> bool:
    loteria = _strip_invisible(row[COL_LOTERIA-1]) if _safe_len(row,COL_LOTERIA) else ""
    numeros = _strip_invisible(row[COL_NUMEROS-1]) if _safe_len(row,COL_NUMEROS) else ""
    url     = _strip_invisible(row[COL_URL-1])     if _safe_len(row,COL_URL)     else ""
    if not (loteria and numeros and url): return False
    if not re.match(r"^https?://[^ ]+\.[^ ]+", url): return False
    if not re.search(r"\d", numeros): return False
    return True

# ---------------- Google Sheets ----------------
_cofre_cache: Dict[str, Dict] = {}  # "creds", "canais" (map) e "canais_list" (lista ordenada)

# sinônimos de "Rede" aceitos no Cofre
_COOL_REDE = {
    "GOOGLE": ["GOOGLE", "PLANILHAS GOOGLE", "PLANILHAS_GOOGLE", "PLANILHAS"],
    "X": ["X", "TWITTER"],
    "FACEBOOK": ["FACEBOOK", "META_FACEBOOK", "META"],
    "TELEGRAM": ["TELEGRAM", "TG"],
    "DISCORD": ["DISCORD"],
    "PINTEREST": ["PINTEREST"]
}

def _match_rede(key_rede: str, target: str) -> bool:
    kr = (key_rede or "").strip().upper()
    tg = (target or "").strip().upper()
    return (
        kr == tg
        or kr.replace("_"," ") == tg.replace("_"," ")
        or kr in _COOL_REDE.get(tg, [])
    )

def _gs_creds_from_cofre_only() -> Dict:
    # COFRE-ONLY (não lê env). Se houver GOOGLE_SERVICE_JSON no Cofre, usa. Senão, usa service_account.json.
    if not COFRE_SHEET_ID: return {}
    try:
        for (rede, chave), valor in _cofre_cache.get("creds", {}).items():
            if _match_rede(rede, "GOOGLE") and str(chave).upper() == "GOOGLE_SERVICE_JSON":
                v = _strip_invisible(valor)
                if v:
                    return json.loads(v)
    except Exception:
        pass
    return {}

def _gs_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    info = _gs_creds_from_cofre_only()
    if info:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scopes)
        return gspread.authorize(creds)

    # padrão: arquivo local (recomendado no seu setup)
    path = "service_account.json"
    if not os.path.exists(path):
        raise RuntimeError("Credencial Google ausente: coloque service_account.json na raiz (ou informe GOOGLE_SERVICE_JSON no Cofre).")
    creds = ServiceAccountCredentials.from_json_keyfile_name(path, scopes)
    return gspread.authorize(creds)

def _open_cofre_ws(tab: str):
    if not COFRE_SHEET_ID:
        raise RuntimeError("COFRE_SHEET_ID não definido no .env (obrigatório).")
    sh = _gs_client().open_by_key(COFRE_SHEET_ID)
    return sh.worksheet(tab)

def _open_ws():
    sid = _strip_invisible(SHEET_ID) or _strip_invisible(_cofre_get(("GOOGLE","GOOGLE_SHEET_ID"), "")) or ""
    if not sid:
        raise RuntimeError("GOOGLE_SHEET_ID ausente no Cofre (aba Credenciais_Rede).")
    sh = _gs_client().open_by_key(sid)
    return sh.worksheet(SHEET_TAB)

def _ensure_status_column(ws, rede: str, env_col: Optional[int]) -> int:
    if env_col and isinstance(env_col,int) and env_col>0:
        return env_col
    header = ws.row_values(1)
    target = f"Publicado_{rede}"
    for i,h in enumerate(header, start=1):
        if h and h.strip().lower() == target.lower():
            return i
    col = len(header)+1
    ws.update_cell(1, col, target)
    _log(f"[Planilha] Criada coluna: {target} (col {col})")
    return col

def marcar_publicado(ws, rownum, rede, value=None):
    col = COL_STATUS_REDES.get(rede, None)
    if not col:
        col = _ensure_status_column(ws, rede, None)
        COL_STATUS_REDES[rede] = col
    value = value or f"Publicado {rede} via {BOT_ORIGEM} em {_ts_br()}"
    ws.update_cell(rownum, col, value)

# ---------------- Cofre ----------------
def _cofre_load():
    # Credenciais + Canais
    creds_ws = _open_cofre_ws(COFRE_ABA_CRED)
    creds_map = {}
    if creds_ws:
        rows = creds_ws.get_all_values()
        for r in rows[1:]:
            rede = _strip_invisible(r[0]) if len(r)>0 else ""
            chave= _strip_invisible(r[2]) if len(r)>2 else ""
            valor= _strip_invisible(r[3]) if len(r)>3 else ""
            # IMPORTANTE: armazena mesmo com VALOR vazio para evitar duplicar placeholders
            if rede and chave:
                creds_map[(rede.upper(), chave.upper())] = valor
    _cofre_cache["creds"] = creds_map

    canais_ws = _open_cofre_ws(COFRE_ABA_CANAIS)
    canais_map = {"TELEGRAM_CANAL_1":"", "TELEGRAM_CANAL_2":""}  # legacy (fallback)
    canais_list = []
    if canais_ws:
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
                canais_list.append({"ordem":o, "rede":rede, "tipo":tipo, "nome":nome or tipo, "url":url})
                if tipo in canais_map and url:
                    canais_map[tipo] = url
    canais_list.sort(key=lambda x: x["ordem"])
    _cofre_cache["canais"] = canais_map
    _cofre_cache["canais_list"] = canais_list

def _cofre_get(key: Tuple[str,str], default: Optional[str]=None) -> Optional[str]:
    """Busca por (rede, chave) aceitando sinônimos de rede."""
    rede, chave = (key[0] or "").upper(), (key[1] or "").upper()
    m = _cofre_cache.get("creds", {})

    v = m.get((rede, chave))
    if v is not None:
        return v if v != "" else default

    for (r,k), val in m.items():
        if k == chave and _match_rede(r, rede):
            return val if val != "" else default

    return default

def _cofre_get_many(prefix: Tuple[str,str]) -> List[Tuple[int,str]]:
    rede, pref = (prefix[0] or "").upper(), (prefix[1] or "").upper()
    m = _cofre_cache.get("creds", {})
    out=[]
    for (r,k),v in m.items():
        if _match_rede(r, rede) and str(k).upper().startswith(pref):
            mm = re.search(rf"^{re.escape(pref)}(\d+)$", str(k).upper())
            if mm:
                try:
                    out.append((int(mm.group(1)), v))
                except Exception:
                    pass
    out.sort(key=lambda x:x[0])
    return out

def _cofre_ensure_headers_cred(ws):
    header = ws.row_values(1)
    want = ["Rede","Conta","Chave","Valor"]
    if not header:
        ws.update("A1:D1", [want])
        return
    got = [(_strip_invisible(h) or "") for h in header[:4]]
    if got != want:
        _log("[Cofre] Aviso: cabeçalho de Credenciais_Rede não está exatamente em Rede|Conta|Chave|Valor (mantendo como está).")

def _cofre_find_cred_row(ws, rede:str, chave:str) -> Optional[int]:
    """Procura (Rede, Chave) na planilha, retorna row index ou None. Aceita sinônimos de Rede."""
    target_rede = (rede or "").strip().upper()
    target_key  = (chave or "").strip().upper()
    vals = ws.get_all_values()
    for i, r in enumerate(vals[1:], start=2):
        r_rede  = _strip_invisible(r[0]).upper() if len(r)>0 else ""
        r_chave = _strip_invisible(r[2]).upper() if len(r)>2 else ""
        if r_chave == target_key and _match_rede(r_rede, target_rede):
            return i
    return None

def _cofre_append_cred_if_missing(rede:str, conta:str, chave:str):
    ws = _open_cofre_ws(COFRE_ABA_CRED)
    _cofre_ensure_headers_cred(ws)

    # evita duplicar placeholders
    exists = _cofre_find_cred_row(ws, rede, chave)
    if exists:
        return False

    ws.append_row([rede, conta, chave, ""], value_input_option="RAW")
    _log(f"[Cofre] Placeholder criado: Rede={rede} | Conta={conta} | Chave={chave} | Valor=(vazio)")
    return True

def _cofre_bootstrap_required_or_fail(targets: List[str]):
    """
    Garante que as chaves mínimas existam no Cofre.
    Se faltar, cria placeholders e ENCERRA com erro (NUNCA usa env).
    """
    conta_padrao = "Portal SimonSports"
    missing: List[Tuple[str,str,str]] = []

    def need(rede:str, chave:str, conta:str=None):
        v = _cofre_get((rede, chave), None)
        if not v:
            missing.append((rede, conta or conta_padrao, chave))

    # Google (planilha principal)
    need("GOOGLE", "GOOGLE_SHEET_ID")

    tset = [s.upper().strip() for s in (targets or [])]

    if "X" in tset:
        need("X", "TWITTER_API_KEY_1", "PSimonSports")
        need("X", "TWITTER_API_SECRET_1", "PSimonSports")
        need("X", "TWITTER_ACCESS_TOKEN_1", "PSimonSports")
        need("X", "TWITTER_ACCESS_SECRET_1", "PSimonSports")
        # ACC2 é opcional (se existir, usa). Não força.

    if "FACEBOOK" in tset:
        need("FACEBOOK", "PAGE_ID_1")
        need("FACEBOOK", "PAGE_TOKEN_1")

    if "TELEGRAM" in tset:
        need("TELEGRAM", "BOT_TOKEN")
        need("TELEGRAM", "CHAT_ID_1")

    if "DISCORD" in tset:
        need("DISCORD", "WEBHOOK_1")

    if "PINTEREST" in tset:
        need("PINTEREST", "ACCESS_TOKEN")
        need("PINTEREST", "BOARD_ID")

    if missing:
        created_any = False
        for rede, conta, chave in missing:
            created_any = _cofre_append_cred_if_missing(rede, conta, chave) or created_any

        # atualiza mensagem (mesmo se já existia linha, mas estava vazia)
        raise RuntimeError(
            "Credenciais faltando no Cofre (aba Credenciais_Rede). "
            "Foram criados placeholders (quando não existiam). "
            "Preencha a coluna Valor e execute novamente."
        )

def _apply_cofre_to_runtime_and_networks():
    """
    COFRE-ONLY:
    Carrega credenciais do Cofre para variáveis globais e retorna redes ativas,
    mantendo a ordem definida em TARGET_NETWORKS.
    """
    global SHEET_ID, FB_PAGE_IDS, FB_PAGE_TOKENS, TG_BOT_TOKEN, TG_CHAT_IDS, DISCORD_WEBHOOKS
    global PINTEREST_ACCESS_TOKEN, PINTEREST_BOARD_ID

    SHEET_ID = _strip_invisible(_cofre_get(("GOOGLE","GOOGLE_SHEET_ID"), "")) or ""

    # X: valida ACC1
    x1_ok = all(_cofre_get(("X", k), "") for k in [
        "TWITTER_API_KEY_1","TWITTER_API_SECRET_1","TWITTER_ACCESS_TOKEN_1","TWITTER_ACCESS_SECRET_1"
    ])

    # Facebook: PAGE_ID_n / PAGE_TOKEN_n
    fb_ids    = _cofre_get_many(("FACEBOOK","PAGE_ID_"))
    fb_tokens = _cofre_get_many(("FACEBOOK","PAGE_TOKEN_"))
    mp = {n:v for n,v in fb_ids}; mt = {n:v for n,v in fb_tokens}
    ids=[]; toks=[]
    for n in sorted(set(mp)&set(mt)):
        if mp[n] and mt[n]:
            ids.append(mp[n]); toks.append(mt[n])
    FB_PAGE_IDS, FB_PAGE_TOKENS = ids, toks

    # Telegram: BOT_TOKEN + CHAT_ID_n
    TG_BOT_TOKEN = _strip_invisible(_cofre_get(("TELEGRAM","BOT_TOKEN"), "")) or ""
    TG_CHAT_IDS  = [v for _,v in _cofre_get_many(("TELEGRAM","CHAT_ID_")) if _strip_invisible(v)]

    # Discord: WEBHOOK_n
    DISCORD_WEBHOOKS = [v for _,v in _cofre_get_many(("DISCORD","WEBHOOK_")) if _strip_invisible(v)]

    # Pinterest
    PINTEREST_ACCESS_TOKEN = _strip_invisible(_cofre_get(("PINTEREST","ACCESS_TOKEN"), "")) or ""
    PINTEREST_BOARD_ID     = _strip_invisible(_cofre_get(("PINTEREST","BOARD_ID"), "")) or ""

    # redes ativas (mantém ordem de TARGET_NETWORKS)
    active = set()
    if x1_ok: active.add("X")
    if FB_PAGE_IDS and FB_PAGE_TOKENS and len(FB_PAGE_IDS)==len(FB_PAGE_TOKENS): active.add("FACEBOOK")
    if TG_BOT_TOKEN and TG_CHAT_IDS: active.add("TELEGRAM")
    if DISCORD_WEBHOOKS: active.add("DISCORD")
    if PINTEREST_ACCESS_TOKEN and PINTEREST_BOARD_ID: active.add("PINTEREST")

    ordered = [r for r in TARGET_NETWORKS if r in active]
    if ordered:
        _log(f"[Cofre] Redes ativas: {', '.join(ordered)}")
    else:
        _log("[Cofre] Nenhuma rede ativa detectada (mas credenciais podem estar vazias/pendentes).")
    return ordered

# ---------------- imagem ----------------
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
    if not USE_KIT_IMAGE_FIRST:
        return None
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
            files=sorted(glob.glob(pat))
            if files:
                with open(files[0],"rb") as f:
                    buf=io.BytesIO(f.read()); buf.seek(0)
                    return buf
        return None
    except Exception as e:
        _log(f"[KIT] erro: {e}")
        return None

def _build_image_from_row(row):
    buf=_try_load_kit_image(row)
    if buf:
        return buf
    loteria  = row[COL_LOTERIA-1]  if _safe_len(row,COL_LOTERIA)  else "Loteria"
    concurso = row[COL_CONCURSO-1] if _safe_len(row,COL_CONCURSO) else "0000"
    data_br  = row[COL_DATA-1]     if _safe_len(row,COL_DATA)     else _now().strftime("%d/%m/%Y")
    numeros  = row[COL_NUMEROS-1]  if _safe_len(row,COL_NUMEROS)  else ""
    url_res  = row[COL_URL-1]      if _safe_len(row,COL_URL)      else ""
    return gerar_imagem_loteria(str(loteria), str(concurso), str(data_br), str(numeros), str(url_res))

# ---------------- texto da publicação (TODOS os canais) ----------------
def _build_canais_block_for(rede_alvo: str, max_chars: int = None) -> str:
    """
    Monta bloco:
    Inscreva-se nos nossos canais
    Nome
    URL
    (lista completa do Cofre; corta por limite quando max_chars é dado)
    """
    canais = _cofre_cache.get("canais_list", [])
    if not canais:
        return ""
    lines = ["Inscreva-se nos nossos canais"]
    for ch in canais:
        nome = ch.get("nome") or ch.get("tipo") or ch.get("rede") or "Canal"
        url  = ch.get("url") or ""
        if not url:
            continue
        lines += [nome, url, ""]

    txt = "\n".join([s for s in lines if s is not None]).strip()

    if max_chars and len(txt) > max_chars:
        header = "Inscreva-se nos nossos canais\n"
        rest = txt[len(header):].split("\n")

        pairs = []
        i = 0
        while i < len(rest):
            name = rest[i] if i < len(rest) else ""
            url  = rest[i+1] if i+1 < len(rest) else ""
            pairs.append((name, url))
            i += 3 if i+2 < len(rest) and rest[i+2] == "" else 2

        out = header
        for (name, url) in pairs:
            candidate = f"{out}{name}\n{url}\n\n"
            if len(candidate) <= max_chars:
                out = candidate
            else:
                break
        return out.strip()

    return txt


def montar_texto_publicacao(row, rede_alvo: str) -> str:
    """Texto final para a rede (X/FACEBOOK/TELEGRAM/DISCORD/PINTEREST)."""
    url = (_strip_invisible(row[COL_URL-1]) if _safe_len(row, COL_URL) else "")
    head = f"Resultado completo aqui >>>>\n{url}\n\n".strip()

    canais_block = ""
    canais_list = _cofre_cache.get("canais_list", [])

    if canais_list:
        if rede_alvo == "X":
            # deixa margem para evitar estouro (limite prático)
            canais_block = _build_canais_block_for(rede_alvo, max_chars=max(0, 275 - len(head) - 1))
        else:
            canais_block = _build_canais_block_for(rede_alvo)
    else:
        # fallback P/Q (legado)
        dicas  = (_strip_invisible(row[COL_TG_DICAS-1])  if _safe_len(row, COL_TG_DICAS)  else "")
        portal = (_strip_invisible(row[COL_TG_PORTAL-1]) if _safe_len(row, COL_TG_PORTAL) else "")
        if dicas or portal:
            parts = ["Inscreva-se nos nossos canais"]
            if dicas:
                parts += ["Dicas Esportivas", dicas, ""]
            if portal:
                parts += ["Portal SimonSports", portal, ""]
            canais_block = "\n".join([p for p in parts if p]).strip()

    text = head + ("\n" + canais_block if canais_block else "")
    if rede_alvo == "X" and len(text) > 275:
        text = text[:275]
    return text.strip()


# ---------------- coleta candidatos ----------------
def coleta_candidatos_para(ws, rede: str):
    linhas = ws.get_all_values()
    if len(linhas) <= 1:
        _log(f"[{rede}] Planilha sem dados.")
        return []

    if rede not in COL_STATUS_REDES or not COL_STATUS_REDES[rede]:
        env_col = {
            "X": COL_STATUS_X,
            "FACEBOOK": COL_STATUS_FACEBOOK,
            "TELEGRAM": COL_STATUS_TELEGRAM,
            "DISCORD": COL_STATUS_DISCORD,
            "PINTEREST": COL_STATUS_PINTEREST
        }.get(rede, None)
        COL_STATUS_REDES[rede] = _ensure_status_column(ws, rede, env_col)

    col_status = COL_STATUS_REDES.get(rede)
    data = linhas[1:]
    cand = []

    for rindex, row in enumerate(data, start=2):
        status_val = row[col_status-1] if len(row) >= col_status else ""
        if not _is_empty_status(status_val):
            continue
        if not _row_has_min_payload(row):
            continue
        cand.append((rindex, row))

    _log(f"[{rede}] Candidatas: {len(cand)}/{len(data)}")
    return cand


# ---------------- publicadores ----------------
def _tw_creds(idx: int) -> Dict[str, str]:
    # COFRE-ONLY: nunca ler env
    return {
        "api_key":       _cofre_get(("X", f"TWITTER_API_KEY_{idx}"), "") or "",
        "api_secret":    _cofre_get(("X", f"TWITTER_API_SECRET_{idx}"), "") or "",
        "access_token":  _cofre_get(("X", f"TWITTER_ACCESS_TOKEN_{idx}"), "") or "",
        "access_secret": _cofre_get(("X", f"TWITTER_ACCESS_SECRET_{idx}"), "") or "",
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


def build_x_accounts():
    accs = []

    def ok(d): 
        return all(d.get(k) for k in ("api_key", "api_secret", "access_token", "access_secret"))

    tw1 = _tw_creds(1)
    if ok(tw1):
        accs.append(XAccount("ACC1", **tw1))
    else:
        _log("Conta X ACC1 incompleta no Cofre.")

    tw2 = _tw_creds(2)
    if ok(tw2):
        accs.append(XAccount("ACC2", **tw2))

    if not accs:
        raise RuntimeError("Nenhuma conta X configurada no Cofre.")

    return accs


_recent_tweets_cache = defaultdict(set)
_postados_nesta_execucao = defaultdict(set)


def x_load_recent_texts(acc, max_results=50):
    if X_SKIP_DUP_CHECK:
        return set()
    try:
        resp = acc.client_v2.get_users_tweets(
            id=acc.user_id,
            max_results=min(max_results, 100),
            tweet_fields=["text"]
        )
        out = set()
        if resp and resp.data:
            for tw in resp.data:
                t = (tw.text or "").strip()
                if t:
                    out.add(t)
        _recent_tweets_cache[acc.label] = set(list(out)[-50:])
        return _recent_tweets_cache[acc.label]
    except Exception as e:
        _log(f"[{acc.handle}] warning: tweets recentes: {e}")
        return set()


def x_is_dup(acc, text):
    if X_SKIP_DUP_CHECK:
        return False
    t = (text or "").strip()
    return bool(t and (t in _recent_tweets_cache[acc.label] or t in _postados_nesta_execucao[acc.label]))


def x_upload_media_if_any(acc, row):
    if not POST_X_WITH_IMAGE or DRY_RUN:
        return None
    try:
        buf = _build_image_from_row(row)
        media = acc.api_v1.media_upload(filename="resultado.png", file=buf)
        return [media.media_id_string]
    except Exception as e:
        _log(f"[{acc.handle}] Erro imagem: {e}")
        return None


def publicar_em_x(ws, candidatos):
    contas = build_x_accounts()
    for acc in contas:
        _recent_tweets_cache[acc.label] = x_load_recent_texts(acc, 50)
        _log(f"[X] Conta: {acc.handle}")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode_cfg = get_text_mode("X")

    for rownum, row in candidatos[:limite]:
        texto_full = montar_texto_publicacao(row, "X")
        mode = "IMAGE_ONLY" if X_REPLY_WITH_LINK_BELOW else mode_cfg
        texto_para = "" if mode == "IMAGE_ONLY" else texto_full

        ok_all = True

        if X_POST_IN_ALL_ACCOUNTS:
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
                                text=(texto_para or None) if mode != "IMAGE_ONLY" else None,
                                media_ids=media_ids if POST_X_WITH_IMAGE else None
                            )
                            if texto_para:
                                _postados_nesta_execucao[acc.label].add(texto_para)
                                _recent_tweets_cache[acc.label].add(texto_para)
                            _log(f"[X][{acc.handle}] OK → {resp.data['id']}")
                except Exception as e:
                    _log(f"[X][{acc.handle}] erro: {e}")
                    ok_all = False
                time.sleep(0.7)
        else:
            acc = contas[0]
            media_ids = x_upload_media_if_any(acc, row)
            try:
                if DRY_RUN:
                    _log(f"[X][{acc.handle}] DRY_RUN")
                else:
                    if texto_para and x_is_dup(acc, texto_para):
                        _log(f"[X][{acc.handle}] SKIP duplicado.")
                    else:
                        resp = acc.client_v2.create_tweet(
                            text=(texto_para or None) if mode != "IMAGE_ONLY" else None,
                            media_ids=media_ids if POST_X_WITH_IMAGE else None
                        )
                        if texto_para:
                            _postados_nesta_execucao[acc.label].add(texto_para)
                            _recent_tweets_cache[acc.label].add(texto_para)
                        _log(f"[X][{acc.handle}] OK → {resp.data['id']}")
            except Exception as e:
                _log(f"[X][{acc.handle}] erro: {e}")
                ok_all = False

        if ok_all and not DRY_RUN:
            marcar_publicado(ws, rownum, "X")
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[X] Publicados: {publicados}")
    return publicados


# Facebook
def _fb_post_text(pid, token, message, link=None):
    url = f"https://graph.facebook.com/v19.0/{pid}/feed"
    data = {"message": message, "access_token": token}
    if link:
        data["link"] = link
    r = requests.post(url, data=data, timeout=25)
    r.raise_for_status()
    return r.json().get("id")


def _fb_post_photo(pid, token, caption, image_bytes):
    url = f"https://graph.facebook.com/v19.0/{pid}/photos"
    files = {"source": ("resultado.png", image_bytes, "image/png")}
    data = {"caption": caption, "published": "true", "access_token": token}
    r = requests.post(url, data=data, files=files, timeout=40)
    r.raise_for_status()
    return r.json().get("id")


def publicar_em_facebook(ws, candidatos):
    if not FB_PAGE_IDS or not FB_PAGE_TOKENS or len(FB_PAGE_IDS) != len(FB_PAGE_TOKENS):
        raise RuntimeError("Facebook: configure pares PAGE_ID_n / PAGE_TOKEN_n no Cofre.")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("FACEBOOK")

    for rownum, row in candidatos[:limite]:
        base = montar_texto_publicacao(row, "FACEBOOK")
        msg = "" if mode == "IMAGE_ONLY" else base

        ok_any = False
        for pid, ptok in zip(FB_PAGE_IDS, FB_PAGE_TOKENS):
            try:
                if DRY_RUN:
                    _log(f"[Facebook][{pid}] DRY_RUN")
                    ok = True
                else:
                    if POST_FB_WITH_IMAGE:
                        buf = _build_image_from_row(row)
                        fb_id = _fb_post_photo(pid, ptok, msg, buf.getvalue())
                    else:
                        url_post = _strip_invisible(row[COL_URL-1]) if _safe_len(row, COL_URL) else ""
                        fb_id = _fb_post_text(pid, ptok, msg, link=url_post or None)
                    _log(f"[Facebook][{pid}] OK → {fb_id}")
                    ok = True
            except Exception as e:
                _log(f"[Facebook][{pid}] erro: {e}")
                ok = False

            ok_any = ok_any or ok
            time.sleep(0.7)

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "FACEBOOK")
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Facebook] Publicados: {publicados}")
    return publicados


# Telegram
def _tg_send_photo(token, chat_id, caption, image_bytes):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    files = {"photo": ("resultado.png", image_bytes, "image/png")}
    data = {"chat_id": chat_id, "caption": caption}
    r = requests.post(url, data=data, files=files, timeout=40)
    r.raise_for_status()
    return r.json().get("result", {}).get("message_id")


def _tg_send_text(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": False}
    r = requests.post(url, data=data, timeout=25)
    r.raise_for_status()
    return r.json().get("result", {}).get("message_id")


def publicar_em_telegram(ws, candidatos):
    if not TG_BOT_TOKEN or not TG_CHAT_IDS:
        raise RuntimeError("Telegram: BOT_TOKEN e pelo menos um CHAT_ID_n são necessários no Cofre.")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("TELEGRAM")

    for rownum, row in candidatos[:limite]:
        base = montar_texto_publicacao(row, "TELEGRAM")
        msg = "" if mode == "IMAGE_ONLY" else base

        ok_any = False
        for chat_id in TG_CHAT_IDS:
            try:
                if DRY_RUN:
                    _log(f"[Telegram][{chat_id}] DRY_RUN")
                    ok = True
                else:
                    if POST_TG_WITH_IMAGE:
                        buf = _build_image_from_row(row)
                        msg_id = _tg_send_photo(TG_BOT_TOKEN, chat_id, msg, buf.getvalue())
                    else:
                        final_msg = msg
                        url_post = _strip_invisible(row[COL_URL-1]) if _safe_len(row, COL_URL) else ""
                        if url_post and final_msg:
                            final_msg = f"{final_msg}\n{url_post}"
                        elif url_post and not final_msg:
                            final_msg = url_post
                        msg_id = _tg_send_text(TG_BOT_TOKEN, chat_id, final_msg or "")
                    _log(f"[Telegram][{chat_id}] OK → {msg_id}")
                    ok = True
            except Exception as e:
                _log(f"[Telegram][{chat_id}] erro: {e}")
                ok = False

            ok_any = ok_any or ok
            time.sleep(0.5)

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "TELEGRAM")
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Telegram] Publicados: {publicados}")
    return publicados


# Discord
def _discord_send(webhook_url, content=None, image_bytes=None):
    data = {"content": content or ""}
    files = None
    if image_bytes:
        files = {"file": ("resultado.png", image_bytes, "image/png")}
    r = requests.post(webhook_url, data=data, files=files, timeout=30)
    r.raise_for_status()
    return True


def publicar_em_discord(ws, candidatos):
    if not DISCORD_WEBHOOKS:
        raise RuntimeError("Discord: defina WEBHOOK_n no Cofre.")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("DISCORD")

    for rownum, row in candidatos[:limite]:
        base = montar_texto_publicacao(row, "DISCORD")
        msg = "" if mode == "IMAGE_ONLY" else base

        ok_any = False
        try:
            if DRY_RUN:
                for wh in DISCORD_WEBHOOKS:
                    _log(f"[Discord] DRY_RUN → {wh[-18:]}")
                ok_any = True
            else:
                buf = _build_image_from_row(row)
                img = buf.getvalue()
                for wh in DISCORD_WEBHOOKS:
                    payload = msg
                    url_post = _strip_invisible(row[COL_URL-1]) if _safe_len(row, COL_URL) else ""
                    if url_post and payload:
                        payload = f"{payload}\n{url_post}"
                    elif url_post and not payload:
                        payload = url_post

                    _discord_send(wh, content=(payload or None), image_bytes=img)
                    _log(f"[Discord] OK → {wh[-18:]}")
                ok_any = True
        except Exception as e:
            _log(f"[Discord] erro: {e}")
            ok_any = False

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "DISCORD")
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Discord] Publicados: {publicados}")
    return publicados


# Pinterest
def _pinterest_create_pin(token, board_id, title, description, link, image_bytes=None, image_url=None):
    url = "https://api.pinterest.com/v5/pins"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"board_id": board_id, "title": title[:100], "description": (description or "")[:500]}
    if link:
        payload["link"] = link

    if image_bytes is not None:
        payload["media_source"] = {
            "source_type": "image_base64",
            "content_type": "image/png",
            "data": base64.b64encode(image_bytes).decode("utf-8")
        }
    elif image_url:
        payload["media_source"] = {"source_type": "image_url", "url": image_url}
    else:
        raise ValueError("Pinterest: informe image_bytes ou image_url.")

    r = requests.post(url, headers=headers, json=payload, timeout=40)
    r.raise_for_status()
    return r.json().get("id")


def publicar_em_pinterest(ws, candidatos):
    if not (PINTEREST_ACCESS_TOKEN and PINTEREST_BOARD_ID):
        raise RuntimeError("Pinterest: ACCESS_TOKEN e BOARD_ID são necessários no Cofre.")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("PINTEREST")

    for rownum, row in candidatos[:limite]:
        loteria = row[COL_LOTERIA-1] if _safe_len(row, COL_LOTERIA) else "Loteria"
        concurso = row[COL_CONCURSO-1] if _safe_len(row, COL_CONCURSO) else "0000"
        title = f"{loteria} — Concurso {concurso}"

        desc_full = montar_texto_publicacao(row, "PINTEREST")
        desc = "" if mode == "IMAGE_ONLY" else desc_full
        url_post = _strip_invisible(row[COL_URL-1]) if _safe_len(row, COL_URL) else ""

        try:
            if DRY_RUN:
                _log(f"[Pinterest] DRY_RUN: {title}")
                ok = True
            else:
                if POST_PINTEREST_WITH_IMAGE:
                    buf = _build_image_from_row(row)
                    pin_id = _pinterest_create_pin(
                        PINTEREST_ACCESS_TOKEN, PINTEREST_BOARD_ID,
                        title, desc, url_post, image_bytes=buf.getvalue()
                    )
                else:
                    pin_id = _pinterest_create_pin(
                        PINTEREST_ACCESS_TOKEN, PINTEREST_BOARD_ID,
                        title, desc, url_post, image_url=url_post or None
                    )
                _log(f"[Pinterest] OK → {pin_id}")
                ok = True
        except Exception as e:
            _log(f"[Pinterest] erro: {e}")
            ok = False

        if ok and not DRY_RUN:
            marcar_publicado(ws, rownum, "PINTEREST")
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Pinterest] Publicados: {publicados}")
    return publicados


# Keepalive
def iniciar_keepalive():
    try:
        from flask import Flask
    except ImportError:
        _log("Flask não instalado; keepalive desativado.")
        return None

    app = Flask(__name__)

    @app.route("/")
    @app.route("/ping")
    def raiz():
        return "ok", 200

    def run():
        port = int(os.getenv("PORT", KEEPALIVE_PORT))
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    th = Thread(target=run, daemon=True)
    th.start()
    _log(f"Keepalive em 0.0.0.0:{os.getenv('PORT', KEEPALIVE_PORT)}")
    return th


def _print_config_summary(redes_alvo):
    _log("=== Config ===", f"TAB={SHEET_TAB} | COFRE={COFRE_SHEET_ID or '(vazio)'}")
    _log("Redes alvo:", ", ".join(redes_alvo) if redes_alvo else "(nenhuma ativa)")
    _log("Canais Cofre:", len(_cofre_cache.get("canais_list", [])))


def main():
    _log("Start", f"Origem={BOT_ORIGEM} | DRY_RUN={DRY_RUN} | KIT_FIRST={USE_KIT_IMAGE_FIRST}")

    keepalive_thread = iniciar_keepalive() if ENABLE_KEEPALIVE else None

    try:
        _cofre_load()

        # BOOTSTRAP: cria placeholders e encerra se faltar qualquer credencial mínima
        _cofre_bootstrap_required_or_fail(TARGET_NETWORKS)

        # aplica credenciais do Cofre para runtime e define redes ativas (na ordem de TARGET_NETWORKS)
        redes_alvo = _apply_cofre_to_runtime_and_networks()
        _print_config_summary(redes_alvo)

        ws = _open_ws()

        for rede in redes_alvo:
            rede = rede.upper()
            cand = coleta_candidatos_para(ws, rede)
            if not cand:
                _log(f"[{rede}] Nenhuma candidata.")
                continue

            if rede == "X":
                publicar_em_x(ws, cand)
            elif rede == "FACEBOOK":
                publicar_em_facebook(ws, cand)
            elif rede == "TELEGRAM":
                publicar_em_telegram(ws, cand)
            elif rede == "DISCORD":
                publicar_em_discord(ws, cand)
            elif rede == "PINTEREST":
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


if __name__ == "__main__":
    main()