# -*- coding: utf-8 -*-
"""
Portal SimonSports — Publicador Automático (X, Facebook, Telegram, Discord, Pinterest)
Arquivo: bot.py
Rev: 2025-11-27 — Integração total com Planilha Cofre + canais padrão do Cofre
- Lê credenciais primeiro do .env; se vazio, busca no Cofre (COFRE_SHEET_ID).
- Canais Telegram padrão: pega os 2 primeiros Ativo=Sim na aba COFRE_ABA_CANAIS (ordem crescente)
  para preencher P/Q quando estiverem vazios.
- Publica SEM filtro de data: posta quando a coluna da REDE está VAZIA.
- Ignora “enfileirado”: status por rede é independente.
- Imagem: usa /output (KIT) se USE_KIT_IMAGE_FIRST=true; senão imaging oficial (app/imaging.py).
- Texto único aprovado (E + P + Q com “Inscreva-se”).
- X: Tweepy v1 upload mídia + v2 create_tweet; opção postar em todas as contas.
- Facebook: photo ou feed com link.
- Telegram: sendPhoto ou sendMessage para 1..N chats.
- Discord: webhooks 1..N com imagem.
- Pinterest: API v5 (image_base64 ou image_url); por padrão com imagem.

Dependências:
  pip install gspread oauth2client pytz requests tweepy python-dotenv flask
"""

import os, re, io, glob, json, time, base64
import datetime as dt
from typing import Optional, List, Tuple, Dict
from threading import Thread

import pytz
import requests
import tweepy
from dotenv import load_dotenv

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Imagem oficial (layout aprovado)
from app.imaging import gerar_imagem_loteria  # deve existir

# =========================
# CARREGA .env
# =========================
load_dotenv()
TZ = pytz.timezone("America/Sao_Paulo")

SHEET_ID  = (os.getenv("GOOGLE_SHEET_ID", "") or "").strip()
SHEET_TAB = (os.getenv("SHEET_TAB", "ImportadosBlogger2") or "").strip()

# Planilha Cofre (opcional, recomendado)
COFRE_SHEET_ID   = (os.getenv("COFRE_SHEET_ID","") or "").strip()
COFRE_ABA_CRED   = (os.getenv("COFRE_ABA_CRED","Credenciais_Rede") or "").strip()
COFRE_ABA_CANAIS = (os.getenv("COFRE_ABA_CANAIS","Redes_Sociais_Canais") or "").strip()

# Quais redes publicar nesta execução (fallback se não usar o Cofre)
TARGET_NETWORKS = [
    s.strip().upper() for s in (os.getenv("TARGET_NETWORKS", "X") or "").split(",") if s.strip()
]

# Modo de texto
GLOBAL_TEXT_MODE      = (os.getenv("GLOBAL_TEXT_MODE", "") or "").strip().upper()
X_TEXT_MODE           = (os.getenv("X_TEXT_MODE", "") or "").strip().upper()
FACEBOOK_TEXT_MODE    = (os.getenv("FACEBOOK_TEXT_MODE", "") or "").strip().upper()
TELEGRAM_TEXT_MODE    = (os.getenv("TELEGRAM_TEXT_MODE", "") or "").strip().upper()
DISCORD_TEXT_MODE     = (os.getenv("DISCORD_TEXT_MODE", "") or "").strip().upper()
PINTEREST_TEXT_MODE   = (os.getenv("PINTEREST_TEXT_MODE", "") or "").strip().upper()
VALID_TEXT_MODES      = {"IMAGE_ONLY", "TEXT_AND_IMAGE", "TEXT_ONLY"}

def get_text_mode(rede: str) -> str:
    specific = {
        "X": X_TEXT_MODE, "FACEBOOK": FACEBOOK_TEXT_MODE, "TELEGRAM": TELEGRAM_TEXT_MODE,
        "DISCORD": DISCORD_TEXT_MODE, "PINTEREST": PINTEREST_TEXT_MODE,
    }.get(rede, "")
    mode = (specific or GLOBAL_TEXT_MODE or "TEXT_AND_IMAGE").upper()
    return mode if mode in VALID_TEXT_MODES else "TEXT_AND_IMAGE"

# Flags
DRY_RUN               = (os.getenv("DRY_RUN","false") or "").strip().lower() == "true"
POST_X_WITH_IMAGE     = (os.getenv("POST_X_WITH_IMAGE","true") or "").strip().lower() == "true"
X_POST_IN_ALL_ACCOUNTS= (os.getenv("X_POST_IN_ALL_ACCOUNTS","true") or "").strip().lower() == "true"
POST_FB_WITH_IMAGE    = (os.getenv("POST_FB_WITH_IMAGE","true") or "").strip().lower() == "true"
POST_TG_WITH_IMAGE    = (os.getenv("POST_TG_WITH_IMAGE","true") or "").strip().lower() == "true"
POST_PINTEREST_WITH_IMAGE = (os.getenv("POST_PINTEREST_WITH_IMAGE","true") or "").strip().lower() == "true"

