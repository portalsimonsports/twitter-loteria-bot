# bot.py — Portal SimonSports — Publicador Automático (X, Facebook, Telegram, Discord, Pinterest)
# Rev: 2025-11-18 — SEM FILTRO DE DATA + LIMPEZA DE CARACTERES INVISÍVEIS NA COLUNA DE STATUS
#                  + TEXTO = LINK DO RESULTADO + CTA + REDES SOCIAIS
#
# Planilha: ImportadosBlogger2
# Colunas: A=Loteria B=Concurso C=Data D=Números E=URL
# Status por rede (padrões): H=8 (X), M=13 (Discord), N=14 (Pinterest), O=15 (Facebook), J=10 (Telegram)
#
# Regras de publicação:
# - PUBLICA SEMPRE que a coluna da REDE alvo estiver VAZIA (após remover espaços e caracteres invisíveis)
# - NÃO olha coluna de “Enfileirado”
# - NÃO restringe por data / horário (BACKLOG_DAYS ignorado)
# - Texto padrão da publicação:
#     🔗 Resultado completo aqui: <URL>
#
#     📲 Siga o Portal SimonSports:
#     X: <link>
#     Telegram: <link>
#     Facebook: <link>
#     Instagram: <link>
#     YouTube: <link>
#
#   -> Para mandar só a imagem, use GLOBAL_TEXT_MODE=IMAGE_ONLY no .env

import os
import re
import io
import glob
import json
import time
import base64
import pytz
import tweepy
import requests
import datetime as dt
from threading import Thread
from collections import defaultdict
from dotenv import load_dotenv

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Imagem oficial (padrão aprovado)
from app.imaging import gerar_imagem_loteria

# =========================
# CONFIG / ENV
# =========================

load_dotenv()
TZ = pytz.timezone("America/Sao_Paulo")

SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
SHEET_TAB = os.getenv("SHEET_TAB", "ImportadosBlogger2").strip()

# Redes alvo (X, FACEBOOK, TELEGRAM, DISCORD, PINTEREST)
TARGET_NETWORKS = [
    s.strip().upper()
    for s in os.getenv("TARGET_NETWORKS", "X").split(",")
    if s.strip()
]

# BACKLOG_DAYS agora é ignorado, mas deixei leitura para não quebrar .env
BACKLOG_DAYS = int(os.getenv("BACKLOG_DAYS", "7"))
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() == "true"

# ===== Modo de TEXTO (GLOBAL e por rede) =====

GLOBAL_TEXT_MODE = (os.getenv("GLOBAL_TEXT_MODE", "") or "").strip().upper()  # opcional

# por rede (se vazio, herda do GLOBAL ou usa TEXT_AND_IMAGE como default)
X_TEXT_MODE = (os.getenv("X_TEXT_MODE", "") or "").strip().upper()
FACEBOOK_TEXT_MODE = (os.getenv("FACEBOOK_TEXT_MODE", "") or "").strip().upper()
TELEGRAM_TEXT_MODE = (os.getenv("TELEGRAM_TEXT_MODE", "") or "").strip().upper()
DISCORD_TEXT_MODE = (os.getenv("DISCORD_TEXT_MODE", "") or "").strip().upper()
PINTEREST_TEXT_MODE = (os.getenv("PINTEREST_TEXT_MODE", "") or "").strip().upper()

VALID_TEXT_MODES = {"IMAGE_ONLY", "TEXT_AND_IMAGE", "TEXT_ONLY"}


def get_text_mode(rede: str) -> str:
    """
    Prioridade: modo específico da rede -> GLOBAL_TEXT_MODE -> 'TEXT_AND_IMAGE'
    """
    specific = {
        "X": X_TEXT_MODE,
        "FACEBOOK": FACEBOOK_TEXT_MODE,
        "TELEGRAM": TELEGRAM_TEXT_MODE,
        "DISCORD": DISCORD_TEXT_MODE,
        "PINTEREST": PINTEREST_TEXT_MODE,
    }.get(rede, "")

    mode = (specific or GLOBAL_TEXT_MODE or "TEXT_AND_IMAGE").upper()
    return mode if mode in VALID_TEXT_MODES else "TEXT_AND_IMAGE"


