# bot.py — Portal SimonSports — Publicador Automático de Loterias no X (Twitter)
# Rev: 2025-11-01 — IMAGEM 3D + LOGO por URL (coluna E) + multi-contas + keepalive opcional
# Loterias: Mega-Sena, Quina, Lotofácil, Lotomania, Timemania, Dupla Sena, Federal, Dia de Sorte, Super Sete, Loteca

import os
import io
import re
import json
import time
import pytz
import tweepy
import requests
import datetime as dt
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

SHEET_ID  = os.getenv("GOOGLE_SHEET_ID", "").strip()
SHEET_TAB = os.getenv("SHEET_TAB", "ImportadosBlogger2").strip()

TARGET_NETWORK = os.getenv("TARGET_NETWORK", "X").strip().upper()
BACKLOG_DAYS   = int(os.getenv("BACKLOG_DAYS", "7"))

# Publicar a MESMA linha em todas as contas X
X_POST_IN_ALL_ACCOUNTS = os.getenv("X_POST_IN_ALL_ACCOUNTS", "true").strip().lower() == "true"

# Anexar imagem gerada
POST_X_WITH_IMAGE = os.getenv("POST_X_WITH_IMAGE", "true").strip().lower() == "true"

# Keepalive opcional (para Replit/Render)
ENABLE_KEEPALIVE = os.getenv("ENABLE_KEEPALIVE", "false").strip().lower() == "true"
KEEPALIVE_PORT   = int(os.getenv("KEEPALIVE_PORT", "8080"))

# Limites
MAX_PUBLICACOES_RODADA = int(os.getenv("MAX_PUBLICACOES_RODADA", "30"))
PAUSA_ENTRE_POSTS      = float(os.getenv("PAUSA_ENTRE_POSTS", "2.0"))

# Canais do Telegram (exibidos no texto e na imagem)
TELEGRAM_CANAL_1 = os.getenv("TELEGRAM_CANAL_1", "https://t.me/portalsimonsportsdicasesportivas")
TELEGRAM_CANAL_2 = os.getenv("TELEGRAM_CANAL_2", "https://t.me/portalsimonsports")

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
COL_URL_Imagem, COL_Imagem = 6, 7           # opcionais
COL_STATUS_REDES = {"X": 8}                  # H

# =========================
# Dicionários visuais
# =========================
CORES_LOTERIAS = {
    "mega-sena": "#006400",
    "quina": "#4B0082",
    "lotofácil": "#DD4A91",
    "lotomania": "#FF8C00",
    "timemania": "#00A650",
    "dupla sena": "#8B0000",
    "federal": "#8B4513",
    "dia de sorte": "#FFD700",
    "super sete": "#FF4500",
    "loteca": "#006400",
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
def _status_col_for_target(): return COL_STATUS_REDES.get(TARGET_NETWORK, 8)
def _now(): return dt.datetime.now(TZ)
def _ts(): return _now().strftime("%Y-%m-%d %H:%M:%S")
def _ts_br(): return _now().strftime("%d/%m/%Y %H:%M")

def _parse_date_br(s: str):
    s = str(s or "").strip()
    try:
        d, m, y = s.split("/")
        return dt.date(int(y), int(m), int(d))
    except Exception:
        return None

def _within_backlog(date_br: str, days: int) -> bool:
    if days <= 0:
        return True
    d = _parse_date_br(date_br)
    if not d:
        return True
    return (_now().date() - d).days <= days

def _safe_len(row, idx): return len(row) >= idx
def _log(*a): print(f"[{_ts()}]", *a, flush=True)

# =========================
# Google Sheets
# =========================
def _gs_client():
    sa_json = os.getenv("GOOGLE_SERVICE_JSON", "").strip()
    scopes = ['https://www.googleapis.com/auth/spreadsheets',
              'https://www.googleapis.com/auth/drive']
    if sa_json:
        info = json.loads(sa_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scopes)
    else:
        if not os.path.exists("service_account.json"):
            raise RuntimeError("Credencial Google ausente (defina GOOGLE_SERVICE_JSON ou service_account.json)")
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scopes)
    return gspread.authorize(creds)

