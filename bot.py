# bot.py — Portal SimonSports — Publicador Automático (X, Facebook, Telegram, Discord, Pinterest)
# Rev: 2025-11-01 — multi-redes + multi-contas + imagem 3D + status por rede + backlog por data
# Planilha: ImportadosBlogger2  |  Colunas principais: A=Loteria B=Concurso C=Data D=Números E=URL
# Status por rede (padrões): H=8 (X), M=13 (Discord), N=14 (Pinterest), O=15 (Facebook), J=10 (Telegram)

import os
import io
import re
import json
import time
import base64
import pytz
import tweepy
import requests
import datetime as dt
import unicodedata
from urllib.parse import urlparse
from threading import Thread
from collections import defaultdict
from dotenv import load_dotenv

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Pillow
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# =========================
# CONFIG / ENV
# =========================
load_dotenv()
TZ = pytz.timezone("America/Sao_Paulo")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
SHEET_TAB = os.getenv("SHEET_TAB", "ImportadosBlogger2").strip()

# Execute em UMA ou MAIS redes: "X,FACEBOOK,TELEGRAM,DISCORD,PINTEREST"
TARGET_NETWORKS = [s.strip().upper() for s in os.getenv("TARGET_NETWORKS", "X").split(",") if s.strip()]

BACKLOG_DAYS = int(os.getenv("BACKLOG_DAYS", "7"))
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() == "true"

# ===== X (Twitter)
X_POST_IN_ALL_ACCOUNTS = os.getenv("X_POST_IN_ALL_ACCOUNTS", "true").strip().lower() == "true"
POST_X_WITH_IMAGE = os.getenv("POST_X_WITH_IMAGE", "true").strip().lower() == "true"
COL_STATUS_X = int(os.getenv("COL_STATUS_X", "8"))

# ===== Facebook (Páginas)
POST_FB_WITH_IMAGE = os.getenv("POST_FB_WITH_IMAGE", "true").strip().lower() == "true"
COL_STATUS_FACEBOOK = int(os.getenv("COL_STATUS_FACEBOOK", "15"))
FB_PAGE_IDS = [s.strip() for s in os.getenv("FB_PAGE_IDS", os.getenv("FB_PAGE_ID", "")).split(",") if s.strip()]
FB_PAGE_TOKENS = [s.strip() for s in os.getenv("FB_PAGE_TOKENS", os.getenv("FB_PAGE_TOKEN", "")).split(",") if s.strip()]

# ===== Telegram
POST_TG_WITH_IMAGE = os.getenv("POST_TG_WITH_IMAGE", "true").strip().lower() == "true"
COL_STATUS_TELEGRAM = int(os.getenv("COL_STATUS_TELEGRAM", "10"))
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
TG_CHAT_IDS = [s.strip() for s in os.getenv("TG_CHAT_IDS", "").split(",") if s.strip()]

# ===== Discord
COL_STATUS_DISCORD = int(os.getenv("COL_STATUS_DISCORD", "13"))
DISCORD_WEBHOOKS = [s.strip() for s in os.getenv("DISCORD_WEBHOOKS", "").split(",") if s.strip()]

# ===== Pinterest
COL_STATUS_PINTEREST = int(os.getenv("COL_STATUS_PINTEREST", "14"))
PINTEREST_ACCESS_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "").strip()
PINTEREST_BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "").strip()
POST_PINTEREST_WITH_IMAGE = os.getenv("POST_PINTEREST_WITH_IMAGE", "true").strip().lower() == "true"

# ===== Keepalive (Replit/Render)
ENABLE_KEEPALIVE = os.getenv("ENABLE_KEEPALIVE", "false").strip().lower() == "true"
KEEPALIVE_PORT = int(os.getenv("KEEPALIVE_PORT", "8080"))

# Limites
MAX_PUBLICACOES_RODADA = int(os.getenv("MAX_PUBLICACOES_RODADA", "30"))
PAUSA_ENTRE_POSTS = float(os.getenv("PAUSA_ENTRE_POSTS", "2.0"))