USE_KIT_IMAGE_FIRST   = (os.getenv("USE_KIT_IMAGE_FIRST","false") or "").strip().lower() == "true"
KIT_OUTPUT_DIR        = (os.getenv("KIT_OUTPUT_DIR","output") or "").strip()
PUBLIC_BASE_URL       = (os.getenv("PUBLIC_BASE_URL","") or "").strip()

ENABLE_KEEPALIVE      = (os.getenv("ENABLE_KEEPALIVE","false") or "").strip().lower() == "true"
KEEPALIVE_PORT        = int(os.getenv("KEEPALIVE_PORT","8080"))

MAX_PUBLICACOES_RODADA= int(os.getenv("MAX_PUBLICACOES_RODADA","30"))
PAUSA_ENTRE_POSTS     = float(os.getenv("PAUSA_ENTRE_POSTS","2.0"))

# Colunas de status (1-based)
COL_STATUS_X          = int(os.getenv("COL_STATUS_X","8"))   # H
COL_STATUS_TELEGRAM   = int(os.getenv("COL_STATUS_TELEGRAM","10")) # J
COL_STATUS_DISCORD    = int(os.getenv("COL_STATUS_DISCORD","13"))  # M
COL_STATUS_PINTEREST  = int(os.getenv("COL_STATUS_PINTEREST","14"))# N
COL_STATUS_FACEBOOK   = int(os.getenv("COL_STATUS_FACEBOOK","15")) # O

# Mapeamento por rede
COL_STATUS_REDES: Dict[str,int] = {
    "X": COL_STATUS_X,
    "TELEGRAM": COL_STATUS_TELEGRAM,
    "DISCORD": COL_STATUS_DISCORD,
    "PINTEREST": COL_STATUS_PINTEREST,
    "FACEBOOK": COL_STATUS_FACEBOOK,
}

# Colunas base (1-based)
COL_LOTERIA, COL_CONCURSO, COL_DATA, COL_NUMEROS, COL_URL = 1, 2, 3, 4, 5
COL_URL_IMAGEM, COL_IMAGEM = 6, 7  # opcionais
COL_TG_DICAS, COL_TG_PORTAL = 16, 17  # P e Q

def _detect_origem():
    if os.getenv("BOT_ORIGEM"):
        return os.getenv("BOT_ORIGEM").strip()
    if os.getenv("GITHUB_ACTIONS"): return "GitHub"
    if os.getenv("RENDER"):         return "Render"
    if os.getenv("REPL_ID") or os.getenv("REPLIT_DB_URL"): return "Replit"
    return "Local"

BOT_ORIGEM = _detect_origem()

# =========================
# LOGS e helpers
# =========================
def _now(): return dt.datetime.now(TZ)
def _ts_br(): return _now().strftime("%d/%m/%Y %H:%M")

def _log(*a):
    print(f"[{_now().strftime('%Y-%m-%d %H:%M:%S')}]",
          *a, flush=True)

def _safe_len(row, idx): return len(row) >= idx

def _clean_invisible(s: str) -> str:
    if s is None: return ""
    s = str(s)
    for ch in ["\u200B","\u200C","\u200D","\uFEFF","\u2060"]:
        s = s.replace(ch,"")
    return s.strip()

def _is_empty_status(v):
    return _clean_invisible(v) == ""

def _row_has_min_payload(row) -> bool:
    loteria = _clean_invisible(row[COL_LOTERIA  - 1]) if _safe_len(row, COL_LOTERIA)  else ""
    numeros = _clean_invisible(row[COL_NUMEROS  - 1]) if _safe_len(row, COL_NUMEROS)  else ""
    url     = _clean_invisible(row[COL_URL      - 1]) if _safe_len(row, COL_URL)      else ""
    if not (loteria and numeros and url): return False
    if not re.match(r"^https?://", url): return False
    if not re.search(r"\d", numeros):    return False
    return True

# =========================
# Google Sheets
# =========================
def _gs_client():
    sa_json = (os.getenv("GOOGLE_SERVICE_JSON","") or "").strip()
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    if sa_json:
        info = json.loads(sa_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scopes)
    else:
        path = "service_account.json"
        if not os.path.exists(path):
            raise RuntimeError("Credencial Google ausente (GOOGLE_SERVICE_JSON ou service_account.json).")
        creds = ServiceAccountCredentials.from_json_keyfile_name(path, scopes)
    return gspread.authorize(creds)

def _open_ws():
    if not SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID não definido.")
    sh = _gs_client().open_by_key(SHEET_ID)
    return sh.worksheet(SHEET_TAB)

# ===== Cofre
def _open_cofre_ws(aba):
    if not COFRE_SHEET_ID: return None
    try:
        sh = _gs_client().open_by_key(COFRE_SHEET_ID)
        return sh.worksheet(aba)
    except Exception as e:
        _log(f"[Cofre] erro ao abrir '{aba}': {e}")
        return None

