# bot.py — Portal SimonSports — Publicador Automático de Loterias no X (Twitter)
# Rev: 2025-10-31 — TODAS AS LOTERIAS + NÚMEROS 3D + LOGO OFICIAL + KEEPALIVE SEGURO
# Inclui: Mega-Sena, Quina, Lotofácil, Lotomania, Timemania, Dupla Sena,
#         Federal, Dia de Sorte, SUPER SETE, LOTECA

import os
import io
import json
import time
import pytz
import tweepy
import requests
import datetime as dt
from threading import Thread
from collections import defaultdict
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image, ImageDraw, ImageFont, ImageFilter

load_dotenv()
TZ = pytz.timezone("America/Sao_Paulo")

# === CONFIGURAÇÕES ===
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
SHEET_TAB = os.getenv("SHEET_TAB", "ImportadosBlogger2").strip()
TARGET_NETWORK = os.getenv("TARGET_NETWORK", "X").strip().upper()

BACKLOG_DAYS = int(os.getenv("BACKLOG_DAYS", "2"))
X_POST_IN_ALL_ACCOUNTS = os.getenv("X_POST_IN_ALL_ACCOUNTS", "true").strip().lower() == "true"
POST_X_WITH_IMAGE = os.getenv("POST_X_WITH_IMAGE", "true").strip().lower() == "true"

ENABLE_KEEPALIVE = os.getenv("ENABLE_KEEPALIVE", "false").strip().lower() == "true"
KEEPALIVE_PORT = int(os.getenv("KEEPALIVE_PORT", "8080"))

MAX_PUBLICACOES_RODADA = int(os.getenv("MAX_PUBLICACOES_RODADA", "30"))
PAUSA_ENTRE_POSTS = float(os.getenv("PAUSA_ENTRE_POSTS", "2.5"))

# === CANAIS DO TELEGRAM ===
TELEGRAM_CANAL_1 = os.getenv("TELEGRAM_CANAL_1", "https://t.me/portalsimonsportsdicasesportivas")
TELEGRAM_CANAL_2 = os.getenv("TELEGRAM_CANAL_2", "https://t.me/portalsimonsports")

# === LOTERIAS DA CAIXA ===
CORES_LOTERIAS = {
    "mega-sena": "#006400",
    "quina": "#4B0082",
    "lotofácil": "#DD4A91",
    "lotomania": "#FF8C00",
    "timemania": "#00FF00",
    "dupla sena": "#000080",
    "federal": "#8B4513",
    "dia de sorte": "#FFD700",
    "super sete": "#FF4500",   # Laranja
    "loteca": "#006400",       # Verde
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
    "mega-sena": 6,
    "quina": 5,
    "lotofácil": 15,
    "lotomania": 20,
    "timemania": 10,
    "dupla sena": 6,
    "federal": 5,
    "dia de sorte": 7,
    "super sete": 7,
    "loteca": 14,
}

# === DETECÇÃO DE ORIGEM ===
def _detect_origem():
    if os.getenv("BOT_ORIGEM"): return os.getenv("BOT_ORIGEM").strip()
    if os.getenv("GITHUB_ACTIONS"): return "GitHub"
    if os.getenv("REPL_ID") or os.getenv("REPLIT_DB_URL"): return "Replit"
    if os.getenv("RENDER"): return "Render"
    return "Local"
BOT_ORIGEM = _detect_origem()

# === COLUNAS DA PLANILHA (1-based) ===
COL_Loteria, COL_Concurso, COL_Data, COL_Numeros, COL_URL = 1, 2, 3, 4, 5
COL_STATUS_REDES = {"X": 8}

# === CONTAS DO X (TWITTER) ===
TW1 = {
    "API_KEY": os.getenv("TWITTER_API_KEY_1", ""),
    "API_SECRET": os.getenv("TWITTER_API_SECRET_1", ""),
    "ACCESS_TOKEN": os.getenv("TWITTER_ACCESS_TOKEN_1", ""),
    "ACCESS_SECRET": os.getenv("TWITTER_ACCESS_SECRET_1", ""),
}
TW2 = {
    "API_KEY": os.getenv("TWITTER_API_KEY_2", ""),
    "API_SECRET": os.getenv("TWITTER_API_SECRET_2", ""),
    "ACCESS_TOKEN": os.getenv("TWITTER_ACCESS_TOKEN_2", ""),
    "ACCESS_SECRET": os.getenv("TWITTER_ACCESS_SECRET_2", ""),
}

