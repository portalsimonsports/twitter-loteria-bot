# bot.py — Portal SimonSports — Publicador Automático (X, Facebook, Telegram, Discord, Pinterest)
# Rev: 2025-11-28 — CREDENCIAIS 100% via COFRE (Sheets) + criação automática de colunas Publicado_<REDE>
# Regras:
# - Publica SEM filtro de data: se a coluna da rede estiver vazia, publica.
# - Lê credenciais de: COFRE_SHEET_ID / abas (Credenciais_Rede, Redes_Sociais_Canais).
# - Usa apenas estes Secrets no GitHub: GOOGLE_SERVICE_JSON, GOOGLE_SHEET_ID, SHEET_TAB,
#   COFRE_SHEET_ID, COFRE_ABA_CRED, COFRE_ABA_CANAIS, DRY_RUN, MAX_PUBLICACOES_RODADA, PAUSA_ENTRE_POSTS, colunas.
#
# Dependências: gspread, google-auth, requests, tweepy
# (as mesmas já usadas no repositório; se faltar, adicione no requirements)

import os
import re
import io
import json
import time
import math
import pytz
import queue
import base64
import random
import string
import logging
import datetime as dt
from typing import Dict, List, Tuple, Any

import requests

# Tweepy é usado para X (Twitter). Mantém compatibilidade com o repo.
try:
    import tweepy
except Exception:
    tweepy = None

# Google Sheets (autenticação via service account JSON no Secret)
import gspread
from google.oauth2.service_account import Credentials

TZ = os.getenv("TZ", "America/Sao_Paulo")
BR_TZ = pytz.timezone(TZ)

# ==============================
# Utilidades de log
# ==============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def now_str():
    return dt.datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M")

def sanitize(s):
    if s is None:
        return ""
    return str(s).strip()

def normalize_key(k: str) -> str:
    k = sanitize(k)
    k = k.replace(" ", "_").replace("-", "_")
    k = re.sub(r"__+", "_", k)
    return k.upper()

# ==============================
# Config (apenas planilhas e limites)
# ==============================
GOOGLE_SHEET_ID     = os.getenv("GOOGLE_SHEET_ID", "").strip()
SHEET_TAB           = os.getenv("SHEET_TAB", "ImportadosBlogger2").strip()

COFRE_SHEET_ID      = os.getenv("COFRE_SHEET_ID", "").strip()
COFRE_ABA_CRED      = os.getenv("COFRE_ABA_CRED", "Credenciais_Rede").strip()
COFRE_ABA_CANAIS    = os.getenv("COFRE_ABA_CANAIS", "Redes_Sociais_Canais").strip()

MAX_PUBLICACOES     = int(os.getenv("MAX_PUBLICACOES_RODADA", "30"))
PAUSA_ENTRE_POSTS   = float(os.getenv("PAUSA_ENTRE_POSTS", "2.0"))
DRY_RUN             = os.getenv("DRY_RUN", "false").lower() == "true"

# Índices de colunas (1-based)
COL_STATUS_X         = int(os.getenv("COL_STATUS_X", "8"))
COL_STATUS_TELEGRAM  = int(os.getenv("COL_STATUS_TELEGRAM", "10"))
COL_STATUS_DISCORD   = int(os.getenv("COL_STATUS_DISCORD", "13"))
COL_STATUS_PINTEREST = int(os.getenv("COL_STATUS_PINTEREST", "14"))
COL_STATUS_FACEBOOK  = int(os.getenv("COL_STATUS_FACEBOOK", "15"))

SUPPORTED = ["X", "FACEBOOK", "TELEGRAM", "DISCORD", "PINTEREST"]

# ==============================
# Conexão Google Sheets
# ==============================
def gs_client():
    raw = os.getenv("GOOGLE_SERVICE_JSON", "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_JSON não definido no Secret.")
    try:
        data = json.loads(raw)
    except Exception:
        # pode ter sido salvo sem as barras duplas \n — tenta consertar
        fixed = raw.replace('\\n', '\n')
        data = json.loads(fixed)
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive.readonly"]
    creds = Credentials.from_service_account_info(data, scopes=scopes)
    return gspread.authorize(creds)