def _detect_origem():
    if os.getenv("BOT_ORIGEM"): return os.getenv("BOT_ORIGEM").strip()
    if os.getenv("GITHUB_ACTIONS"): return "GitHub"
    if os.getenv("REPL_ID") or os.getenv("REPLIT_DB_URL"): return "Replit"
    if os.getenv("RENDER"): return "Render"
    return "Local"

BOT_ORIGEM = _detect_origem()

# =========================
# Planilha — colunas (1-based)
# =========================
COL_Loteria, COL_Concurso, COL_Data, COL_Numeros, COL_URL = 1, 2, 3, 4, 5
COL_URL_Imagem, COL_Imagem = 6, 7  # opcionais

COL_STATUS_REDES = {
    "X": COL_STATUS_X,               # H
    "FACEBOOK": COL_STATUS_FACEBOOK, # O
    "TELEGRAM": COL_STATUS_TELEGRAM, # J
    "DISCORD": COL_STATUS_DISCORD,   # M
    "PINTEREST": COL_STATUS_PINTEREST, # N
}

# =========================
# Dicionários visuais
# =========================
CORES_LOTERIAS = {
    "mega-sena": "#006400", "quina": "#4B0082", "lotofácil": "#DD4A91", "lotomania": "#FF8C00",
    "timemania": "#00A650", "dupla sena": "#8B0000", "federal": "#8B4513", "dia de sorte": "#FFD700",
    "super sete": "#FF4500", "loteca": "#006400",
}

LOGOS_LOTERIAS = {
    "mega-sena": "https://loterias.caixa.gov.br/Site/Imagens/loterias/megasena.png",
    "quina": "https://loterias.caixa.gov.br/Site/Imagens/loterias/quina.png",
    "lotofácil": "https://loterias.caixa.gov.br/Site/Imagens/loterias/lotofacil.png",
    "lotomania": "https://loterias.caixa.gov.br/Site/Imagens/loterias/lotomania.png",
    "timemania": "https://loterias.caixa.gov.br/Site/Imagens/loterias/timemania.png",
    "dupla sena": "https://loterias.caixa.gov.br/Site/Imagens/loterias/duplasena.png",
    "federal": "https://loterias.caixa.gov.br/Site/Imagens/loterias/federal.png",
    "dia de sorte": "https://loterias.caixa.gov.br/Site/Imagens/loterias/diadesorte.png",
    "super sete": "https://loterias.caixa.gov.br/Site/Imagens/loterias/supersete.png",
    "loteca": "https://loterias.caixa.gov.br/Site/Imagens/loterias/loteca.png",
}

NUMEROS_POR_LOTERIA = {
    "mega-sena": 6, "quina": 5, "lotofácil": 15, "lotomania": 20,
    "timemania": 10, "dupla sena": 6, "federal": 5, "dia de sorte": 7,
    "super sete": 7, "loteca": 14,
}

# =========================
# Utilitários
# =========================
def _not_empty(v): return bool(str(v or "").strip())
def _now(): return dt.datetime.now(TZ)
def _ts(): return _now().strftime("%Y-%m-%d %H:%M:%S")
def _ts_br(): return _now().strftime("%d/%m/%Y %H:%M")
def _safe_len(row, idx): return len(row) >= idx
def _log(*a): print(f"[{_ts()}]", *a, flush=True)

def _parse_date_br(s: str):
    """Aceita 'dd/mm/aaaa' e ignora hora se houver."""
    s = str(s or "").strip()
    if not s: return None
    m = re.match(r"(\d{2}/\d{2}/\d{4})", s)
    if not m: return None
    try:
        return dt.datetime.strptime(m.group(1), "%d/%m/%Y").date()
    except ValueError:
        return None

def _within_backlog(date_br: str, days: int) -> bool:
    if days <= 0: return True
    d = _parse_date_br(date_br)
    if not d: return True
    return (_now().date() - d).days <= days