def cofre_get_cred(rede: str, chave: str, conta: str = None) -> str:
    """Busca UMA credencial (Valor) no Cofre (aba Credenciais_Rede)."""
    ws = _open_cofre_ws(COFRE_ABA_CRED)
    if not ws: return ""
    vals = ws.get_all_values()
    if not vals or len(vals[0]) < 4: return ""
    rede  = (rede  or "").strip().lower()
    chave = (chave or "").strip().lower()
    conta = (conta or "").strip().lower() if conta else None
    for r in vals[1:]:
        if len(r) < 4: continue
        r_rede, r_conta, r_chave, r_valor = (r[0] or "").lower(), (r[1] or "").lower(), (r[2] or "").lower(), (r[3] or "")
        if r_rede == rede and r_chave == chave and (conta is None or r_conta == conta):
            return (r_valor or "").strip()
    return ""

def cofre_get_list(rede: str, prefixo_chave: str) -> List[str]:
    """Retorna lista ordenada por sufixo _N (1..N) para chaves com um prefixo."""
    ws = _open_cofre_ws(COFRE_ABA_CRED)
    if not ws: return []
    vals = ws.get_all_values()
    if not vals or len(vals[0]) < 4: return []
    rede  = (rede  or "").strip().lower()
    pref  = (prefixo_chave or "").strip().lower()
    bucket = {}
    for r in vals[1:]:
        if len(r) < 4: continue
        r_rede, r_chave, r_valor = (r[0] or "").lower(), (r[2] or "").lower(), (r[3] or "")
        if r_rede != rede: continue
        if not r_chave.startswith(pref): continue
        m = re.search(r"_(\d+)$", r_chave)
        idx = int(m.group(1)) if m else 1
        bucket[idx] = (r_valor or "").strip()
    return [bucket[k] for k in sorted(bucket) if bucket.get(k)]

def cofre_discover_networks() -> List[str]:
    """Detecta redes 'ativas' no Cofre (tem Valor preenchido) e já limitadas às suportadas."""
    ws = _open_cofre_ws(COFRE_ABA_CRED)
    if not ws: return []
    vals = ws.get_all_values()
    out = set()
    suportadas = {"x","facebook","telegram","discord","pinterest"}
    for r in vals[1:]:
        if len(r) < 4: continue
        rede, valor = (r[0] or "").strip().lower(), (r[3] or "").strip()
        if rede in suportadas and valor:
            out.add(rede.upper())
    return sorted(out)

def cofre_default_channels() -> Tuple[str,str]:
    """Pega 2 primeiros links Ativo=Sim na aba de canais (ordem asc.)."""
    ws = _open_cofre_ws(COFRE_ABA_CANAIS)
    if not ws:
        return ("https://t.me/portalsimonsportsdicasesportivas","https://t.me/portalsimonsports")
    vals = ws.get_all_values()
    if not vals or len(vals[0]) < 6:
        return ("https://t.me/portalsimonsportsdicasesportivas","https://t.me/portalsimonsports")
    ativos = []
    for r in vals[1:]:
        if len(r) < 6: continue
        ativo, ordem, rede, tipo, nome, url = (r[0] or "").strip().lower(), (r[1] or "").strip(), (r[2] or ""), (r[3] or ""), (r[4] or ""), (r[5] or "").strip()
        if ativo in ("sim","1","true") and url:
            try: ordem = int(ordem)
            except: ordem = 999999
            ativos.append((ordem, url))
    ativos.sort(key=lambda x: x[0])
    if len(ativos) == 0:
        return ("https://t.me/portalsimonsportsdicasesportivas","https://t.me/portalsimonsports")
    if len(ativos) == 1:
        return (ativos[0][1], "https://t.me/portalsimonsports")
    return (ativos[0][1], ativos[1][1])

# =========================
# Marcação de publicação
# =========================
def marcar_publicado(ws, rownum, rede, value=None):
    col = COL_STATUS_REDES.get(rede, None)
    if not col: return
    value = value or f"Publicado {rede} via {BOT_ORIGEM} em {_ts_br()}"
    ws.update_cell(rownum, col, value)

# =========================
# Slug helpers (KIT)
# =========================
_LOTERIA_SLUGS = {
    "mega-sena":"mega-sena","quina":"quina","lotofacil":"lotofacil","lotofácil":"lotofacil",
    "lotomania":"lotomania","timemania":"timemania","dupla sena":"dupla-sena","dupla-sena":"dupla-sena",
    "federal":"federal","loteria federal":"federal","dia de sorte":"dia-de-sorte","dia-de-sorte":"dia-de-sorte",
    "super sete":"super-sete","super-sete":"super-sete","loteca":"loteca","+milionaria":"mais-milionaria",
    "mais milionaria":"mais-milionaria","mais milionária":"mais-milionaria","mais-milionaria":"mais-milionaria"
}