def open_sheet(sheet_id: str, tab: str):
    gc = gs_client()
    ss = gc.open_by_key(sheet_id)
    return ss.worksheet(tab)

# ==============================
# Leitura do Cofre
# ==============================
def ler_cofre_credenciais() -> Dict[str, Dict[str, str]]:
    """
    Retorna:
      {
        "X":          {"TWITTER_API_KEY_1": "...", "TWITTER_ACCESS_TOKEN_1": "...", ...},
        "FACEBOOK":   {"PAGE_ID_1": "...", "PAGE_TOKEN_1": "...", ...},
        "TELEGRAM":   {"TG_BOT_TOKEN": "..."},
        "DISCORD":    {"DISCORD_WEBHOOKS": "..."},
        "PINTEREST":  {"ACCESS_TOKEN": "...", "BOARD_ID": "...", ...},
      }
    """
    if not COFRE_SHEET_ID:
        logging.info("COFRE_SHEET_ID não definido. Nenhuma credencial será lida do Cofre.")
        return {}

    try:
        w = open_sheet(COFRE_SHEET_ID, COFRE_ABA_CRED)
    except Exception as e:
        logging.error(f"Falha ao abrir Cofre [{COFRE_ABA_CRED}]: {e}")
        return {}

    rows = w.get_all_values()
    if not rows:
        return {}

    # Head esperado: Rede | Conta | Chave | Valor
    header = [normalize_key(h) for h in rows[0]]
    col_map = {h:i for i,h in enumerate(header)}
    req = ["REDE", "CONTA", "CHAVE", "VALOR"]
    if not all(k in col_map for k in req):
        logging.warning("Cabeçalho do Cofre não bate com 'Rede | Conta | Chave | Valor'.")
        return {}

    data: Dict[str, Dict[str, str]] = {}
    for r in rows[1:]:
        rede  = sanitize(r[col_map["REDE"]]).upper()
        chave = normalize_key(r[col_map["CHAVE"]])
        valor = sanitize(r[col_map["VALOR"]])
        if not rede or not chave or not valor:
            continue
        if rede not in SUPPORTED and rede.lower() not in ["planilhas google", "github"]:
            # ignora outras linhas
            continue
        if rede.upper() not in data:
            data[rede.upper()] = {}
        data[rede.upper()][chave] = valor

    return data

def ler_cofre_canais_telegram() -> List[str]:
    """
    Lê aba Redes_Sociais_Canais e devolve os 2 primeiros URLs ativos de Telegram (ordem ASC).
    Colunas esperadas: Ativo | Ordem | Rede | Tipo | Nome_Exibição | URL
    """
    urls: List[str] = []
    if not COFRE_SHEET_ID:
        return urls
    try:
        w = open_sheet(COFRE_SHEET_ID, COFRE_ABA_CANAIS)
        rows = w.get_all_values()
        if not rows:
            return urls
        header = [normalize_key(h) for h in rows[0]]
        col = {h:i for i,h in enumerate(header)}
        needed = ["ATIVO", "ORDEM", "REDE", "TIPO", "URL"]
        if not all(k in col for k in needed):
            return urls

        # filtra Telegram ativos
        temp = []
        for r in rows[1:]:
            ativo = sanitize(r[col["ATIVO"]]).lower() in ["sim", "yes", "true", "1", "x"]
            rede  = sanitize(r[col["REDE"]]).lower()
            url   = sanitize(r[col["URL"]])
            ordem = sanitize(r[col["ORDEM"]])
            if not ativo or "telegram" not in rede or not url:
                continue
            try:
                ordem_i = int(ordem)
            except Exception:
                ordem_i = 9999
            temp.append((ordem_i, url))
        temp.sort(key=lambda x: x[0])
        urls = [u for _,u in temp[:2]]
        return urls
    except Exception as e:
        logging.warning(f"Erro lendo Cofre canais Telegram: {e}")
        return urls