def _open_ws():
    if not SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID não definido.")
    sh = _gs_client().open_by_key(SHEET_ID)
    return sh.worksheet(SHEET_TAB)

def marcar_publicado(ws, rownum, value=None):
    col = _status_col_for_target()
    valor = value or f"Publicado via {BOT_ORIGEM} em {_ts_br()}"
    ws.update_cell(rownum, col, valor)

# =========================
# X / Twitter — contas e anti-duplicados
# =========================
TW1 = {
    "API_KEY":       os.getenv("TWITTER_API_KEY_1", ""),
    "API_SECRET":    os.getenv("TWITTER_API_SECRET_1", ""),
    "ACCESS_TOKEN":  os.getenv("TWITTER_ACCESS_TOKEN_1", ""),
    "ACCESS_SECRET": os.getenv("TWITTER_ACCESS_SECRET_1", ""),
}
TW2 = {
    "API_KEY":       os.getenv("TWITTER_API_KEY_2", ""),
    "API_SECRET":    os.getenv("TWITTER_API_SECRET_2", ""),
    "ACCESS_TOKEN":  os.getenv("TWITTER_ACCESS_TOKEN_2", ""),
    "ACCESS_SECRET": os.getenv("TWITTER_ACCESS_SECRET_2", ""),
}

class XAccount:
    def __init__(self, label, api_key, api_secret, access_token, access_secret):
        self.label = label
        # v2 (tweet)
        self.client_v2 = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret
        )
        # v1.1 (mídia)
        auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
        self.api_v1 = tweepy.API(auth)
        # identidade
        try:
            me = self.client_v2.get_me()
            self.user_id = me.data.id if me and me.data else None
            self.handle = "@" + (me.data.username if me and me.data else label)
        except Exception:
            self.user_id = None
            self.handle = f"@{label}"

    def __repr__(self):
        return f"<XAccount {self.label} {self.handle} id={self.user_id}>"

def build_x_accounts():
    accs = []
    if all(TW1.values()):
        accs.append(XAccount("ACC1", TW1["API_KEY"], TW1["API_SECRET"], TW1["ACCESS_TOKEN"], TW1["ACCESS_SECRET"]))
    if all(TW2.values()):
        accs.append(XAccount("ACC2", TW2["API_KEY"], TW2["API_SECRET"], TW2["ACCESS_TOKEN"], TW2["ACCESS_SECRET"]))
    if not accs:
        raise RuntimeError("Nenhuma conta X configurada (defina *_1 e/ou *_2).")
    return accs

_recent_tweets_cache = defaultdict(set)
_postados_nesta_execucao = defaultdict(set)

def x_load_recent_texts(acc: XAccount, max_results=50):
    try:
        resp = acc.client_v2.get_users_tweets(
            id=acc.user_id,
            max_results=min(max_results, 100),
            tweet_fields=["created_at", "text"]
        )
        out = set()
        if resp and resp.data:
            for tw in resp.data:
                t = (tw.text or "").strip()
                if t:
                    out.add(t)
        return out
    except Exception as e:
        msg = str(e)
        if "401" in msg or "Unauthorized" in msg:
            _log(f"[{acc.handle}] aviso: ignorando restrição de leitura (401 Unauthorized).")
            return set()
        _log(f"[{acc.handle}] warn: falha ao carregar tweets recentes: {e}")
        return set()