def _slugify(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[áàâãä]","a",s); s = re.sub(r"[éèêë]","e",s)
    s = re.sub(r"[íìîï]","i",s); s = re.sub(r"[óòôõö]","o",s)
    s = re.sub(r"[úùûü]","u",s); s = re.sub(r"[ç]","c",s)
    s = re.sub(r"[^a-z0-9 \-]+","",s).strip()   # hífen no fim do colchete = seguro
    s = re.sub(r"\s+","-",s)
    return s

def _guess_slug(name: str) -> str:
    p = (name or "").lower()
    for k, v in _LOTERIA_SLUGS.items():
        if k in p: return v
    return _slugify(name or "loteria")

# =========================
# IMAGEM: tenta KIT, senão oficial
# =========================
def _try_load_kit_image(row):
    if not USE_KIT_IMAGE_FIRST: return None
    try:
        loteria  = row[COL_LOTERIA - 1] if _safe_len(row, COL_LOTERIA) else ""
        concurso = row[COL_CONCURSO - 1] if _safe_len(row, COL_CONCURSO) else ""
        data_br  = row[COL_DATA - 1]     if _safe_len(row, COL_DATA)     else ""
        slug = _guess_slug(loteria)

        patterns = []
        if concurso:
            patterns.append(os.path.join(KIT_OUTPUT_DIR, f"*{slug}*{_slugify(concurso)}*.jp*g"))
            patterns.append(os.path.join(KIT_OUTPUT_DIR, f"{slug}-{_slugify(concurso)}*.jp*g"))
        if data_br:
            patterns.append(os.path.join(KIT_OUTPUT_DIR, f"*{slug}*{_slugify(data_br)}*.jp*g"))
        patterns.append(os.path.join(KIT_OUTPUT_DIR, f"{slug}*.jp*g"))

        for pat in patterns:
            files = sorted(glob.glob(pat))
            if files:
                path = files[0]
                with open(path, "rb") as f:
                    buf = io.BytesIO(f.read()); buf.seek(0)
                    return buf
        return None
    except Exception as e:
        _log(f"[KIT] erro ao tentar carregar imagem: {e}")
        return None

def _build_image_from_row(row):
    buf = _try_load_kit_image(row)
    if buf: return buf  # JPG/PNG do KIT
    loteria  = row[COL_LOTERIA  - 1] if _safe_len(row, COL_LOTERIA)  else "Loteria"
    concurso = row[COL_CONCURSO - 1] if _safe_len(row, COL_CONCURSO) else "0000"
    data_br  = row[COL_DATA     - 1] if _safe_len(row, COL_DATA)     else _now().strftime("%d/%m/%Y")
    numeros  = row[COL_NUMEROS  - 1] if _safe_len(row, COL_NUMEROS)  else ""
    url_res  = row[COL_URL      - 1] if _safe_len(row, COL_URL)      else ""
    return gerar_imagem_loteria(str(loteria), str(concurso), str(data_br), str(numeros), str(url_res))

# =========================
# Texto único aprovado
# =========================
def montar_texto_base(row) -> str:
    url    = (row[COL_URL - 1]       if _safe_len(row, COL_URL)       else "").strip()
    dicas_plan  = (row[COL_TG_DICAS  - 1] if _safe_len(row, COL_TG_DICAS)  else "").strip()
    portal_plan = (row[COL_TG_PORTAL - 1] if _safe_len(row, COL_TG_PORTAL) else "").strip()
    if not (dicas_plan and portal_plan):
        d1, d2 = cofre_default_channels()
        dicas  = dicas_plan  or d1
        portal = portal_plan or d2
    else:
        dicas, portal = dicas_plan, portal_plan

    txt = (
        "Resultado completo aqui >>>>\n"
        f"{url}\n\n"
        "Palpites quentes AGORA\n"
        "Inscreva-se :\n"
        f"{dicas}\n\n"
        "Todas as notícias do portal\n"
        "Inscreva-se :\n"
        f"{portal}"
    ).strip()

    # Segurança para X
    if len(txt) > 275:
        txt = txt[:275]
    return txt

# =========================
# Coleta de candidatas (por rede)
# =========================
def coleta_candidatos_para(ws, rede: str):
    linhas = ws.get_all_values()
    if len(linhas) <= 1:
        _log(f"[{rede}] Planilha sem dados.")
        return []
    data = linhas[1:]
    cand = []
    col_status = COL_STATUS_REDES.get(rede)
    if not col_status:
        _log(f"[{rede}] Coluna de status não definida.")
        return []

    total = len(data)
    vazios = preenchidas = ignoradas_sem_payload = 0

    for rindex, row in enumerate(data, start=2):
        status_val = row[col_status - 1] if len(row) >= col_status else ""
        if not _is_empty_status(status_val):
            preenchidas += 1
            continue

        if not _row_has_min_payload(row):
            ignoradas_sem_payload += 1
            continue

        cand.append((rindex, row))
        vazios += 1

    _log(f"[{rede}] Candidatas: {vazios}/{total} | status preenchido: {preenchidas} | sem payload: {ignoradas_sem_payload}")
    return cand

# =========================
# CREDENCIAIS (ENV -> Cofre)
# =========================
TW1 = {
    "api_key":      (os.getenv("TWITTER_API_KEY_1","").strip() or cofre_get_cred("x","twitter_api_key_1")),
    "api_secret":   (os.getenv("TWITTER_API_SECRET_1","").strip() or cofre_get_cred("x","twitter_api_secret_1")),
    "access_token": (os.getenv("TWITTER_ACCESS_TOKEN_1","").strip() or cofre_get_cred("x","twitter_access_token_1")),
    "access_secret":(os.getenv("TWITTER_ACCESS_SECRET_1","").strip() or cofre_get_cred("x","twitter_access_secret_1")),
}
TW2 = {
    "api_key":      (os.getenv("TWITTER_API_KEY_2","").strip() or cofre_get_cred("x","twitter_api_key_2")),
    "api_secret":   (os.getenv("TWITTER_API_SECRET_2","").strip() or cofre_get_cred("x","twitter_api_secret_2")),
    "access_token": (os.getenv("TWITTER_ACCESS_TOKEN_2","").strip() or cofre_get_cred("x","twitter_access_token_2")),
    "access_secret":(os.getenv("TWITTER_ACCESS_SECRET_2","").strip() or cofre_get_cred("x","twitter_access_secret_2")),
}

class XAccount:
    def __init__(self, label, api_key, api_secret, access_token, access_secret):
        self.label = label
        self.client_v2 = tweepy.Client(
            consumer_key=api_key, consumer_secret=api_secret,
            access_token=access_token, access_token_secret=access_secret
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
    def ok(d): return all(d.get(k) for k in ("api_key","api_secret","access_token","access_secret"))
    if ok(TW1): accs.append(XAccount("ACC1", **TW1))
    if ok(TW2): accs.append(XAccount("ACC2", **TW2))
    if not accs: raise RuntimeError("Nenhuma conta X configurada (ENV ou Cofre).")
    return accs

_recent_tweets_cache: Dict[str,set] = {}
_postados_nesta_execucao: Dict[str,set] = {}

def x_load_recent_texts(acc: XAccount, max_results=50):
    try:
        resp = acc.client_v2.get_users_tweets(
            id=acc.user_id, max_results=min(max_results,100), tweet_fields=["text"]
        )
        out = set()
        if resp and resp.data:
            for tw in resp.data:
                t = (tw.text or "").strip()
                if t: out.add(t)
        _recent_tweets_cache[acc.label] = set(list(out)[-50:])
        return _recent_tweets_cache[acc.label]
    except Exception as e:
        _log(f"[{acc.handle}] warning: falha ao ler tweets recentes: {e}")
        return set()

def x_is_dup(acc: XAccount, text: str) -> bool:
    t = (text or "").strip()
    if not t: return False
    return (t in _recent_tweets_cache.get(acc.label,set())) or (t in _postados_nesta_execucao.get(acc.label,set()))

def x_upload_media_if_any(acc: XAccount, row):
    if not POST_X_WITH_IMAGE or DRY_RUN: return None
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
        _log(f"[X] Conta conectada: {acc.handle}")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode_cfg = get_text_mode("X")

    for rownum, row in candidatos[:limite]:
        if not _row_has_min_payload(row):
            _log(f"[X] L{rownum} ignorada: payload insuficiente.")
            continue

        texto_full = montar_texto_base(row)
        texto_para_postar = "" if mode_cfg == "IMAGE_ONLY" else texto_full

        ok_all = True
        if X_POST_IN_ALL_ACCOUNTS:
            for acc in contas:
                media_ids = x_upload_media_if_any(acc, row)
                ok = False
                try:
                    if DRY_RUN:
                        _log(f"[X][{acc.handle}] DRY_RUN — sem envio."); ok = True
                    else:
                        if texto_para_postar and x_is_dup(acc, texto_para_postar):
                            _log(f"[X][{acc.handle}] SKIP duplicado."); ok = True
                        else:
                            resp = acc.client_v2.create_tweet(
                                text=(texto_para_postar or None) if mode_cfg != "IMAGE_ONLY" else None,
                                media_ids=media_ids if POST_X_WITH_IMAGE else None,
                            )
                            _log(f"[X][{acc.handle}] OK → {resp.data['id']}")
                            if texto_para_postar:
                                _postados_nesta_execucao.setdefault(acc.label,set()).add(texto_para_postar)
                                _recent_tweets_cache.setdefault(acc.label,set()).add(texto_para_postar)
                            ok = True
                except Exception as e:
                    _log(f"[X][{acc.handle}] erro: {e}"); ok = False
                ok_all = ok_all and ok
                time.sleep(0.7)
        else:
            acc = contas[0]
            media_ids = x_upload_media_if_any(acc, row)
            ok = False
            try:
                if DRY_RUN:
                    _log(f"[X][{acc.handle}] DRY_RUN — sem envio."); ok = True
                else:
                    if texto_para_postar and x_is_dup(acc, texto_para_postar):
                        _log(f"[X][{acc.handle}] SKIP duplicado."); ok = True
                    else:
                        resp = acc.client_v2.create_tweet(
                            text=(texto_para_postar or None) if mode_cfg != "IMAGE_ONLY" else None,
                            media_ids=media_ids if POST_X_WITH_IMAGE else None,
                        )
                        _log(f"[X][{acc.handle}] OK → {resp.data['id']}")
                        if texto_para_postar:
                            _postados_nesta_execucao.setdefault(acc.label,set()).add(texto_para_postar)
                            _recent_tweets_cache.setdefault(acc.label,set()).add(texto_para_postar)
                        ok = True
            except Exception as e:
                _log(f"[X][{acc.handle}] erro: {e}"); ok = False
            ok_all = ok_all and ok

        if ok_all and not DRY_RUN:
            marcar_publicado(ws, rownum, "X")
            publicados += 1
        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[X] Publicados: {publicados}")
    return publicados

# -------------------------
# Facebook
# -------------------------
def _fb_post_text(page_id, page_token, message: str, link: Optional[str] = None):
    url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
    data = {"message": message, "access_token": page_token}
    if link: data["link"] = link
    r = requests.post(url, data=data, timeout=25); r.raise_for_status()
    return r.json().get("id")

def _fb_post_photo(page_id, page_token, caption: str, image_bytes: bytes):
    url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
    files = {"source": ("resultado.png", image_bytes, "image/png")}
    data  = {"caption": caption, "published": "true", "access_token": page_token}
    r = requests.post(url, data=data, files=files, timeout=40); r.raise_for_status()
    return r.json().get("id")

def publicar_em_facebook(ws, candidatos):
    fb_ids_env = (os.getenv("FB_PAGE_IDS","") or "").strip()
    fb_tks_env = (os.getenv("FB_PAGE_TOKENS","") or "").strip()
    FB_PAGE_IDS = [s.strip() for s in fb_ids_env.split(",") if s.strip()] or cofre_get_list("facebook","page_id_")
    FB_PAGE_TOKENS = [s.strip() for s in fb_tks_env.split(",") if s.strip()] or cofre_get_list("facebook","page_token_")
    if not FB_PAGE_IDS:    FB_PAGE_IDS    = cofre_get_list("facebook","app_id_")
    if not FB_PAGE_TOKENS: FB_PAGE_TOKENS = cofre_get_list("facebook","token_de_acesso_")

    if not FB_PAGE_IDS or not FB_PAGE_TOKENS or len(FB_PAGE_IDS) != len(FB_PAGE_TOKENS):
        raise RuntimeError("Facebook: configure FB_PAGE_IDS/FB_PAGE_TOKENS (ENV) ou PAGE_ID_/PAGE_TOKEN_ (Cofre).")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("FACEBOOK")

    for rownum, row in candidatos[:limite]:
        if not _row_has_min_payload(row):
            _log(f"[Facebook] L{rownum} ignorada: payload insuficiente."); continue

        base = montar_texto_base(row)
        msg = "" if mode == "IMAGE_ONLY" else base
        ok_any = False

        for pid, ptoken in zip(FB_PAGE_IDS, FB_PAGE_TOKENS):
            try:
                if DRY_RUN:
                    _log(f"[Facebook][{pid}] DRY_RUN."); ok = True
                else:
                    if POST_FB_WITH_IMAGE:
                        buf = _build_image_from_row(row)
                        fb_id = _fb_post_photo(pid, ptoken, msg, buf.getvalue())
                    else:
                        url_post = (row[COL_URL - 1] if _safe_len(row, COL_URL) else "").strip()
                        fb_id = _fb_post_text(pid, ptoken, msg, link=url_post or None)
                    _log(f"[Facebook][{pid}] OK → {fb_id}"); ok = True
            except Exception as e:
                _log(f"[Facebook][{pid}] erro: {e}"); ok = False
            ok_any = ok_any or ok
            time.sleep(0.7)

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "FACEBOOK")
            publicados += 1
        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Facebook] Publicados: {publicados}")
    return publicados