# ===== X (Twitter) =====

X_POST_IN_ALL_ACCOUNTS = os.getenv("X_POST_IN_ALL_ACCOUNTS", "true").strip().lower() == "true"
POST_X_WITH_IMAGE = os.getenv("POST_X_WITH_IMAGE", "true").strip().lower() == "true"
COL_STATUS_X = int(os.getenv("COL_STATUS_X", "8"))  # H

# ===== Facebook (Páginas) =====

POST_FB_WITH_IMAGE = os.getenv("POST_FB_WITH_IMAGE", "true").strip().lower() == "true"
COL_STATUS_FACEBOOK = int(os.getenv("COL_STATUS_FACEBOOK", "15"))  # O
FB_PAGE_IDS = [
    s.strip()
    for s in os.getenv("FB_PAGE_IDS", os.getenv("FB_PAGE_ID", "")).split(",")
    if s.strip()
]
FB_PAGE_TOKENS = [
    s.strip()
    for s in os.getenv("FB_PAGE_TOKENS", os.getenv("FB_PAGE_TOKEN", "")).split(",")
    if s.strip()
]

# ===== Telegram =====

POST_TG_WITH_IMAGE = os.getenv("POST_TG_WITH_IMAGE", "true").strip().lower() == "true"
COL_STATUS_TELEGRAM = int(os.getenv("COL_STATUS_TELEGRAM", "10"))  # J
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
TG_CHAT_IDS = [s.strip() for s in os.getenv("TG_CHAT_IDS", "").split(",") if s.strip()]

# ===== Discord =====

COL_STATUS_DISCORD = int(os.getenv("COL_STATUS_DISCORD", "13"))  # M
DISCORD_WEBHOOKS = [s.strip() for s in os.getenv("DISCORD_WEBHOOKS", "").split(",") if s.strip()]

# ===== Pinterest =====

COL_STATUS_PINTEREST = int(os.getenv("COL_STATUS_PINTEREST", "14"))  # N
PINTEREST_ACCESS_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "").strip()
PINTEREST_BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "").strip()
POST_PINTEREST_WITH_IMAGE = os.getenv("POST_PINTEREST_WITH_IMAGE", "true").strip().lower() == "true"

# ===== KIT (HTML/CSS) /output =====

USE_KIT_IMAGE_FIRST = os.getenv("USE_KIT_IMAGE_FIRST", "false").strip().lower() == "true"
KIT_OUTPUT_DIR = os.getenv("KIT_OUTPUT_DIR", "output").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()  # (reservado para futuro uso se precisar)

# ===== Keepalive (Replit/Render) =====

ENABLE_KEEPALIVE = os.getenv("ENABLE_KEEPALIVE", "false").strip().lower() == "true"
KEEPALIVE_PORT = int(os.getenv("KEEPALIVE_PORT", "8080"))

# Limites

MAX_PUBLICACOES_RODADA = int(os.getenv("MAX_PUBLICACOES_RODADA", "30"))
PAUSA_ENTRE_POSTS = float(os.getenv("PAUSA_ENTRE_POSTS", "2.0"))


def _detect_origem():
    if os.getenv("BOT_ORIGEM"):
        return os.getenv("BOT_ORIGEM").strip()
    if os.getenv("GITHUB_ACTIONS"):
        return "GitHub"
    if os.getenv("REPL_ID") or os.getenv("REPLIT_DB_URL"):
        return "Replit"
    if os.getenv("RENDER"):
        return "Render"
    return "Local"


BOT_ORIGEM = _detect_origem()

# =========================
# Planilha — colunas (1-based)
# =========================

COL_Loteria, COL_Concurso, COL_Data, COL_Numeros, COL_URL = 1, 2, 3, 4, 5
COL_URL_Imagem, COL_Imagem = 6, 7  # opcionais (não obrigatórios)

COL_STATUS_REDES = {
    "X": COL_STATUS_X,                  # H
    "FACEBOOK": COL_STATUS_FACEBOOK,    # O
    "TELEGRAM": COL_STATUS_TELEGRAM,    # J
    "DISCORD": COL_STATUS_DISCORD,      # M
    "PINTEREST": COL_STATUS_PINTEREST,  # N
}