# ==============================
# Leitura da planilha de Publicações
# ==============================
def get_pub_sheet():
    if not GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID não definido.")
    return open_sheet(GOOGLE_SHEET_ID, SHEET_TAB)

def ensure_status_columns(ws, required: Dict[str, int]):
    """
    Garante que existam colunas 'Publicado_<REDE>' nos índices definidos.
    Se a planilha já tem cabeçalho, só preenche a célula do cabeçalho.
    """
    vals = ws.row_values(1)
    max_len = max(len(vals), max(required.values()))
    if len(vals) < max_len:
        # completa a linha 1 para ter colunas suficientes
        padding = [""] * (max_len - len(vals))
        ws.update_cell(1, len(vals)+1, "")  # assegura a edição
        if padding:
            # gspread não atualiza múltiplas em branco facilmente; abaixo atualizamos nominalmente
            pass

    # escreve os cabeçalhos
    inv = {v:k for k,v in required.items()}
    cell_updates = []
    for col_idx, rede in inv.items():
        header_name = f"Publicado_{rede}"
        cur = ws.cell(1, col_idx).value or ""
        if cur.strip() != header_name:
            cell_updates.append({"range": gspread.utils.rowcol_to_a1(1, col_idx), "values": [[header_name]]})
    if cell_updates:
        ws.batch_update([{"range": u["range"], "values": u["values"]} for u in cell_updates], value_input_option="USER_ENTERED")

def fetch_rows_to_publish(ws, col_status: int, limit: int) -> List[Tuple[int, Dict[str, Any]]]:
    """
    Retorna lista [(row_index, row_dict), ...] até 'limit', onde a célula da rede está vazia.
    Considera colunas: A=Loteria, B=Concurso, C=Data, D=Números, E=URL, (opcionais: URL IMAGEM / IMAGEM)
    """
    all_vals = ws.get_all_values()
    if not all_vals or len(all_vals) < 2:
        return []

    header = [sanitize(h) for h in all_vals[0]]
    # mapeia colunas
    idx = {h:i for i,h in enumerate(header)}
    def get(row, name, default=""):
        i = idx.get(name, None)
        return sanitize(row[i]) if (i is not None and i < len(row)) else default

    rows_out = []
    for i, row in enumerate(all_vals[1:], start=2):
        # status vazio?
        st = ""
        if col_status <= len(row):
            st = sanitize(row[col_status-1])
        if st != "":
            continue

        item = {
            "row": i,
            "loteria": get(row, "Loteria"),
            "concurso": get(row, "Concurso"),
            "data": get(row, "Data"),
            "numeros": get(row, "Números"),
            "url": get(row, "URL"),
            "url_imagem": get(row, "URL IMAGEM") or get(row, "Link da Imagem") or "",
            "imagem": get(row, "IMAGEM") or "",
        }
        rows_out.append((i, item))
        if len(rows_out) >= limit:
            break

    return rows_out

def mark_published(ws, row_idx: int, col_status: int, rede: str, origem="Cofre"):
    ws.update_cell(row_idx, col_status, f"Publicado {rede} via {origem} em {now_str()}")

# ==============================
# Postagens — implementações simples e robustas
# ==============================