# -------------------------
# Telegram
# -------------------------
def _tg_send_photo(token, chat_id, caption, image_bytes):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    files = {"photo": ("resultado.png", image_bytes, "image/png")}
    data = {"chat_id": chat_id, "caption": caption}
    r = requests.post(url, data=data, files=files, timeout=40); r.raise_for_status()
    return r.json().get("result", {}).get("message_id")

def _tg_send_text(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": False}
    r = requests.post(url, data=data, timeout=25); r.raise_for_status()
    return r.json().get("result", {}).get("message_id")

def publicar_em_telegram(ws, candidatos):
    TG_BOT_TOKEN = (os.getenv("TG_BOT_TOKEN","").strip() or
                    cofre_get_cred("telegram","tg_bot_token") or
                    cofre_get_cred("telegram","bot_token"))
    ids_env = (os.getenv("TG_CHAT_IDS","") or "").strip()
    TG_CHAT_IDS = [s.strip() for s in ids_env.split(",") if s.strip()] or cofre_get_list("telegram","chat_id_")
    if not TG_BOT_TOKEN or not TG_CHAT_IDS:
        raise RuntimeError("Telegram: configure TG_BOT_TOKEN/TG_CHAT_IDS (ENV) ou BOT_TOKEN/CHAT_ID_# (Cofre).")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("TELEGRAM")

    for rownum, row in candidatos[:limite]:
        if not _row_has_min_payload(row):
            _log(f"[Telegram] L{rownum} ignorada: payload insuficiente."); continue

        base = montar_texto_base(row)
        msg = "" if mode == "IMAGE_ONLY" else base
        ok_any = False

        for chat_id in TG_CHAT_IDS:
            try:
                if DRY_RUN:
                    _log(f"[Telegram][{chat_id}] DRY_RUN."); ok = True
                else:
                    if POST_TG_WITH_IMAGE:
                        buf = _build_image_from_row(row)
                        msg_id = _tg_send_photo(TG_BOT_TOKEN, chat_id, msg, buf.getvalue())
                    else:
                        final_msg = msg
                        url_post = (row[COL_URL - 1] if _safe_len(row, COL_URL) else "").strip()
                        if url_post and final_msg: final_msg = f"{final_msg}\n{url_post}"
                        elif url_post and not final_msg: final_msg = url_post
                        msg_id = _tg_send_text(TG_BOT_TOKEN, chat_id, final_msg or "")
                    _log(f"[Telegram][{chat_id}] OK → {msg_id}"); ok = True
            except Exception as e:
                _log(f"[Telegram][{chat_id}] erro: {e}"); ok = False

            ok_any = ok_any or ok
            time.sleep(0.5)

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "TELEGRAM")
            publicados += 1
        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Telegram] Publicados: {publicados}")
    return publicados