# =========================
# Utilitários
# =========================


def _not_empty(v):
    return bool(str(v or "").strip())


def _is_empty_status(v):
    """
    Considera a célula VAZIA mesmo se tiver espaços ou caracteres invisíveis
    comuns (zero width, BOM, etc).
    Usado para decidir se a coluna de status está realmente vazia.
    """
    if v is None:
        return True

    s = str(v)
    # limpa espaços normais nas pontas
    s = s.strip()
    # remove caracteres invisíveis mais comuns
    invisiveis = ["\u200B", "\u200C", "\u200D", "\uFEFF", "\u2060"]
    for ch in invisiveis:
        s = s.replace(ch, "")

    return s == ""


def _now():
    return dt.datetime.now(TZ)


def _ts():
    return _now().strftime("%Y-%m-%d %H:%M:%S")


def _ts_br():
    return _now().strftime("%d/%m/%Y %H:%M")


def _safe_len(row, idx):
    return len(row) >= idx


def _log(*a):
    print(f"[{_ts()}]", *a, flush=True)


# =========================
# Google Sheets
# =========================


def _gs_client():
    sa_json = os.getenv("GOOGLE_SERVICE_JSON", "").strip()
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
            raise RuntimeError(
                "Credencial Google ausente (defina GOOGLE_SERVICE_JSON ou service_account.json)"
            )
        creds = ServiceAccountCredentials.from_json_keyfile_name(path, scopes)

    return gspread.authorize(creds)


def _open_ws():
    if not SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID não definido.")
    sh = _gs_client().open_by_key(SHEET_ID)
    return sh.worksheet(SHEET_TAB)


def marcar_publicado(ws, rownum, rede, value=None):
    col = COL_STATUS_REDES.get(rede, None)
    if not col:
        return
    valor = value or f"Publicado {rede} via {BOT_ORIGEM} em {_ts_br()}"
    ws.update_cell(rownum, col, valor)


# =========================
# Slug helpers (KIT)
# =========================

_LOTERIA_SLUGS = {
    "mega-sena": "mega-sena",
    "quina": "quina",
    "lotofacil": "lotofacil",
    "lotofácil": "lotofacil",
    "lotomania": "lotomania",
    "timemania": "timemania",
    "dupla sena": "dupla-sena",
    "dupla-sena": "dupla-sena",
    "federal": "federal",
    "dia de sorte": "dia-de-sorte",
    "dia-de-sorte": "dia-de-sorte",
    "super sete": "super-sete",
    "super-sete": "super-sete",
    "loteca": "loteca",
}