# ---- X (Twitter)
def post_x(creds: Dict[str, str], text: str, image_url: str = "") -> bool:
    if not tweepy:
        logging.error("tweepy não disponível. Instale para postar no X.")
        return False

    # Conta 1 obrigatória
    k1 = creds.get("TWITTER_API_KEY_1") or creds.get("API_KEY_1")
    s1 = creds.get("TWITTER_API_SECRET_1") or creds.get("API_SECRET_1")
    t1 = creds.get("TWITTER_ACCESS_TOKEN_1")
    ts1= creds.get("TWITTER_ACCESS_SECRET_1")

    if not all([k1, s1, t1, ts1]):
        logging.error("Credenciais X (conta 1) ausentes no Cofre.")
        return False

    ok_any = False
    def _post(k, s, t, ts):
        try:
            auth = tweepy.OAuth1UserHandler(k, s, t, ts)
            api = tweepy.API(auth)
            if image_url:
                # download da imagem para upload
                resp = requests.get(image_url, timeout=30)
                resp.raise_for_status()
                with io.BytesIO(resp.content) as f:
                    media = api.media_upload(filename="img.jpg", file=f)
                api.update_status(status=text, media_ids=[media.media_id])
            else:
                api.update_status(status=text)
            return True
        except Exception as e:
            logging.error(f"X falhou: {e}")
            return False

    ok_any |= _post(k1, s1, t1, ts1)

    # conta 2 (se existir)
    k2 = creds.get("TWITTER_API_KEY_2") or creds.get("API_KEY_2")
    s2 = creds.get("TWITTER_API_SECRET_2") or creds.get("API_SECRET_2")
    t2 = creds.get("TWITTER_ACCESS_TOKEN_2")
    ts2= creds.get("TWITTER_ACCESS_SECRET_2")
    if k2 and s2 and t2 and ts2:
        ok_any |= _post(k2, s2, t2, ts2)

    return ok_any

# ---- Telegram
def post_telegram(creds: Dict[str,str], text: str, image_url: str, canais_defaults: List[str]) -> bool:
    bot_token = creds.get("TG_BOT_TOKEN") or creds.get("TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_TOKEN", "")
    if not bot_token:
        logging.error("TG_BOT_TOKEN não encontrado no Cofre nem no Secret.")
        return False

    # Canais do Cofre (aba canais)
    chat_ids = []
    # além dos defaults (URLs), aceita ID numérico em TG_CHAT_IDS (Secret) como fallback
    for u in canais_defaults:
        # aceita t.me/xxx -> @xxx
        m = re.search(r"t\.me/([a-zA-Z0-9_]+)", u)
        if m:
            chat_ids.append("@"+m.group(1))

    extra_ids = os.getenv("TG_CHAT_IDS", "").strip()
    if extra_ids:
        for cid in extra_ids.split(","):
            cid = cid.strip()
            if cid:
                chat_ids.append(cid)

    chat_ids = list(dict.fromkeys(chat_ids))[:2]  # max 2

    if not chat_ids:
        logging.warning("Nenhum canal Telegram ativo no Cofre; nada a postar.")
        return False

    ok = False
    for cid in chat_ids:
        try:
            if image_url:
                url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                payload = {"chat_id": cid, "photo": image_url, "caption": text}
            else:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {"chat_id": cid, "text": text}
            if DRY_RUN:
                logging.info(f"[DRY] Telegram -> {cid}: {text}")
                ok = True
                continue
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code // 100 == 2:
                ok = True
            else:
                logging.error(f"Telegram erro ({cid}): {r.status_code} {r.text[:200]}")
        except Exception as e:
            logging.error(f"Telegram exceção ({cid}): {e}")
    return ok

# ---- Discord
def post_discord(creds: Dict[str,str], text: str, image_url: str="") -> bool:
    webhooks = creds.get("DISCORD_WEBHOOKS", "")
    if not webhooks:
        logging.error("DISCORD_WEBHOOKS não encontrado no Cofre.")
        return False
    ok = False
    for wh in [w.strip() for w in webhooks.split(",") if w.strip()]:
        try:
            payload = {"content": text}
            if DRY_RUN:
                logging.info(f"[DRY] Discord -> {wh}: {text}")
                ok = True
                continue
            r = requests.post(wh, json=payload, timeout=30)
            if r.status_code // 100 == 2:
                ok = True
            else:
                logging.error(f"Discord erro: {r.status_code} {r.text[:200]}")
        except Exception as e:
            logging.error(f"Discord exceção: {e}")
    return ok