# -------------------------
# Discord
# -------------------------
def _discord_send(webhook_url, content=None, image_bytes=None):
    data = {"content": content or ""}
    files = {"file": ("resultado.png", image_bytes, "image/png")} if image_bytes else None
    r = requests.post(webhook_url, data=data, files=files, timeout=30); r.raise_for_status()
    return True

def publicar_em_discord(ws, candidatos):
    discord_env = (os.getenv("DISCORD_WEBHOOKS","") or "").strip()
    DISCORD_WEBHOOKS = [s.strip() for s in (discord_env.split(",") if discord_env else cofre_get_list("discord","webhook_")) if s.strip()]
    if not DISCORD_WEBHOOKS:
        raise RuntimeError("Discord: defina DISCORD_WEBHOOKS (ENV) ou WEBHOOK_# (Cofre).")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("DISCORD")

    for rownum, row in candidatos[:limite]:
        if not _row_has_min_payload(row):
            _log(f"[Discord] L{rownum} ignorada: payload insuficiente."); continue

        base = montar_texto_base(row)
        msg = "" if mode == "IMAGE_ONLY" else base
        ok_any = False

        try:
            if DRY_RUN:
                for wh in DISCORD_WEBHOOKS:
                    _log(f"[Discord] DRY_RUN → {wh[-18:]}"); 
                ok_any = True
            else:
                buf = _build_image_from_row(row)
                img_bytes = buf.getvalue()
                for wh in DISCORD_WEBHOOKS:
                    payload = msg
                    url_post = (row[COL_URL - 1] if _safe_len(row, COL_URL) else "").strip()
                    if url_post and payload: payload = f"{payload}\n{url_post}"
                    elif url_post and not payload: payload = url_post
                    _discord_send(wh, content=(payload or None), image_bytes=img_bytes)
                    _log(f"[Discord] OK → {wh[-18:]}")
                ok_any = True
        except Exception as e:
            _log(f"[Discord] erro: {e}"); ok_any = False

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "DISCORD")
            publicados += 1
        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Discord] Publicados: {publicados}")
    return publicados