def _slugify(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[áàâãä]", "a", s)
    s = re.sub(r"[éèêë]", "e", s)
    s = re.sub(r"[íìîï]", "i", s)
    s = re.sub(r"[óòôõö]", "o", s)
    s = re.sub(r"[úùûü]", "u", s)
    s = re.sub(r"ç", "c", s)
    s = re.sub(r"[^a-z0-9- ]+", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s


def _guess_slug(name: str) -> str:
    p = (name or "").lower()
    for k, v in _LOTERIA_SLUGS.items():
        if k in p:
            return v
    return _slugify(name or "loteria")


# =========================
# IMAGEM: KIT /output -> oficial imaging.py
# =========================


def _try_load_kit_image(row):
    """
    Se USE_KIT_IMAGE_FIRST, tenta localizar arquivo no KIT_OUTPUT_DIR usando slug e concurso/data.
    Retorna BytesIO ou None.
    """
    if not USE_KIT_IMAGE_FIRST:
        return None

    try:
        loteria = row[COL_Loteria - 1] if _safe_len(row, COL_Loteria) else ""
        concurso = row[COL_Concurso - 1] if _safe_len(row, COL_Concurso) else ""
        data_br = row[COL_Data - 1] if _safe_len(row, COL_Data) else ""
        slug = _guess_slug(loteria)

        patterns = []

        if concurso:
            patterns.append(
                os.path.join(KIT_OUTPUT_DIR, f"*{slug}*{_slugify(concurso)}*.jp*g")
            )
            patterns.append(
                os.path.join(KIT_OUTPUT_DIR, f"{slug}-{_slugify(concurso)}*.jp*g")
            )

        if data_br:
            patterns.append(
                os.path.join(KIT_OUTPUT_DIR, f"*{slug}*{_slugify(data_br)}*.jp*g")
            )

        # fallback genérico por slug
        patterns.append(os.path.join(KIT_OUTPUT_DIR, f"{slug}*.jp*g"))

        for pat in patterns:
            files = sorted(glob.glob(pat))
            if files:
                path = files[0]
                with open(path, "rb") as f:
                    buf = io.BytesIO(f.read())
                    buf.seek(0)
                    return buf

        return None
    except Exception as e:
        _log(f"[KIT] erro ao tentar carregar imagem: {e}")
        return None


def _build_image_from_row(row):
    """
    Retorna BytesIO (PNG ou JPG).
    Prioriza KIT /output (se habilitado); se não encontrar, gera imagem oficial via gerar_imagem_loteria.
    """
    buf = _try_load_kit_image(row)
    if buf:
        return buf  # JPG/PNG do KIT

    # Gera imagem oficial (PNG) via Pillow / imaging.py
    loteria = row[COL_Loteria - 1] if _safe_len(row, COL_Loteria) else "Loteria"
    concurso = row[COL_Concurso - 1] if _safe_len(row, COL_Concurso) else "0000"
    data_br = row[COL_Data - 1] if _safe_len(row, COL_Data) else _now().strftime(
        "%d/%m/%Y"
    )
    numeros = row[COL_Numeros - 1] if _safe_len(row, COL_Numeros) else ""
    url_res = row[COL_URL - 1] if _safe_len(row, COL_URL) else ""

    # gerar_imagem_loteria deve retornar BytesIO já posicionado
    return gerar_imagem_loteria(
        str(loteria), str(concurso), str(data_br), str(numeros), str(url_res)
    )


# =========================
# Texto (tweet/post/caption)
# =========================

# >>> AJUSTE AQUI COM SEUS LINKS OFICIAIS <<<
LINK_X = os.getenv("LINK_X", "https://x.com/PortalSimonSports")
LINK_TG = os.getenv("LINK_TG", "https://t.me/PortalSimonSports")
LINK_FB = os.getenv("LINK_FB", "https://facebook.com/PortalSimonSports")
LINK_IG = os.getenv("LINK_IG", "https://instagram.com/PortalSimonSports")
LINK_YT = os.getenv("LINK_YT", "https://youtube.com/@PortalSimonSports")


def montar_texto_base(row) -> str:
    """
    TEXTO PADRÃO:
    - Linha 1: CTA + link do resultado (coluna E)
    - Embaixo: links das redes sociais para inscrição/seguidores
    - Sem cabeçalho, sem lista de números
    """
    url = (row[COL_URL - 1] if _safe_len(row, COL_URL) else "").strip()

    linhas = []

    if url:
        linhas.append(f"🔗 Resultado completo aqui: {url}")
        linhas.append("")  # linha em branco

    linhas.append("📲 Siga o Portal SimonSports:")
    linhas.append(f"X: {LINK_X}")
    linhas.append(f"Telegram: {LINK_TG}")
    linhas.append(f"Facebook: {LINK_FB}")
    linhas.append(f"Instagram: {LINK_IG}")
    linhas.append(f"YouTube: {LINK_YT}")

    return "\n".join(linhas).strip()


# =========================
# Coleta de linhas candidatas (por REDE)
# =========================


def coletar_candidatos_para(ws, rede: str):
    """
    Retorna lista de tuplas (rownum, row) somente onde:
      - status da REDE (coluna específica) está VAZIO (após remover caracteres invisíveis)

    NÃO olha coluna de ENFILEIRADO.
    NÃO filtra mais por data (BACKLOG_DAYS ignorado).
    """
    rows = ws.get_all_values()
    if len(rows) <= 1:
        _log(f"[{rede}] Planilha sem dados.")
        return []

    data = rows[1:]
    cand = []
    col_status = COL_STATUS_REDES.get(rede)
    if not col_status:
        _log(f"[{rede}] Coluna de status não definida.")
        return []

    total = len(data)
    vazias = 0
    preenchidas = 0

    for rindex, row in enumerate(data, start=2):
        status_val = row[col_status - 1] if len(row) >= col_status else ""
        tem_status = not _is_empty_status(status_val)

        if not tem_status:
            cand.append((rindex, row))
            vazias += 1
        else:
            preenchidas += 1
            preview = str(status_val)
            preview = preview.replace("\n", "\\n")
            _log(
                f"[{rede}] SKIP L{rindex}: status col {col_status} preenchido ({preview[:40]})"
            )

    _log(
        f"[{rede}] Candidatas (sem filtro de data): {vazias}/{total} | status preenchido: {preenchidas}"
    )
    return cand


# =========================
# Publicadores por REDE
# =========================

# --- X (Twitter) ---
TW1 = {
    "api_key": os.getenv("TWITTER_API_KEY_1", ""),
    "api_secret": os.getenv("TWITTER_API_SECRET_1", ""),
    "access_token": os.getenv("TWITTER_ACCESS_TOKEN_1", ""),
    "access_secret": os.getenv("TWITTER_ACCESS_SECRET_1", ""),
}
TW2 = {
    "api_key": os.getenv("TWITTER_API_KEY_2", ""),
    "api_secret": os.getenv("TWITTER_API_SECRET_2", ""),
    "access_token": os.getenv("TWITTER_ACCESS_TOKEN_2", ""),
    "access_secret": os.getenv("TWITTER_ACCESS_SECRET_2", ""),
}


class XAccount:
    def __init__(self, label, api_key, api_secret, access_token, access_secret):
        self.label = label
        self.client_v2 = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        auth = tweepy.OAuth1UserHandler(
            api_key,
            api_secret,
            access_token,
            access_secret,
        )
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

    if ok(TW1):
        accs.append(XAccount("ACC1", **TW1))
    else:
        _log("Conta ACC1 incompleta nos Secrets — verifique *_1.")

    if ok(TW2):
        accs.append(XAccount("ACC2", **TW2))
    else:
        _log("Conta ACC2 incompleta nos Secrets — verifique *_2.")

    if not accs:
        raise RuntimeError("Nenhuma conta X configurada.")
    return accs


_recent_tweets_cache = defaultdict(set)
_postados_nesta_execucao = defaultdict(set)


def x_load_recent_texts(acc: XAccount, max_results=50):
    try:
        resp = acc.client_v2.get_users_tweets(
            id=acc.user_id,
            max_results=min(max_results, 100),
            tweet_fields=["text"],
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
        _log(f"[{acc.handle}] warn: falha ao ler tweets recentes: {e}")
        return set()


def x_is_dup(acc: XAccount, text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return (t in _recent_tweets_cache[acc.label]) or (t in _postados_nesta_execucao[acc.label])


def x_upload_media_if_any(acc: XAccount, row):
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
        _log(f"[X] Conta conectada: {acc.handle}")

    publicados = 0
    acc_idx = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("X")

    for rownum, row in candidatos[:limite]:
        texto_full = montar_texto_base(row)
        texto_para_postar = "" if mode == "IMAGE_ONLY" else texto_full
        ok_any = False

        if X_POST_IN_ALL_ACCOUNTS:
            for acc in contas:
                media_ids = x_upload_media_if_any(acc, row)
                try:
                    if DRY_RUN:
                        _log(f"[X][{acc.handle}] DRY-RUN")
                        ok = True
                    else:
                        if texto_para_postar and x_is_dup(acc, texto_para_postar):
                            _log(f"[X][{acc.handle}] SKIP duplicado.")
                            ok = False
                        else:
                            resp = acc.client_v2.create_tweet(
                                text=(texto_para_postar or None)
                                if mode != "IMAGE_ONLY"
                                else None,
                                media_ids=media_ids if POST_X_WITH_IMAGE else None,
                            )
                            if texto_para_postar:
                                _postados_nesta_execucao[acc.label].add(texto_para_postar)
                                _recent_tweets_cache[acc.label].add(texto_para_postar)
                            _log(f"[X][{acc.handle}] OK → {resp.data['id']}")
                            ok = True
                except Exception as e:
                    _log(f"[X][{acc.handle}] erro: {e}")
                    ok = False

                ok_any = ok_any or ok
                time.sleep(0.7)
        else:
            acc = contas[acc_idx % len(contas)]
            acc_idx += 1
            media_ids = x_upload_media_if_any(acc, row)
            try:
                if DRY_RUN:
                    _log(f"[X][{acc.handle}] DRY-RUN")
                    ok_any = True
                else:
                    if texto_para_postar and x_is_dup(acc, texto_para_postar):
                        _log(f"[X][{acc.handle}] SKIP duplicado.")
                        ok_any = False
                    else:
                        resp = acc.client_v2.create_tweet(
                            text=(texto_para_postar or None)
                            if mode != "IMAGE_ONLY"
                            else None,
                            media_ids=media_ids if POST_X_WITH_IMAGE else None,
                        )
                        if texto_para_postar:
                            _postados_nesta_execucao[acc.label].add(texto_para_postar)
                            _recent_tweets_cache[acc.label].add(texto_para_postar)
                        _log(f"[X][{acc.handle}] OK → {resp.data['id']}")
                        ok_any = True
            except Exception as e:
                _log(f"[X][{acc.handle}] erro: {e}")
                ok_any = False

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "X")
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"[X] Publicados: {publicados}")
    return publicados


# --- Facebook ---


def _fb_post_text(page_id, page_token, message: str, link: str | None = None):
    url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
    data = {"message": message, "access_token": page_token}
    if link:
        data["link"] = link
    r = requests.post(url, data=data, timeout=25)
    r.raise_for_status()
    return r.json().get("id")


def _fb_post_photo(page_id, page_token, caption: str, image_bytes: bytes):
    url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
    files = {"source": ("resultado.png", image_bytes, "image/png")}
    data = {"caption": caption, "published": "true", "access_token": page_token}
    r = requests.post(url, data=data, files=files, timeout=40)
    r.raise_for_status()
    return r.json().get("id")


def publicar_em_facebook(ws, candidatos):
    if not FB_PAGE_IDS or not FB_PAGE_TOKENS or len(FB_PAGE_IDS) != len(FB_PAGE_TOKENS):
        raise RuntimeError("Facebook: configure FB_PAGE_IDS e FB_PAGE_TOKENS (mesmo tamanho).")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("FACEBOOK")

    for rownum, row in candidatos[:limite]:
        base = montar_texto_base(row)
        msg = "" if mode == "IMAGE_ONLY" else base
        ok_any = False

        for pid, ptoken in zip(FB_PAGE_IDS, FB_PAGE_TOKENS):
            try:
                if DRY_RUN:
                    _log(f"[Facebook][{pid}] DRY-RUN")
                    ok = True
                else:
                    if POST_FB_WITH_IMAGE:
                        buf = _build_image_from_row(row)
                        fb_id = _fb_post_photo(pid, ptoken, msg, buf.getvalue())
                    else:
                        url_post = row[COL_URL - 1] if _safe_len(row, COL_URL) else ""
                        fb_id = _fb_post_text(pid, ptoken, msg, link=url_post or None)
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


# --- Telegram ---


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
        raise RuntimeError("Telegram: configure TG_BOT_TOKEN e TG_CHAT_IDS.")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("TELEGRAM")

    for rownum, row in candidatos[:limite]:
        base = montar_texto_base(row)
        msg = "" if mode == "IMAGE_ONLY" else base
        ok_any = False

        for chat_id in TG_CHAT_IDS:
            try:
                if DRY_RUN:
                    _log(f"[Telegram][{chat_id}] DRY-RUN")
                    ok = True
                else:
                    if POST_TG_WITH_IMAGE:
                        buf = _build_image_from_row(row)
                        msg_id = _tg_send_photo(TG_BOT_TOKEN, chat_id, msg, buf.getvalue())
                    else:
                        url_post = row[COL_URL - 1] if _safe_len(row, COL_URL) else ""
                        final_msg = msg
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


# --- Discord ---


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
        raise RuntimeError("Discord: defina DISCORD_WEBHOOKS (um ou mais, separados por vírgula).")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("DISCORD")

    for rownum, row in candidatos[:limite]:
        base = montar_texto_base(row)
        msg = "" if mode == "IMAGE_ONLY" else base
        ok_any = False

        try:
            if DRY_RUN:
                for wh in DISCORD_WEBHOOKS:
                    _log(f"[Discord] DRY-RUN → {wh[-18:]}")
                ok_any = True
            else:
                buf = _build_image_from_row(row)
                img_bytes = buf.getvalue()
                for wh in DISCORD_WEBHOOKS:
                    payload = msg
                    url_post = row[COL_URL - 1] if _safe_len(row, COL_URL) else ""
                    if url_post and payload:
                        payload = f"{payload}\n{url_post}"
                    elif url_post and not payload:
                        payload = url_post
                    _discord_send(wh, content=(payload or None), image_bytes=img_bytes)
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


# --- Pinterest ---


def _pinterest_create_pin(
    token,
    board_id,
    title,
    description,
    link,
    image_bytes=None,
    image_url=None,
):
    url = "https://api.pinterest.com/v5/pins"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "board_id": board_id,
        "title": title[:100],
        "description": (description or "")[:500],
    }
    if link:
        payload["link"] = link

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

    r = requests.post(url, headers=headers, json=payload, timeout=40)
    r.raise_for_status()
    return r.json().get("id")


def publicar_em_pinterest(ws, candidatos):
    if not (PINTEREST_ACCESS_TOKEN and PINTEREST_BOARD_ID):
        raise RuntimeError("Pinterest: defina PINTEREST_ACCESS_TOKEN e PINTEREST_BOARD_ID.")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    mode = get_text_mode("PINTEREST")

    for rownum, row in candidatos[:limite]:
        loteria = row[COL_Loteria - 1] if _safe_len(row, COL_Loteria) else "Loteria"
        concurso = row[COL_Concurso - 1] if _safe_len(row, COL_Concurso) else "0000"
        title = f"{loteria} — Concurso {concurso}"
        desc_full = montar_texto_base(row)
        desc = "" if mode == "IMAGE_ONLY" else desc_full
        url_post = row[COL_URL - 1] if _safe_len(row, COL_URL) else ""

        try:
            if DRY_RUN:
                _log(f"[Pinterest] DRY-RUN: {title}")
                ok = True
            else:
                if POST_PINTEREST_WITH_IMAGE:
                    buf = _build_image_from_row(row)
                    pin_id = _pinterest_create_pin(
                        PINTEREST_ACCESS_TOKEN,
                        PINTEREST_BOARD_ID,
                        title,
                        desc,
                        url_post,
                        image_bytes=buf.getvalue(),
                    )
                else:
                    pin_id = _pinterest_create_pin(
                        PINTEREST_ACCESS_TOKEN,
                        PINTEREST_BOARD_ID,
                        title,
                        desc,
                        url_post,
                        image_url=url_post or None,
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


# =========================
# Keepalive (opcional)
# =========================


def start_keepalive():
    try:
        from flask import Flask
    except ImportError:
        _log("Flask não instalado; keepalive desativado.")
        return None

    app = Flask(__name__)

    @app.route("/")
    @app.route("/ping")
    def root():
        return "ok", 200

    def run():
        port = int(os.getenv("PORT", KEEPALIVE_PORT))
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    th = Thread(target=run, daemon=True)
    th.start()
    _log(f"Keepalive Flask ativo em 0.0.0.0:{os.getenv('PORT', KEEPALIVE_PORT)}")
    return th


# =========================
# MAIN
# =========================


def main():
    _log(
        "Iniciando bot... "
        f"Origem={BOT_ORIGEM} | Redes={','.join(TARGET_NETWORKS)} | DRY_RUN={DRY_RUN} | "
        f"GLOBAL_TEXT_MODE={GLOBAL_TEXT_MODE or '—'} | KIT_FIRST={USE_KIT_IMAGE_FIRST}"
    )

    keepalive_thread = start_keepalive() if ENABLE_KEEPALIVE else None

    try:
        ws = _open_ws()

        for rede in TARGET_NETWORKS:
            if rede not in COL_STATUS_REDES:
                _log(f"[{rede}] rede não suportada.")
                continue

            candidatos = coletar_candidatos_para(ws, rede)
            if not candidatos:
                _log(f"[{rede}] Nenhuma candidata.")
                continue

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
                _log(f"[{rede}] não implementada.")

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