# ---- Pinterest (v5) — requer imagem
def post_pinterest(creds: Dict[str,str], link_url: str, image_url: str) -> bool:
    token = creds.get("ACCESS_TOKEN") or creds.get("PINTEREST_ACCESS_TOKEN")
    board = creds.get("BOARD_ID") or creds.get("PINTEREST_BOARD_ID")
    if not token or not board:
        logging.error("Pinterest ACCESS_TOKEN/BOARD_ID ausentes no Cofre.")
        return False
    if not image_url:
        logging.error("Pinterest exige imagem (URL IMAGEM/IMAGEM).")
        return False
    try:
        url = "https://api.pinterest.com/v5/pins"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "board_id": board,
            "title": "Resultado de Loteria",
            "link": link_url,
            "media_source": {"source_type": "image_url", "url": image_url}
        }
        if DRY_RUN:
            logging.info(f"[DRY] Pinterest -> board {board} | {link_url} | {image_url}")
            return True
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        if r.status_code // 100 == 2:
            return True
        logging.error(f"Pinterest erro: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        logging.error(f"Pinterest exceção: {e}")
        return False

# ---- Facebook (Page) — requer PAGE_ID_1 + PAGE_TOKEN_1
def post_facebook(creds: Dict[str,str], text: str, image_url: str, link_url: str) -> bool:
    page_token = creds.get("PAGE_TOKEN_1") or creds.get("PAGE_ACCESS_TOKEN_1") or creds.get("TOKEN_DE_ACESSO_1")
    page_id    = creds.get("PAGE_ID_1") or creds.get("PAGEID_1") or ""

    if not page_token:
        logging.error("Facebook: PAGE_TOKEN_1 (ou Token_de_Acesso_1) não encontrado no Cofre.")
        return False

    # descobre page_id se não veio
    try:
        if not page_id:
            r = requests.get("https://graph.facebook.com/v20.0/me/accounts",
                             params={"access_token": page_token}, timeout=30)
            if r.status_code // 100 == 2:
                data = r.json().get("data", [])
                if data:
                    page_id = data[0]["id"]
            if not page_id:
                logging.error("Facebook: não consegui obter PAGE_ID com o token informado.")
                return False

        if image_url:
            # publica foto com legenda
            url = f"https://graph.facebook.com/v20.0/{page_id}/photos"
            payload = {"url": image_url, "caption": text, "access_token": page_token}
        else:
            # publica post com link (feed)
            url = f"https://graph.facebook.com/v20.0/{page_id}/feed"
            payload = {"message": text + ("\n" + link_url if link_url else ""), "access_token": page_token}

        if DRY_RUN:
            logging.info(f"[DRY] Facebook -> {page_id}: {payload}")
            return True

        r = requests.post(url, data=payload, timeout=60)
        if r.status_code // 100 == 2:
            return True
        logging.error(f"Facebook erro: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        logging.error(f"Facebook exceção: {e}")
        return False

# ==============================
# Mensagem
# ==============================
def montar_texto(item: Dict[str,Any]) -> Tuple[str, str]:
    """
    Retorna (texto, link) — texto enxuto aprovado (apenas o link na maioria das redes).
    """
    link = item.get("url","")
    # Texto minimalista para reduzir rejeições das APIs
    texto = link or ""
    return texto, link

def escolher_imagem(item: Dict[str,Any]) -> str:
    # Prefere "URL IMAGEM" se vier preenchido; senão, tenta "IMAGEM" (pode ser caminho/URL)
    return item.get("url_imagem") or item.get("imagem") or ""

# ==============================
# Main
# ==============================
def main():
    logging.info("=== Portal SimonSports | Publicador Automático (via COFRE) ===")
    logging.info(f"SHEET: {GOOGLE_SHEET_ID} | TAB: {SHEET_TAB}")
    if not COFRE_SHEET_ID:
        logging.warning("ATENÇÃO: COFRE_SHEET_ID vazio — sem credenciais de rede!")

    # carrega cofre
    cofre = ler_cofre_credenciais()
    canais_tg = ler_cofre_canais_telegram()

    # redes com credenciais válidas no cofre
    redes_ok = []
    for r in SUPPORTED:
        if r in cofre and len(cofre[r])>0:
            redes_ok.append(r)

    if not redes_ok:
        logging.error("Nenhuma rede ativa encontrada no Cofre. Nada a publicar.")
        return

    ws = get_pub_sheet()
    ensure_status_columns(ws, {
        "X": COL_STATUS_X,
        "TELEGRAM": COL_STATUS_TELEGRAM,
        "DISCORD": COL_STATUS_DISCORD,
        "PINTEREST": COL_STATUS_PINTEREST,
        "FACEBOOK": COL_STATUS_FACEBOOK,
    })

    publicados_total = 0

    # Publica X
    if "X" in redes_ok:
        rows = fetch_rows_to_publish(ws, COL_STATUS_X, MAX_PUBLICACOES)
        for row_idx, item in rows:
            texto, link = montar_texto(item)
            img = escolher_imagem(item)
            ok = post_x(cofre["X"], texto, img)
            if ok:
                mark_published(ws, row_idx, COL_STATUS_X, "X")
                publicados_total += 1
                time.sleep(PAUSA_ENTRE_POSTS)

    # Telegram
    if "TELEGRAM" in redes_ok:
        rows = fetch_rows_to_publish(ws, COL_STATUS_TELEGRAM, MAX_PUBLICACOES)
        for row_idx, item in rows:
            texto, link = montar_texto(item)
            img = escolher_imagem(item)
            ok = post_telegram(cofre["TELEGRAM"], texto, img, canais_tg)
            if ok:
                mark_published(ws, row_idx, COL_STATUS_TELEGRAM, "Telegram")
                publicados_total += 1
                time.sleep(PAUSA_ENTRE_POSTS)

    # Discord
    if "DISCORD" in redes_ok:
        rows = fetch_rows_to_publish(ws, COL_STATUS_DISCORD, MAX_PUBLICACOES)
        for row_idx, item in rows:
            texto, link = montar_texto(item)
            img = escolher_imagem(item)
            ok = post_discord(cofre["DISCORD"], texto, img)
            if ok:
                mark_published(ws, row_idx, COL_STATUS_DISCORD, "Discord")
                publicados_total += 1
                time.sleep(PAUSA_ENTRE_POSTS)

    # Pinterest (exige imagem)
    if "PINTEREST" in redes_ok:
        rows = fetch_rows_to_publish(ws, COL_STATUS_PINTEREST, MAX_PUBLICACOES)
        for row_idx, item in rows:
            texto, link = montar_texto(item)
            img = escolher_imagem(item)
            ok = post_pinterest(cofre["PINTEREST"], link, img)
            if ok:
                mark_published(ws, row_idx, COL_STATUS_PINTEREST, "Pinterest")
                publicados_total += 1
                time.sleep(PAUSA_ENTRE_POSTS)

    # Facebook (Page)
    if "FACEBOOK" in redes_ok:
        rows = fetch_rows_to_publish(ws, COL_STATUS_FACEBOOK, MAX_PUBLICACOES)
        for row_idx, item in rows:
            texto, link = montar_texto(item)
            img = escolher_imagem(item)
            ok = post_facebook(cofre["FACEBOOK"], texto, img, link)
            if ok:
                mark_published(ws, row_idx, COL_STATUS_FACEBOOK, "Facebook")
                publicados_total += 1
                time.sleep(PAUSA_ENTRE_POSTS)

    logging.info(f"Concluído. Publicações efetuadas: {publicados_total}")

if __name__ == "__main__":
    main()