# === FUNÇÕES AUXILIARES ===
def _not_empty(v): return bool(str(v or "").strip())
def _status_col_for_target(): return COL_STATUS_REDES.get(TARGET_NETWORK, 8)
def _now(): return dt.datetime.now(TZ)
def _ts(): return _now().strftime("%Y-%m-%d %H:%M:%S")
def _ts_br(): return _now().strftime("%d/%m/%Y %H:%M")
def _parse_date_br(s):
    s = str(s or "").strip()
    try:
        d, m, y = s.split("/")
        return dt.date(int(y), int(m), int(d))
    except Exception:
        return None
def _within_backlog(date_br, days):
    if days <= 0: return True
    d = _parse_date_br(date_br)
    if not d: return True
    return (_now().date() - d).days <= days
def _safe_len(row, idx): return len(row) >= idx
def _log(*a): print(f"[{_ts()}]", *a, flush=True)

# === GOOGLE SHEETS ===
def _gs_client():
    sa_json = os.getenv("GOOGLE_SERVICE_JSON", "").strip()
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    if sa_json:
        info = json.loads(sa_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scopes)
    else:
        if not os.path.exists("service_account.json"):
            raise RuntimeError("Credencial Google ausente: service_account.json ou GOOGLE_SERVICE_JSON")
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scopes)
    return gspread.authorize(creds)

def _open_ws():
    if not SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID não definido no .env")
    sh = _gs_client().open_by_key(SHEET_ID)
    return sh.worksheet(SHEET_TAB)

def marcar_publicado(ws, rownum):
    col = _status_col_for_target()
    ws.update_cell(rownum, col, f"Publicado via {BOT_ORIGEM} em {_ts_br()}")

# === CONTAS DO X ===
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
    if all(TW1.values()): accs.append(XAccount("ACC1", **TW1))
    if all(TW2.values()): accs.append(XAccount("ACC2", **TW2))
    if not accs:
        raise RuntimeError("Nenhuma conta X configurada. Verifique as chaves no .env")
    return accs

# === CACHE DE TWEETS ===
_recent_tweets_cache = defaultdict(set)
_postados_nesta_execucao = defaultdict(set)

def x_load_recent_texts(acc, max_results=50):
    try:
        r = acc.client_v2.get_users_tweets(id=acc.user_id, max_results=min(max_results, 100), tweet_fields=["text"])
        s = set()
        if r and r.data:
            for tw in r.data:
                t = (tw.text or "").strip()
                if t: s.add(t)
        return s
    except Exception:
        return set()

def x_is_dup(acc, text):
    t = (text or "").strip()
    return bool(t) and (t in _recent_tweets_cache[acc.label] or t in _postados_nesta_execucao[acc.label])