def x_is_dup(acc: XAccount, text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return (t in _recent_tweets_cache[acc.label]) or (t in _postados_nesta_execucao[acc.label])

# =========================
# Inferência de LOGO a partir da coluna E (URL do post)
# =========================
def get_logo_from_url(url: str) -> str | None:
    """Tenta inferir o logo da loteria a partir do path do URL do post."""
    try:
        if not url:
            return None
        p = urlparse(str(url))
        path = (p.path or "").lower()  # e.g. '/2025/10/quina-6865.html'
        # casa diretamente qualquer slug conhecido
        for slug in LOGOS_LOTERIAS.keys():
            slug_norm = slug.replace(' ', '-')
            if slug_norm in path:
                return LOGOS_LOTERIAS.get(slug)
        # fallback: pega o último segmento, remove números finais
        last = path.rstrip('/').split('/')[-1]
        m = re.match(r'([a-z0-9\-]+)', last)
        if m:
            candidate = re.sub(r'-\d+$', '', m.group(1))
            for slug in LOGOS_LOTERIAS.keys():
                if slug.replace(' ', '-').lower() == candidate:
                    return LOGOS_LOTERIAS.get(slug)
        return None
    except Exception:
        return None

# =========================
# Fontes (fallback seguro)
# =========================
def _load_font(size, bold=False):
    try:
        path = "arialbd.ttf" if bold else "arial.ttf"
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

# =========================
# Geração de IMAGEM 3D PROFISSIONAL
# =========================
def gerar_imagem_3d(loteria, concurso, data_br, numeros_str, url_resultado, logo_override=None):
    loteria_lower = (loteria or "").lower().strip()
    cor_hex = CORES_LOTERIAS.get(loteria_lower, "#4B0082")

    # Prioridade de logo:
    # 1) logo_override
    # 2) inferido pelo URL do resultado
    # 3) dicionário pelo nome da loteria
    logo_url = None
    if logo_override and str(logo_override).strip():
        logo_url = str(logo_override).strip()
    else:
        logo_url = get_logo_from_url(url_resultado) or LOGOS_LOTERIAS.get(loteria_lower)

    # Números
    max_numeros = NUMEROS_POR_LOTERIA.get(loteria_lower, 6)
    numeros = [n.strip() for n in str(numeros_str).replace(',', ' ').split() if n.strip()]
    if not numeros:
        numeros = ["?"] * max_numeros
    numeros = numeros[:max_numeros]

    # Canvas
    largura, altura = 880, 900
    img = Image.new('RGB', (largura, altura), color='#ffffff')
    draw = ImageDraw.Draw(img)

    font_titulo = _load_font(56, bold=True)
    font_sub    = _load_font(36, bold=False)
    font_num    = _load_font(50, bold=True)

    y = 40

    # Título e data
    titulo = f"{loteria} — Concurso {concurso}"
    draw.text((60, y), titulo, fill='#0f172a', font=font_titulo)
    y += 80
    draw.text((60, y), f"{data_br}", fill='#475569', font=font_sub)
    y += 70

    # Logo (se disponível)
    if logo_url:
        try:
            r = requests.get(logo_url, timeout=10)
            r.raise_for_status()
            logo_img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            ratio = logo_img.width / logo_img.height
            h = 150
            w = int(h * ratio)
            if w > largura - 120:
                w = largura - 120
                h = int(w / ratio)
            logo_img = logo_img.resize((w, h), Image.Resampling.LANCZOS)
            x_logo = (largura - w) // 2
            img.paste(logo_img, (x_logo, y), logo_img)
            y += h + 40
        except Exception as e:
            _log(f"Logo falhou ({loteria}): {e}")
            y += 20
    else:
        y += 20

    # Paleta
    cor_rgb = tuple(int(cor_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    raio = 64
    espaco = 110
    x_inicio = (largura - (len(numeros) * espaco - espaco//2)) // 2

    # Desenho das bolas 3D
    for i, num in enumerate(numeros):
        x = x_inicio + i * espaco

        # base da bola
        bola = Image.new('RGBA', (raio*2+36, raio*2+36), (0,0,0,0))
        d = ImageDraw.Draw(bola)
        for j in range(raio):
            k = 1.0 - (j/raio)*0.6
            fill = tuple(int(c*k) for c in cor_rgb) + (255,)
            d.ellipse((j, j, raio*2+36 - j*2, raio*2+36 - j*2), fill=fill)

        # brilho
        brilho = Image.new('RGBA', (raio*2+36, raio*2+36), (0,0,0,0))
        db = ImageDraw.Draw(brilho)
        db.ellipse((24, 18, 58, 52), fill=(255,255,255,170))
        bola = Image.alpha_composite(bola, brilho)

        # sombra
        sombra = bola.filter(ImageFilter.GaussianBlur(12))
        img.paste((0,0,0,60), (x-12, y+18), sombra)

        # cola bola
        img.paste(bola, (x-12, y-12), bola)

        # número com leve sombra
        txt_img = Image.new('RGBA', (160,160), (0,0,0,0))
        txt_d = ImageDraw.Draw(txt_img)
        txt_d.text((80, 58), str(num), font=font_num, fill=(0,0,0,210), anchor="mm")
        txt_d.text((78, 56), str(num), font=font_num, fill=(255,255,255,255), anchor="mm")
        img.paste(txt_img, (x-68, y-68), txt_img)

    y += 170

    # URL do resultado
    if url_resultado:
        draw.text((60, y), "Resultado completo:", fill='#0f172a', font=font_sub)
        y += 42
        draw.text((60, y), str(url_resultado), fill='#0ea5e9', font=font_sub)
        y += 60

    # Canais Telegram
    if TELEGRAM_CANAL_1 or TELEGRAM_CANAL_2:
        draw.text((60, y), "Canais no Telegram:", fill='#0f172a', font=font_sub)
        y += 42
        if TELEGRAM_CANAL_1:
            draw.text((80, y), TELEGRAM_CANAL_1, fill='#0284c7', font=font_sub); y += 38
        if TELEGRAM_CANAL_2:
            draw.text((80, y), TELEGRAM_CANAL_2, fill='#0284c7', font=font_sub)

    # Exporta para buffer
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer

# =========================
# Upload de mídia e tweet
# =========================
def x_upload_media_if_any(acc: XAccount, row):
    if not POST_X_WITH_IMAGE:
        return None

    loteria  = row[COL_Loteria-1]  if _safe_len(row, COL_Loteria)  else "Loteria"
    concurso = row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else "0000"
    data_br  = row[COL_Data-1]     if _safe_len(row, COL_Data)     else _now().strftime("%d/%m/%Y")
    numeros  = row[COL_Numeros-1]  if _safe_len(row, COL_Numeros)  else ""
    url_res  = row[COL_URL-1]      if _safe_len(row, COL_URL)      else ""

    # Detecta logo por prioridade: col 6/7 → URL da coluna E → dicionário
    logo_override = None
    if _safe_len(row, COL_URL_Imagem) and str(row[COL_URL_Imagem-1]).strip():
        logo_override = str(row[COL_URL_Imagem-1]).strip()
    elif _safe_len(row, COL_Imagem) and str(row[COL_Imagem-1]).strip():
        logo_override = str(row[COL_Imagem-1]).strip()
    else:
        logo_override = get_logo_from_url(url_res)

    try:
        buffer = gerar_imagem_3d(loteria, concurso, data_br, str(numeros), url_res, logo_override=logo_override)
        media = acc.api_v1.media_upload(filename="resultado.png", file=buffer)
        _log(f"[{acc.handle}] Imagem 3D gerada: {loteria}")
        return [media.media_id_string]
    except Exception as e:
        _log(f"[{acc.handle}] Erro ao gerar/anexar imagem: {e}")
        return None

def x_tweet(acc: XAccount, text: str, media_ids=None):
    t = (text or "").strip()
    if not t:
        return None
    if x_is_dup(acc, t):
        _log(f"[{acc.handle}] SKIP duplicado (cache).")
        return None
    try:
        if media_ids:
            resp = acc.client_v2.create_tweet(text=t, media_ids=media_ids)
        else:
            resp = acc.client_v2.create_tweet(text=t)
        _postados_nesta_execucao[acc.label].add(t)
        _recent_tweets_cache[acc.label].add(t)
        _log(f"[{acc.handle}] OK → {resp.data}")
        return resp
    except tweepy.Forbidden as e:
        _log(f"[{acc.handle}] 403 Forbidden: {e}")
        return None
    except Exception as e:
        _log(f"[{acc.handle}] erro ao postar: {e}")
        return None

# =========================
# Texto do tweet — post ÚNICO (título + números + link + telegram)
# =========================
def montar_corpo_unico(row) -> str:
    loteria  = (row[COL_Loteria-1]  if _safe_len(row, COL_Loteria)  else "").strip()
    concurso = (row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else "").strip()
    data_br  = (row[COL_Data-1]     if _safe_len(row, COL_Data)     else "").strip()
    numeros  = (row[COL_Numeros-1]  if _safe_len(row, COL_Numeros)  else "").strip()
    url      = (row[COL_URL-1]      if _safe_len(row, COL_URL)      else "").strip()

    # normaliza números
    nums = [n.strip() for n in numeros.replace(';', ',').replace('  ', ' ').replace(' ', ',').split(',') if n.strip()]
    nums_str = ", ".join(nums)

    linhas = [f"{loteria} — Concurso {concurso} — ({data_br})"]
    if nums_str:
        linhas.append(f"Números: {nums_str}")
    if url:
        linhas += ["Confira o resultado completo aqui >>", url]
    if TELEGRAM_CANAL_1 or TELEGRAM_CANAL_2:
        linhas += [
            "Inscreva-se nos canais do Telegram e receba as publicações em primeira mão — simples, grátis e divertido:",
        ]
        if TELEGRAM_CANAL_1: linhas.append(TELEGRAM_CANAL_1)
        if TELEGRAM_CANAL_2: linhas.append(TELEGRAM_CANAL_2)

    return "\n".join(linhas).strip()

# =========================
# Coleta de linhas candidatas
# =========================
def coletar_candidatos(ws):
    rows = ws.get_all_values()
    if not rows:
        return []
    data = rows[1:]
    cand = []
    col_status = _status_col_for_target()
    for rindex, row in enumerate(data, start=2):
        if len(row) >= col_status and _not_empty(row[col_status-1]):
            continue
        data_br = row[COL_Data-1] if _safe_len(row, COL_Data) else ""
        if not _within_backlog(data_br, BACKLOG_DAYS):
            continue
        cand.append((rindex, row))
    return cand

# =========================
# Publicação
# =========================
def publicar_linha_em_conta(acc: XAccount, row):
    if acc.label not in _recent_tweets_cache:
        _recent_tweets_cache[acc.label] = x_load_recent_texts(acc, max_results=50)
    texto = montar_corpo_unico(row)
    media_ids = x_upload_media_if_any(acc, row)
    resp = x_tweet(acc, texto, media_ids=media_ids)
    return resp is not None

def publicar_em_x(ws, candidatos):
    contas = build_x_accounts()
    for acc in contas:
        _recent_tweets_cache[acc.label] = x_load_recent_texts(acc, 50)
        _log(f"Conta conectada: {acc.handle}")

    publicados = 0
    acc_idx = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    for rownum, row in candidatos[:limite]:
        ok_any = False
        if X_POST_IN_ALL_ACCOUNTS:
            for acc in contas:
                if publicar_linha_em_conta(acc, row):
                    ok_any = True
                time.sleep(0.7)
        else:
            acc = contas[acc_idx % len(contas)]
            acc_idx += 1
            ok_any = publicar_linha_em_conta(acc, row)

        if ok_any:
            marcar_publicado(ws, rownum)
            publicados += 1

        time.sleep(PAUSA_ENTRE_POSTS)

    _log(f"Resumo: publicados nesta rodada = {publicados}")
    return publicados

# =========================
# Keepalive (opcional)
# =========================
def start_keepalive():
    try:
        from flask import Flask
    except Exception:
        _log("Flask não instalado; keepalive desativado.")
        return None

    app = Flask(__name__)

    @app.route("/")
    def root():
        return "ok", 200

    @app.route("/ping")
    def ping():
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
    _log(f"Iniciando bot... Origem={BOT_ORIGEM} | Rede={TARGET_NETWORK}")
    keepalive_thread = start_keepalive() if ENABLE_KEEPALIVE else None
    try:
        ws = _open_ws()
        candidatos = coletar_candidatos(ws)
        _log(f"Candidatas: {len(candidatos)} (limite {MAX_PUBLICACOES_RODADA})")
        if not candidatos:
            _log("Nenhuma linha candidata.")
            if ENABLE_KEEPALIVE:
                _log("Mantendo vivo para pings...")
                while True:
                    time.sleep(600)
            return
        if TARGET_NETWORK == "X":
            publicar_em_x(ws, candidatos)
        else:
            _log(f"Rede destino '{TARGET_NETWORK}' não implementada.")
        _log("Concluído.")
    except Exception as e:
        _log(f"[FATAL] {e}")
        raise
    finally:
        if ENABLE_KEEPALIVE and keepalive_thread:
            time.sleep(1)

if __name__ == "__main__":
    main()