# -------------------------
# Pinterest (API v5)
# -------------------------
def _pinterest_create_pin(token: str, board_id: str, title: str, description: str,
                          link: Optional[str], image_bytes: Optional[bytes] = None,
                          image_url: Optional[str] = None):
    url = "https://api.pinterest.com/v5/pins"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"board_id": board_id, "title": title[:100], "description": (description or "")[:500]}
    if link: payload["link"] = link

    if image_bytes is not None:
        payload["media_source"] = {
            "source_type": "image_base64",
            "content_type": "image/png",
            "data": base64.b64encode(image_bytes).decode("utf-8"),
        }
    elif image_url:
        payload["media_source"] = {"source_type": "image_url", "url": image_url}
    else:
        raise ValueError("Pinterest: informe image_bytes ou image_url.")

    r = requests.post(url, headers=headers, json=payload, timeout=40); r.raise_for_status()
    return r.json().get("id")

def publicar_em_pinterest(ws, candidatos):
    token = (os.getenv("PINTEREST_ACCESS_TOKEN","").strip() or cofre_get_cred("pinterest","access_token"))
    board = (os.getenv("PINTEREST_BOARD_ID","").strip() or cofre_get_cred("pinterest","board_id"))
    if not (token and board):
        raise RuntimeError("Pinterest: defina PINTEREST_ACCESS_TOKEN/PINTEREST_BOARD_ID (ENV) ou ACCESS_TOKEN/BOARD_ID (Cofre).")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("PINTEREST")

    for rownum, row in candidatos[:limite]:
        if not _row_has_min_payload(row):
            _log(f"[Pinterest] L{rownum} ignorada: payload insuficiente."); continue

        loteria  = row[COL_LOTERIA  - 1] if _safe_len(row, COL_LOTERIA)  else "Loteria"
        concurso = row[COL_CONCURSO - 1] if _safe_len(row, COL_CONCURSO) else "0000"
        title = f"{loteria} — Concurso {concurso}"
        desc_full = montar_texto_base(row)
        desc = "" if mode == "IMAGE_ONLY" else desc_full
        url_post = (row[COL_URL - 1] if _safe_len(row, COL_URL) else "").strip()

        try:
            if DRY_RUN:
                _log(f"[Pinterest] DRY_RUN — {title}"); ok = True
            else:
                if POST_PINTEREST_WITH_IMAGE:
                    buf = _build_image_from_row(row)
                    pin_id = _pinterest_create_pin(token, board, title, desc, url_post, image_bytes=buf.getvalue(), image_url=None)
                else:
                    # Fallback por URL (não recomendado, mas disponível)
                    pin_id = _pinterest_create_pin(token, board, title, desc, url_post, image_bytes=None, image_url=url_post or None)
                _log(f"[Pinterest] OK → {pin_id}"); ok = True
        except Exception as e:
            _log(f"[Pinterest] erro: {e}"); ok = False

        if ok and not DRY_RUN:
            marcar_publicado(ws, rownum, "PINTEREST")
            publicados += 1
        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[Pinterest] Publicados: {publicados}")
    return publicados