# === GERA IMAGEM 3D COM LOGO OFICIAL ===
def gerar_imagem_3d(loteria, concurso, data_br, numeros_str, url_resultado):
    loteria_lower = loteria.lower().strip()
    cor_hex = CORES_LOTERIAS.get(loteria_lower, "#4B0082")
    logo_url = LOGOS_LOTERIAS.get(loteria_lower)
    max_numeros = NUMEROS_POR_LOTERIA.get(loteria_lower, 6)

    numeros = [n.strip() for n in numeros_str.replace(',', ' ').split() if n.strip()]
    if not numeros: numeros = ["?"] * max_numeros
    numeros = numeros[:max_numeros]

    largura, altura = 800, 780
    img = Image.new('RGB', (largura, altura), color='#f8f9fa')
    draw = ImageDraw.Draw(img)

    try:
        font_titulo = ImageFont.truetype("arialbd.ttf", 56)
        font_num = ImageFont.truetype("arialbd.ttf", 52)
        font_texto = ImageFont.truetype("arial.ttf", 36)
    except:
        font_titulo = ImageFont.load_default()
        font_num = font_titulo
        font_texto = font_titulo

    y = 40

    # Título
    titulo = f"{loteria} — Concurso {concurso} — ({data_br})"
    draw.text((50, y), titulo, fill='#000000', font=font_titulo)
    y += 90

    # Logo
    if logo_url:
        try:
            r = requests.get(logo_url, timeout=10)
            logo_img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            ratio = logo_img.width / logo_img.height
            nova_altura = 160
            nova_largura = int(nova_altura * ratio)
            logo_img = logo_img.resize((nova_largura, nova_altura), Image.Resampling.LANCZOS)
            x_logo = (largura - nova_largura) // 2
            img.paste(logo_img, (x_logo, y), logo_img)
            y += 180
        except Exception as e:
            _log(f"Logo falhou ({loteria}): {e}")
            y += 60
    else:
        y += 60

    # Números 3D
    raio = 58
    espaco = 105
    x_inicio = (largura - (len(numeros) * espaco - espaco // 2)) // 2
    cor_rgb = tuple(int(cor_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

    for i, num in enumerate(numeros):
        x = x_inicio + i * espaco

        # Bola 3D
        bola = Image.new('RGBA', (raio*2+30, raio*2+30), (0,0,0,0))
        d = ImageDraw.Draw(bola)
        for j in range(raio):
            intensidade = 1 - j / raio * 0.5
            fill = tuple(int(c * intensidade) for c in cor_rgb) + (255,)
            d.ellipse((j, j, raio*2+30-j*2, raio*2+30-j*2), fill=fill)

        # Sombra
        sombra = bola.filter(ImageFilter.GaussianBlur(10))
        img.paste((0,0,0,70), (x-8, y+12), sombra)

        # Colar bola
        img.paste(bola, (x-8, y-8), bola)

        # Número 3D
        txt_img = Image.new('RGBA', (120,120), (0,0,0,0))
        txt_d = ImageDraw.Draw(txt_img)
        txt_d.text((60, 38), num, font=font_num, fill=(0,0,0,180), anchor="mm")
        txt_d.text((58, 36), num, font=font_num, fill=(255,255,255,255), anchor="mm")
        img.paste(txt_img, (x-60, y-60), txt_img)

    y += 150

    # Link
    if url_resultado:
        draw.text((50, y), url_resultado, fill='#0066cc', font=font_texto)
        y += 60

    # Canais Telegram
    draw.text((50, y), "Canais no Telegram:", fill='#000000', font=font_texto)
    y += 50
    draw.text((70, y), TELEGRAM_CANAL_1, fill='#0088cc', font=font_texto)
    y += 45
    draw.text((70, y), TELEGRAM_CANAL_2, fill='#0088cc', font=font_texto)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# === UPLOAD E TWEET ===
def x_upload_media_if_any(acc, row):
    if not POST_X_WITH_IMAGE:
        return None
    loteria = row[COL_Loteria-1] if _safe_len(row, COL_Loteria) else "Loteria"
    concurso = row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else "0000"
    data_br = row[COL_Data-1] if _safe_len(row, COL_Data) else _now().strftime("%d/%m/%Y")
    numeros = row[COL_Numeros-1] if _safe_len(row, COL_Numeros) else ""
    url = row[COL_URL-1] if _safe_len(row, COL_URL) else ""

    try:
        buffer = gerar_imagem_3d(loteria, concurso, data_br, str(numeros), url)
        media = acc.api_v1.media_upload(filename="resultado.png", file=buffer)
        _log(f"[{acc.handle}] Imagem 3D gerada: {loteria}")
        return [media.media_id_string]
    except Exception as e:
        _log(f"[{acc.handle}] Erro ao gerar imagem: {e}")
        return None

def x_tweet(acc, text, media_ids=None):
    t = (text or "").strip()
    if not t or x_is_dup(acc, t):
        return None
    try:
        r = acc.client_v2.create_tweet(text=t, media_ids=media_ids) if media_ids else acc.client_v2.create_tweet(text=t)
        _postados_nesta_execucao[acc.label].add(t)
        _recent_tweets_cache[acc.label].add(t)
        _log(f"[{acc.handle}] Publicado com sucesso!")
        return r
    except Exception as e:
        _log(f"[{acc.handle}] Erro ao publicar: {e}")
        return None

# === MONTAR TEXTO ===
def montar_corpo_unico(row):
    loteria = row[COL_Loteria-1] if _safe_len(row, COL_Loteria) else ""
    concurso = row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else ""
    data_br = row[COL_Data-1] if _safe_len(row, COL_Data) else ""
    numeros = row[COL_Numeros-1] if _safe_len(row, COL_Numeros) else ""
    url = row[COL_URL-1] if _safe_len(row, COL_URL) else ""

    nums_lista = [n.strip() for n in str(numeros).split(',') if n.strip()]
    nums_str = ', '.join(nums_lista)

    linhas = [
        f"{loteria} — Concurso {concurso} — ({data_br})",
        f"Números: {nums_str}" if nums_str else "",
        "",
    ]
    if url:
        linhas += [url, ""]
    if TELEGRAM_CANAL_1 or TELEGRAM_CANAL_2:
        linhas += ["Canais no Telegram:"]
        if TELEGRAM_CANAL_1: linhas.append(TELEGRAM_CANAL_1)
        if TELEGRAM_CANAL_2: linhas.append(TELEGRAM_CANAL_2)

    return "\n".join([l for l in linhas if l]).strip()

# === COLETAR CANDIDATOS ===
def coletar_candidatos(ws):
    rows = ws.get_all_values()
    if not rows: return []
    data = rows[1:]
    cand = []
    col_status = _status_col_for_target()
    for rindex, row in enumerate(data, start=2):
        if len(row) >= col_status and _not_empty(row[col_status-1]): continue
        data_br = row[COL_Data-1] if _safe_len(row, COL_Data) else ""
        if not _within_backlog(data_br, BACKLOG_DAYS): continue
        cand.append((rindex, row))
    return cand

# === PUBLICAR ===
def publicar_linha_em_conta(acc, row):
    if acc.label not in _recent_tweets_cache:
        _recent_tweets_cache[acc.label] = x_load_recent_texts(acc, 50)
    corpo = montar_corpo_unico(row)
    media_ids = x_upload_media_if_any(acc, row)
    resp = x_tweet(acc, corpo, media_ids=media_ids)
    return resp is not None

def publicar_em_x(ws, candidatos):
    contas = build_x_accounts()
    for acc in contas:
        _recent_tweets_cache[acc.label] = x_load_recent_texts(acc, 50)
        _log(f"Conta conectada: {acc.handle}")

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
        time.sleep(PAUSA_ENTRE_POSTS)

# === KEEPALIVE SEGURO ===
def start_keepalive():
    try:
        from flask import Flask
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
        _log(f"Keepalive ativo na porta {os.getenv('PORT', KEEPALIVE_PORT)}")
        return th
    except ImportError:
        _log("Flask não instalado. Keepalive desativado.")
        return None
    except Exception as e:
        _log(f"Erro no keepalive: {e}")
        return None

# === MAIN ===
def main():
    _log(f"Iniciando bot... Origem={BOT_ORIGEM}")
    keepalive_thread = None
    if ENABLE_KEEPALIVE:
        keepalive_thread = start_keepalive()

    try:
        ws = _open_ws()
        candidatos = coletar_candidatos(ws)
        _log(f"Linhas candidatas: {len(candidatos)}")
        if not candidatos:
            _log("Nenhuma linha para publicar.")
            if ENABLE_KEEPALIVE:
                while True: time.sleep(600)
            return
        publicar_em_x(ws, candidatos)
        _log("Publicação finalizada com sucesso.")
    except Exception as e:
        _log(f"[FATAL] {e}")
        raise
    finally:
        if ENABLE_KEEPALIVE and keepalive_thread:
            time.sleep(1)

if __name__ == "__main__":
    main()