# ==== NOVOS UTILITÁRIOS ====
def _norm_key_loteria(name: str) -> str:
    """Normaliza variações: acentos, hifens, espaços e grafias (mega sena -> mega-sena)."""
    n = unicodedata.normalize('NFD', str(name or '').strip().lower())
    n = ''.join(c for c in n if unicodedata.category(c) != 'Mn')  # remove acento
    n = n.replace('mega sena', 'mega-sena')
    n = n.replace('lotofacil', 'lotofácil')  # sua chave usa acento
    n = n.replace('duplasena', 'dupla sena')
    n = n.replace('super sete', 'super sete')
    n = n.replace('dia de sorte', 'dia de sorte')
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def _fetch_image_bytes(url: str, timeout=20):
    """Baixa uma imagem (PNG/JPG) e retorna bytes, ou None se falhar."""
    try:
        if not url: return None
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        if r.content and len(r.content) > 1000:
            return r.content
    except Exception as e:
        _log(f"[fetch_image] falha: {e}")
    return None

# =========================
# Google Sheets
# =========================
def _gs_client():
    sa_json = os.getenv("GOOGLE_SERVICE_JSON", "").strip()
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    if sa_json:
        info = json.loads(sa_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scopes)
    else:
        path = "service_account.json"
        if not os.path.exists(path):
            raise RuntimeError("Credencial Google ausente (defina GOOGLE_SERVICE_JSON ou service_account.json)")
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
# X / Twitter — contas e anti-duplicados
# =========================
TW1 = {
    "api_key":       os.getenv("TWITTER_API_KEY_1", ""),
    "api_secret":    os.getenv("TWITTER_API_SECRET_1", ""),
    "access_token":  os.getenv("TWITTER_ACCESS_TOKEN_1", ""),
    "access_secret": os.getenv("TWITTER_ACCESS_SECRET_1", ""),
}
TW2 = {
    "api_key":       os.getenv("TWITTER_API_KEY_2", ""),
    "api_secret":    os.getenv("TWITTER_API_SECRET_2", ""),
    "access_token":  os.getenv("TWITTER_ACCESS_TOKEN_2", ""),
    "access_secret": os.getenv("TWITTER_ACCESS_SECRET_2", ""),
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
    def ok(d): return all(d.get(k) for k in ("api_key","api_secret","access_token","access_secret"))
    if ok(TW1): accs.append(XAccount("ACC1", **TW1))
    else: _log("Conta ACC1 incompleta nos Secrets — verifique *_1.")
    if ok(TW2): accs.append(XAccount("ACC2", **TW2))
    else: _log("Conta ACC2 incompleta nos Secrets — verifique *_2.")
    if not accs: raise RuntimeError("Nenhuma conta X configurada.")
    return accs

_recent_tweets_cache = defaultdict(set)
_postados_nesta_execucao = defaultdict(set)

def x_load_recent_texts(acc: XAccount, max_results=50):
    try:
        resp = acc.client_v2.get_users_tweets(
            id=acc.user_id, max_results=min(max_results, 100), tweet_fields=["text"]
        )
        out = set()
        if resp and resp.data:
            for tw in resp.data:
                t = (tw.text or "").strip()
                if t: out.add(t)
        _recent_tweets_cache[acc.label] = set(list(out)[-50:])
        return _recent_tweets_cache[acc.label]
    except Exception as e:
        _log(f"[{acc.handle}] warn: falha ao ler tweets recentes: {e}")
        return set()

def x_is_dup(acc: XAccount, text: str) -> bool:
    t = (text or "").strip()
    if not t: return False
    return (t in _recent_tweets_cache[acc.label]) or (t in _postados_nesta_execucao[acc.label])

# =========================
# Inferência de LOGO a partir da URL (coluna E)
# =========================
def get_logo_from_url(url: str):
    try:
        if not url: return None
        p = urlparse(str(url))
        path = (p.path or "").lower()
        for slug in LOGOS_LOTERIAS:
            if slug.replace(' ', '-') in path:
                return LOGOS_LOTERIAS.get(slug)
        last = path.rstrip('/').split('/')[-1]
        m = re.match(r'([a-z0-9\-]+)', last)
        if m:
            candidate = re.sub(r'-\d+$', '', m.group(1))
            for slug in LOGOS_LOTERIAS:
                if slug.replace(' ', '-').lower() == candidate:
                    return LOGOS_LOTERIAS.get(slug)
        return None
    except Exception:
        return None

# =========================
# Fontes (fallback)
# =========================
def _load_font(size, bold=False):
    try:
        path = "arialbd.ttf" if bold else "arial.ttf"
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

# =========================
# Imagem 3D
# =========================
def gerar_imagem_3d(loteria, concurso, data_br, numeros_str, url_resultado, logo_override=None):
    key = _norm_key_loteria(loteria)
    cor_hex = CORES_LOTERIAS.get(key, "#4B0082")
    cor_rgb = tuple(int(cor_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

    logo_url = (str(logo_override).strip() or None) if logo_override else None
    if not logo_url:
        logo_url = get_logo_from_url(url_resultado) or LOGOS_LOTERIAS.get(key)

    max_numeros = NUMEROS_POR_LOTERIA.get(key, 6)
    numeros = [n.strip() for n in str(numeros_str).replace(',', ' ').split() if n.strip()]
    if not numeros: numeros = ["?"] * max_numeros
    numeros = numeros[:max_numeros]

    largura, altura = 880, 900
    img = Image.new('RGB', (largura, altura), color='#ffffff')
    draw = ImageDraw.Draw(img)
    font_titulo = _load_font(56, bold=True)
    font_sub = _load_font(36, bold=False)
    y = 40

    titulo = f"{loteria} — Concurso {concurso}"
    draw.text((60, y), titulo, fill='#0f172a', font=font_titulo); y += 80
    draw.text((60, y), f"{data_br}", fill='#475569', font=font_sub); y += 70

    if logo_url:
        try:
            r = requests.get(logo_url, timeout=10); r.raise_for_status()
            logo_img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            ratio = logo_img.width / logo_img.height
            h = min(150, int(largura * 0.3)); w = int(h * ratio)
            if w > largura - 120: w = largura - 120; h = int(w / ratio)
            logo_img = logo_img.resize((w, h), Image.Resampling.LANCZOS)
            x_logo = (largura - w) // 2
            img.paste(logo_img, (x_logo, y), logo_img); y += h + 40
        except Exception as e:
            _log(f"Logo falhou ({loteria}): {e}"); y += 20
    else:
        y += 20

    raio = 64; espaco = 110
    x_inicio = (largura - (len(numeros) * espaco - espaco//2)) // 2
    for i, num in enumerate(numeros):
        x = x_inicio + i * espaco
        bola = Image.new('RGBA', (raio*2+36, raio*2+36), (0,0,0,0))
        d = ImageDraw.Draw(bola)
        for j in range(raio):
            k = 1.0 - (j/raio)*0.6
            fill = tuple(int(c*k) for c in cor_rgb) + (255,)
            d.ellipse((j, j, raio*2+36 - j*2, raio*2+36 - j*2), fill=fill)
        brilho = Image.new('RGBA', (raio*2+36, raio*2+36), (0,0,0,0))
        ImageDraw.Draw(brilho).ellipse((24, 18, 58, 52), fill=(255,255,255,170))
        bola = Image.alpha_composite(bola, brilho)
        sombra = bola.filter(ImageFilter.GaussianBlur(12))
        img.paste((0,0,0,60), (x-12, y+18), sombra)
        img.paste(bola, (x-12, y-12), bola)
        font_size = 50 if len(num) <= 2 else 42
        font_num = _load_font(font_size, bold=True)
        txt_img = Image.new('RGBA', (160,160), (0,0,0,0))
        td = ImageDraw.Draw(txt_img)
        td.text((80, 58), str(num), font=font_num, fill=(0,0,0,210), anchor="mm")
        td.text((78, 56), str(num), font=font_num, fill=(255,255,255,255), anchor="mm")
        img.paste(txt_img, (x-68, y-68), txt_img)

    y += 170
    if url_resultado:
        draw.text((60, y), "Resultado completo:", fill='#0f172a', font=font_sub); y += 42
        draw.text((60, y), str(url_resultado), fill='#0ea5e9', font=font_sub); y += 60

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer

# =========================
# Texto (tweet/post/caption)
# =========================
def montar_texto_base(row, incluir_telegram=False) -> str:
    loteria = (row[COL_Loteria-1] if _safe_len(row, COL_Loteria) else "").strip()
    concurso = (row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else "").strip()
    data_br = (row[COL_Data-1] if _safe_len(row, COL_Data) else "").strip()
    numeros = (row[COL_Numeros-1] if _safe_len(row, COL_Numeros) else "").strip()
    url = (row[COL_URL-1] if _safe_len(row, COL_URL) else "").strip()

    nums = [n.strip() for n in numeros.replace(';', ',').replace(' ', ',').split(',') if n.strip()]
    nums_str = ", ".join(nums)

    linhas = [f"{loteria} — Concurso {concurso} — ({data_br})"]
    if nums_str: linhas.append(f"Números: {nums_str}")
    if url: linhas += ["Resultado completo:", url]

    return "\n".join(linhas).strip()

# =========================
# Coleta de linhas candidatas (por REDE)
# =========================
def coletar_candidatos_para(ws, rede: str):
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
    vazias = preenchidas = fora_backlog = 0

    for rindex, row in enumerate(data, start=2):
        status_val = row[col_status-1] if len(row) >= col_status else ""
        tem_status = bool(str(status_val or "").strip())
        data_br = row[COL_Data-1] if _safe_len(row, COL_Data) else ""
        dentro = _within_backlog(data_br, BACKLOG_DAYS)

        if dentro and not tem_status:
            cand.append((rindex, row)); vazias += 1
        else:
            if tem_status:
                preenchidas += 1
                _log(f"[{rede}] SKIP L{rindex}: status col {col_status} preenchido ({str(status_val)[:25]})")
            elif not dentro:
                fora_backlog += 1
                _log(f"[{rede}] SKIP L{rindex}: fora do backlog ({data_br})")

    _log(f"[{rede}] Candidatas: {vazias}/{total} | status: {preenchidas} | fora backlog: {fora_backlog}")
    return cand

# =========================
# Publicadores por REDE
# =========================
# --- X ---
def x_upload_media_if_any(acc: XAccount, row):
    if not POST_X_WITH_IMAGE or DRY_RUN:
        return None

    loteria = row[COL_Loteria-1] if _safe_len(row, COL_Loteria) else "Loteria"
    concurso = row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else "0000"
    data_br = row[COL_Data-1] if _safe_len(row, COL_Data) else _now().strftime("%d/%m/%Y")
    numeros = row[COL_Numeros-1] if _safe_len(row, COL_Numeros) else ""
    url_res = row[COL_URL-1] if _safe_len(row, COL_URL) else ""

    # 1) Se já houver URL IMAGEM (imagem pronta), usa ela
    if _safe_len(row, COL_URL_Imagem):
        url_img = str(row[COL_URL_Imagem-1] or "").strip()
        if url_img:
            pic = _fetch_image_bytes(url_img)
            if pic:
                buf = io.BytesIO(pic)
                media = acc.api_v1.media_upload(filename="resultado.png", file=buf)
                return [media.media_id_string]

    # 2) Se não houver imagem pronta, gera 3D (com logo inferido pela URL)
    logo_override = None
    if _safe_len(row, COL_Imagem) and str(row[COL_Imagem-1]).strip():
        logo_override = str(row[COL_Imagem-1]).strip()
    else:
        logo_override = get_logo_from_url(url_res)

    try:
        buf = gerar_imagem_3d(loteria, concurso, data_br, str(numeros), url_res, logo_override=logo_override)
        with buf:
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

    publicados = 0; acc_idx = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    for rownum, row in candidatos[:limite]:
        texto = montar_texto_base(row)
        ok_any = False
        if X_POST_IN_ALL_ACCOUNTS:
            for acc in contas:
                media_ids = x_upload_media_if_any(acc, row)
                try:
                    if DRY_RUN:
                        _log(f"[X][{acc.handle}] DRY-RUN: {texto[:60]}...")
                        ok = True
                    else:
                        if x_is_dup(acc, texto):
                            _log(f"[X][{acc.handle}] SKIP duplicado."); ok = False
                        else:
                            resp = acc.client_v2.create_tweet(text=texto, media_ids=media_ids)
                            _postados_nesta_execucao[acc.label].add(texto)
                            _recent_tweets_cache[acc.label].add(texto)
                            _log(f"[X][{acc.handle}] OK → {resp.data['id']}"); ok = True
                except Exception as e:
                    _log(f"[X][{acc.handle}] erro: {e}"); ok = False
                ok_any = ok_any or ok
                time.sleep(0.7)
        else:
            acc = contas[acc_idx % len(contas)]; acc_idx += 1
            media_ids = x_upload_media_if_any(acc, row)
            try:
                if DRY_RUN:
                    _log(f"[X][{acc.handle}] DRY-RUN: {texto[:60]}..."); ok_any = True
                else:
                    if x_is_dup(acc, texto):
                        _log(f"[X][{acc.handle}] SKIP duplicado."); ok_any = False
                    else:
                        resp = acc.client_v2.create_tweet(text=texto, media_ids=media_ids)
                        _postados_nesta_execucao[acc.label].add(texto)
                        _recent_tweets_cache[acc.label].add(texto)
                        _log(f"[X][{acc.handle}] OK → {resp.data['id']}"); ok_any = True
            except Exception as e:
                _log(f"[X][{acc.handle}] erro: {e}"); ok_any = False

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "X"); publicados += 1
        time.sleep(PAUSA_ENTRE_POSTS)
    _log(f"[X] Publicados: {publicados}")
    return publicados

# --- Facebook ---
def _fb_post_text(page_id, page_token, message: str, link: str = None):
    url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
    data = {"message": message, "access_token": page_token}
    if link: data["link"] = link
    r = requests.post(url, data=data, timeout=25); r.raise_for_status()
    return r.json().get("id")

def _fb_post_photo(page_id, page_token, caption: str, image_bytes: bytes):
    url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
    files = {"source": ("resultado.png", image_bytes, "image/png")}
    data = {"caption": caption, "published": "true", "access_token": page_token}
    r = requests.post(url, data=data, files=files, timeout=40); r.raise_for_status()
    return r.json().get("id")

def publicar_em_facebook(ws, candidatos):
    if not FB_PAGE_IDS or not FB_PAGE_TOKENS or len(FB_PAGE_IDS) != len(FB_PAGE_TOKENS):
        raise RuntimeError("Facebook: configure FB_PAGE_IDS e FB_PAGE_TOKENS (mesmo tamanho).")
    publicados = 0; limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    for rownum, row in candidatos[:limite]:
        msg = montar_texto_base(row)
        url_post = row[COL_URL-1] if _safe_len(row, COL_URL) else ""
        loteria = row[COL_Loteria-1] if _safe_len(row, COL_Loteria) else "Loteria"
        concurso = row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else "0000"
        data_br = row[COL_Data-1] if _safe_len(row, COL_Data) else _now().strftime("%d/%m/%Y")
        numeros = row[COL_Numeros-1] if _safe_len(row, COL_Numeros) else ""

        # Tenta usar imagem pronta (URL IMAGEM); se não, gera 3D
        img_bytes = None
        if _safe_len(row, COL_URL_Imagem):
            url_img = str(row[COL_URL_Imagem-1] or "").strip()
            if url_img:
                img_bytes = _fetch_image_bytes(url_img)

        logo_override = None
        if _safe_len(row, COL_Imagem) and str(row[COL_Imagem-1]).strip():
            logo_override = str(row[COL_Imagem-1]).strip()
        else:
            logo_override = get_logo_from_url(url_post)

        ok_any = False
        for pid, ptoken in zip(FB_PAGE_IDS, FB_PAGE_TOKENS):
            try:
                if DRY_RUN:
                    _log(f"[Facebook][{pid}] DRY-RUN: {msg[:60]}..."); ok = True
                else:
                    if POST_FB_WITH_IMAGE:
                        if not img_bytes:
                            buf = gerar_imagem_3d(loteria, concurso, data_br, str(numeros), url_post, logo_override=logo_override)
                            img_bytes = buf.getvalue()
                        fb_id = _fb_post_photo(pid, ptoken, msg, img_bytes)
                    else:
                        fb_id = _fb_post_text(pid, ptoken, msg, link=url_post or None)
                    _log(f"[Facebook][{pid}] OK → {fb_id}"); ok = True
            except Exception as e:
                _log(f"[Facebook][{pid}] erro: {e}"); ok = False
            ok_any = ok_any or ok
            time.sleep(0.7)

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "FACEBOOK"); publicados += 1
        time.sleep(PAUSA_ENTRE_POSTS)
    _log(f"[Facebook] Publicados: {publicados}")
    return publicados

# --- Telegram ---
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
    if not TG_BOT_TOKEN or not TG_CHAT_IDS:
        raise RuntimeError("Telegram: configure TG_BOT_TOKEN e TG_CHAT_IDS.")
    publicados = 0; limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    for rownum, row in candidatos[:limite]:
        msg = montar_texto_base(row, incluir_telegram=True)
        url_post = row[COL_URL-1] if _safe_len(row, COL_URL) else ""
        loteria = row[COL_Loteria-1] if _safe_len(row, COL_Loteria) else "Loteria"
        concurso = row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else "0000"
        data_br = row[COL_Data-1] if _safe_len(row, COL_Data) else _now().strftime("%d/%m/%Y")
        numeros = row[COL_Numeros-1] if _safe_len(row, COL_Numeros) else ""

        # Preferir URL IMAGEM
        img_bytes = None
        if _safe_len(row, COL_URL_Imagem):
            url_img = str(row[COL_URL_Imagem-1] or "").strip()
            if url_img:
                img_bytes = _fetch_image_bytes(url_img)

        logo_override = None
        if _safe_len(row, COL_Imagem) and str(row[COL_Imagem-1]).strip():
            logo_override = str(row[COL_Imagem-1]).strip()
        else:
            logo_override = get_logo_from_url(url_post)

        ok_any = False
        for chat_id in TG_CHAT_IDS:
            try:
                if DRY_RUN:
                    _log(f"[Telegram][{chat_id}] DRY-RUN: {msg[:60]}..."); ok = True
                else:
                    if POST_TG_WITH_IMAGE:
                        if not img_bytes:
                            buf = gerar_imagem_3d(loteria, concurso, data_br, str(numeros), url_post, logo_override=logo_override)
                            img_bytes = buf.getvalue()
                        msg_id = _tg_send_photo(TG_BOT_TOKEN, chat_id, msg, img_bytes)
                    else:
                        if url_post: msg = f"{msg}\n{url_post}"
                        msg_id = _tg_send_text(TG_BOT_TOKEN, chat_id, msg)
                    _log(f"[Telegram][{chat_id}] OK → {msg_id}"); ok = True
            except Exception as e:
                _log(f"[Telegram][{chat_id}] erro: {e}"); ok = False
            ok_any = ok_any or ok
            time.sleep(0.5)

        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "TELEGRAM"); publicados += 1
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
    for rownum, row in candidatos[:limite]:
        msg = montar_texto_base(row)
        url_post = row[COL_URL-1] if _safe_len(row, COL_URL) else ""
        loteria = row[COL_Loteria-1] if _safe_len(row, COL_Loteria) else "Loteria"
        concurso = row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else "0000"
        data_br = row[COL_Data-1] if _safe_len(row, COL_Data) else _now().strftime("%d/%m/%Y")
        numeros = row[COL_Numeros-1] if _safe_len(row, COL_Numeros) else ""

        # Preferir URL IMAGEM
        img_bytes = None
        if _safe_len(row, COL_URL_Imagem):
            url_img = str(row[COL_URL_Imagem-1] or "").strip()
            if url_img:
                img_bytes = _fetch_image_bytes(url_img)
        if not img_bytes:
            logo_override = get_logo_from_url(url_post)
            buf = gerar_imagem_3d(loteria, concurso, data_br, str(numeros), url_post, logo_override=logo_override)
            img_bytes = buf.getvalue()

        ok_any = False
        try:
            if DRY_RUN:
                for wh in DISCORD_WEBHOOKS:
                    _log(f"[Discord] DRY-RUN → {wh[-18:]}: {msg[:60]}...")
                ok_any = True
            else:
                for wh in DISCORD_WEBHOOKS:
                    _discord_send(wh, content=f"{msg}\n{url_post}" if url_post else msg, image_bytes=img_bytes)
                    _log(f"[Discord] OK → {wh[-18:]}")
                ok_any = True
        except Exception as e:
            _log(f"[Discord] erro: {e}"); ok_any = False
        if ok_any and not DRY_RUN:
            marcar_publicado(ws, rownum, "DISCORD"); publicados += 1
        time.sleep(PAUSA_ENTRE_POSTS)
    _log(f"[Discord] Publicados: {publicados}")
    return publicados

# --- Pinterest ---
def _pinterest_create_pin(token, board_id, title, description, link, image_bytes=None, image_url=None):
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
    r = requests.post(url, headers=headers, json=payload, timeout=40)
    r.raise_for_status()
    return r.json().get("id")

def publicar_em_pinterest(ws, candidatos):
    if not (PINTEREST_ACCESS_TOKEN and PINTEREST_BOARD_ID):
        raise RuntimeError("Pinterest: defina PINTEREST_ACCESS_TOKEN e PINTEREST_BOARD_ID.")
    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    for rownum, row in candidatos[:limite]:
        loteria = row[COL_Loteria-1] if _safe_len(row, COL_Loteria) else "Loteria"
        concurso = row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else "0000"
        data_br = row[COL_Data-1] if _safe_len(row, COL_Data) else _now().strftime("%d/%m/%Y")
        numeros = row[COL_Numeros-1] if _safe_len(row, COL_Numeros) else ""
        url_post = row[COL_URL-1] if _safe_len(row, COL_URL) else ""
        title = f"{loteria} — Concurso {concurso}"
        desc = montar_texto_base(row)

        # Preferir URL IMAGEM
        img_bytes = None
        if POST_PINTEREST_WITH_IMAGE:
            if _safe_len(row, COL_URL_Imagem):
                url_img = str(row[COL_URL_Imagem-1] or "").strip()
                if url_img:
                    img_bytes = _fetch_image_bytes(url_img)
            if not img_bytes:
                logo_override = get_logo_from_url(url_post)
                buf = gerar_imagem_3d(loteria, concurso, data_br, str(numeros), url_post, logo_override=logo_override)
                img_bytes = buf.getvalue()
            pin_id = _pinterest_create_pin(PINTEREST_ACCESS_TOKEN, PINTEREST_BOARD_ID, title, desc, url_post, image_bytes=img_bytes)
        else:
            pin_id = _pinterest_create_pin(PINTEREST_ACCESS_TOKEN, PINTEREST_BOARD_ID, title, desc, url_post, image_url=url_post or None)

        try:
            _log(f"[Pinterest] OK → {pin_id}"); ok = True
        except Exception as e:
            _log(f"[Pinterest] erro: {e}"); ok = False

        if ok and not DRY_RUN:
            marcar_publicado(ws, rownum, "PINTEREST"); publicados += 1
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
    th = Thread(target=run, daemon=True); th.start()
    _log(f"Keepalive Flask ativo em 0.0.0.0:{os.getenv('PORT', KEEPALIVE_PORT)}")
    return th

# =========================
# MAIN
# =========================
def main():
    _log(f"Iniciando bot... Origem={BOT_ORIGEM} | Redes={','.join(TARGET_NETWORKS)} | DRY_RUN={DRY_RUN}")
    keepalive_thread = start_keepalive() if ENABLE_KEEPALIVE else None
    try:
        ws = _open_ws()
        for rede in TARGET_NETWORKS:
            if rede not in COL_STATUS_REDES:
                _log(f"[{rede}] rede não suportada."); continue
            candidatos = coletar_candidatos_para(ws, rede)
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
                _log(f"[{rede}] não implementada.")
        _log("Concluído.")
    except KeyboardInterrupt:
        _log("Interrompido pelo usuário.")
    except Exception as e:
        _log(f"[FATAL] {e}"); raise
    finally:
        if ENABLE_KEEPALIVE and keepalive_thread: time.sleep(1)

if __name__ == "__main__":
    main()