# =========================
# Keepalive (opcional)
# =========================
def iniciar_keepalive():
    try:
        from flask import Flask
    except ImportError:
        _log("Flask não instalado; keepalive desativado."); return None

    app = Flask(__name__)

    @app.route("/")
    def raiz():
        return "ok", 200

    @app.route("/ping")
    def ping():
        return "ok", 200

    def run():
        port = int(os.getenv("PORT", KEEPALIVE_PORT))
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    th = Thread(target=run, daemon=True); th.start()
    _log(f"Keepalive Flask ativo em 0.0.0.0:{os.getenv('PORT', KEEPALIVE_PORT)}")
    return th

# =========================
# MAIN
# =========================
def main():
    # Se houver Cofre, as redes ativas de lá sobrepõem TARGET_NETWORKS
    redes = cofre_discover_networks() if COFRE_SHEET_ID else []
    if redes: redes = [r for r in redes if r in COL_STATUS_REDES]
    if not redes:
        redes = [r for r in TARGET_NETWORKS if r in COL_STATUS_REDES]

    _log("Iniciando bot...",
         f"Origem={BOT_ORIGEM} | Redes={','.join(redes) or '-'} | DRY_RUN={DRY_RUN} | "
         f"GLOBAL_TEXT_MODE={(GLOBAL_TEXT_MODE or 'TEXT_AND_IMAGE')} | KIT_FIRST={USE_KIT_IMAGE_FIRST}")

    keepalive_thread = iniciar_keepalive() if ENABLE_KEEPALIVE else None

    try:
        ws = _open_ws()
        if not redes:
            _log("Nenhuma rede alvo."); return

        for rede in redes:
            candidatos = coleta_candidatos_para(ws, rede)
            if not candidatos:
                _log(f"[{rede}] Nenhuma candidata."); continue

            if rede == "X":
                publicar_em_x(ws, candidatos)
            elif rede == "FACEBOOK":
                publicar_em_facebook(ws, candidatos)
            elif rede == "TELEGRAM":
                publicar_em_telegram(ws, candidatos)
            elif rede == "DISCORD":
                publicar_em_discord(ws, candidatos)
            elif rede == "PINTEREST":
                publicar_em_pinterest(ws, candidatos)
            else:
                _log(f"[{rede}] Rede não suportada.")

        _log("Concluído.")
    except KeyboardInterrupt:
        _log("Interrompido pelo usuário.")
    except Exception as e:
        _log(f"[FATAL] {e}")
        raise
    finally:
        if ENABLE_KEEPALIVE and keepalive_thread:
            time.sleep(1)

if __name__ == "__main__":
    main()