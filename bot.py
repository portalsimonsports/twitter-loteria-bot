# bot.py — Portal SimonSports — Publicador de Loterias (X/Twitter) + filtros por rede
# Rev: 2025-10-30 — TZ America/Sao_Paulo — FULL + ORIGEM + LOG opcional + DRY_RUN
# - Lê a aba "ImportadosBlogger2" (padrão) da planilha GOOGLE_SHEET_ID
# - Ignora linhas cuja coluna da rede-alvo (H/M/N/O) esteja NÃO VAZIA (qualquer texto)
# - Backlog por Data (dd/mm/aaaa) via BACKLOG_DAYS
# - X (Twitter): round-robin entre 2 contas, Tweepy v2 (tweet) e v1.1 (mídia)
# - Anti-duplicados no X: cache de últimos tweets + cache da execução (evita 403)
# - Marca a planilha após publicar (timestamp + origem) na coluna da rede executada
# - Upload de imagem opcional (POST_X_WITH_IMAGE=true) com import local do Pillow
# - Keepalive Flask opcional (/ e /ping) com ENABLE_KEEPALIVE=true (usa PORT do ambiente)
# - Stubs de Discord/Pinterest/Facebook (sem postar; só prontos p/ expansão)
# - NOVO: BOT_ORIGEM (ou autodetecção), LOG_SHEET_TAB opcional e DRY_RUN

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

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# CONFIG / ENV
# =========================
load_dotenv()
TZ = pytz.timezone("America/Sao_Paulo")

SHEET_ID   = os.getenv("GOOGLE_SHEET_ID", "").strip()
SHEET_TAB  = os.getenv("SHEET_TAB", "ImportadosBlogger2").strip()

# Aba de LOG (opcional). Se definido, cada publicação gera 1 linha no log
LOG_SHEET_TAB = os.getenv("LOG_SHEET_TAB", "").strip()  # ex: "LOG_Publicacoes"

# Rede alvo (X, DISCORD, PINTEREST, FACEBOOK)
TARGET_NETWORK = os.getenv("TARGET_NETWORK", "X").strip().upper()

BACKLOG_DAYS   = int(os.getenv("BACKLOG_DAYS", "2"))
POST_X_WITH_IMAGE = os.getenv("POST_X_WITH_IMAGE", "false").strip().lower() == "true"

# Executa sem postar/sem escrever planilha (para testes)
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() == "true"

# Keepalive (opcional)
ENABLE_KEEPALIVE = os.getenv("ENABLE_KEEPALIVE", "false").strip().lower() == "true"
KEEPALIVE_PORT   = int(os.getenv("KEEPALIVE_PORT", "8080"))

# Lotes e pausas
MAX_PUBLICACOES_RODADA = int(os.getenv("MAX_PUBLICACOES_RODADA", "30"))
PAUSA_ENTRE_POSTS = float(os.getenv("PAUSA_ENTRE_POSTS", "2.0"))

# Origem (explícita) ou autodetecção
def _detect_origem():
    if os.getenv("BOT_ORIGEM"):
        return os.getenv("BOT_ORIGEM").strip()
    # Autodetecção
    if os.getenv("GITHUB_ACTIONS"): return "GitHub"
    if os.getenv("REPL_ID") or os.getenv("REPLIT_DB_URL"): return "Replit"
    if os.getenv("RENDER"): return "Render"
    return "Local"
BOT_ORIGEM = _detect_origem()

# Colunas 1-based (estrutura padrão PSS)
COL_Loteria      = 1
COL_Concurso     = 2
COL_Data         = 3
COL_Numeros      = 4
COL_URL          = 5
COL_URL_Imagem   = 6
COL_Imagem       = 7

# === Mapeamento exato das colunas de status (1-based) ===
# H = 8, M = 13, N = 14, O = 15
COL_STATUS_REDES = {
    "X":          8,  # H → Publicado_X
    "DISCORD":   13,  # M → Publicado_Discord
    "PINTEREST": 14,  # N → Publicado_Pinterest
    "FACEBOOK":  15,  # O → Publicado_Facebook
}

# Chaves do X — Conta 1 e 2 (round-robin)
TW1 = {
    "API_KEY":        os.getenv("TWITTER_API_KEY_1", ""),
    "API_SECRET":     os.getenv("TWITTER_API_SECRET_1", ""),
    "ACCESS_TOKEN":   os.getenv("TWITTER_ACCESS_TOKEN_1", ""),
    "ACCESS_SECRET":  os.getenv("TWITTER_ACCESS_SECRET_1", ""),
}
TW2 = {
    "API_KEY":        os.getenv("TWITTER_API_KEY_2", ""),
    "API_SECRET":     os.getenv("TWITTER_API_SECRET_2", ""),
    "ACCESS_TOKEN":   os.getenv("TWITTER_ACCESS_TOKEN_2", ""),
    "ACCESS_SECRET":  os.getenv("TWITTER_ACCESS_SECRET_2", ""),
}

# =========================
# UTILITÁRIOS
# =========================
def _not_empty(v) -> bool:
    return bool(str(v or "").strip())

def _status_col_for_target() -> int:
    return COL_STATUS_REDES.get(TARGET_NETWORK, 8)

def _now() -> dt.datetime:
    return dt.datetime.now(TZ)

def _ts() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S")

def _ts_br() -> str:
    return _now().strftime("%d/%m/%Y %H:%M")

def _parse_date_br(s: str) -> dt.date | None:
    s = str(s or "").strip()
    if not s:
        return None
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
    today = dt.datetime.now(TZ).date()
    return (today - d).days <= days

def _safe_len(row, idx):
    return len(row) >= idx

def _log(*args):
    print(f"[{_ts()}]", *args, flush=True)

# =========================
# GOOGLE SHEETS
# =========================
def _gs_client():
    sa_json = os.getenv("GOOGLE_SERVICE_JSON", "").strip()
    scopes = ['https://www.googleapis.com/auth/spreadsheets',
              'https://www.googleapis.com/auth/drive']
    if sa_json:
        try:
            info = json.loads(sa_json)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scopes)
        except Exception as e:
            raise RuntimeError(f"GOOGLE_SERVICE_JSON inválido: {e}")
    else:
        if not os.path.exists("service_account.json"):
            raise RuntimeError("Credencial Google ausente (defina GOOGLE_SERVICE_JSON ou service_account.json).")
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scopes)
    return gspread.authorize(creds)

def _open_sh_and_ws():
    if not SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID não definido.")
    gc = _gs_client()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(SHEET_TAB)
    return sh, ws

def marcar_publicado(ws, row_number, value=None):
    col = _status_col_for_target()
    valor = value or f"Publicado via {BOT_ORIGEM} em {_ts_br()}"
    if DRY_RUN:
        _log(f"[DRY_RUN] (não escrever) ws.update_cell({row_number}, {col}, {valor!r})")
        return
    ws.update_cell(row_number, col, valor)

def marcar_status(ws, row_number, status_txt):
    col = _status_col_for_target()
    if DRY_RUN:
        _log(f"[DRY_RUN] (não escrever) ws.update_cell({row_number}, {col}, {status_txt!r})")
        return
    ws.update_cell(row_number, col, status_txt)

def coletar_candidatos(ws):
    rows = ws.get_all_values()
    if not rows:
        return []
    data = rows[1:]
    cand = []
    col_status = _status_col_for_target()

    for r_index, row in enumerate(data, start=2):
        # ignora se a coluna da rede estiver preenchida (qualquer conteúdo)
        if len(row) >= col_status and _not_empty(row[col_status-1]):
            continue
        # respeita janela por Data (C)
        data_br = row[COL_Data-1] if _safe_len(row, COL_Data) else ""
        if not _within_backlog(data_br, BACKLOG_DAYS):
            continue
        cand.append((r_index, row))
    return cand

def log_publicacao(sh, row, network, tweet_url=None, status="OK", erro=None):
    """Escreve uma linha de LOG na aba LOG_SHEET_TAB (se existir/nome definido)."""
    if not LOG_SHEET_TAB:
        return
    try:
        ws_log = sh.worksheet(LOG_SHEET_TAB)
    except Exception:
        _log(f"[LOG] Aba '{LOG_SHEET_TAB}' não encontrada — pulando LOG.")
        return

    loteria  = (row[COL_Loteria-1]  if _safe_len(row, COL_Loteria)  else "").strip()
    concurso = (row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else "").strip()
    data_br  = (row[COL_Data-1]     if _safe_len(row, COL_Data)     else "").strip()
    url      = (row[COL_URL-1]      if _safe_len(row, COL_URL)      else "").strip()
    linha = [
        _ts_br(),          # DataHora
        BOT_ORIGEM,        # Origem (GitHub/Replit/Render/Local)
        network,           # Rede
        loteria,
        concurso,
        data_br,
        url,
        status,
        tweet_url or "",
        (str(erro) if erro else "")
    ]
    if DRY_RUN:
        _log(f"[DRY_RUN] (não escrever) LOG append_row: {linha}")
        return
    try:
        ws_log.append_row(linha, value_input_option="USER_ENTERED")
    except Exception as e:
        _log(f"[LOG] Falha ao gravar log: {e}")

# =========================
# X / TWITTER
# =========================
class XAccount:
    def __init__(self, label, api_key, api_secret, access_token, access_secret):
        self.label = label
        # v2 (tweets)
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

# Anti-duplicados
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
        # Suprime 401 Unauthorized (apenas leitura)
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

def x_upload_media_if_any(acc: XAccount, row, alt_text: str = "") -> list | None:
    if not POST_X_WITH_IMAGE:
        return None

    try:
        from PIL import Image
    except Exception:
        Image = None
        _log(f"[{acc.handle}] aviso: Pillow não instalado; enviando imagem sem validação.")

    url_img = ""
    if _safe_len(row, COL_URL_Imagem) and str(row[COL_URL_Imagem-1]).strip():
        url_img = str(row[COL_URL_Imagem-1]).strip()
    elif _safe_len(row, COL_Imagem) and str(row[COL_Imagem-1]).strip():
        url_img = str(row[COL_Imagem-1]).strip()

    if not url_img:
        return None

    try:
        r = requests.get(url_img, timeout=25)
        r.raise_for_status()
        bio = io.BytesIO(r.content)
        if Image is not None:
            try:
                Image.open(bio).verify()
            except Exception:
                pass
            bio.seek(0)

        if DRY_RUN:
            _log(f"[DRY_RUN] (não enviar) upload mídia de {len(r.content)} bytes")
            return None

        media = acc.api_v1.media_upload(
            filename="loteria.jpg",
            file=bio,
            media_category="tweet_image"
        )
        return [media.media_id_string] if media else None
    except Exception as e:
        _log(f"[{acc.handle}] warn: falha ao anexar imagem: {e}")
        return None

def x_create_tweet(acc: XAccount, text: str, media_ids=None):
    t = (text or "").strip()
    if not t:
        return None
    if x_is_dup(acc, t):
        _log(f"[{acc.handle}] SKIP duplicado (cache).")
        return None
    try:
        if DRY_RUN:
            _log(f"[DRY_RUN] (não postar) Tweet:\n{t}")
            return {"data": {"id": "DRY_RUN"}}

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
# TEXTO E LEGENDA
# =========================
def montar_texto_e_legenda(row) -> tuple[str, str]:
    loteria  = (row[COL_Loteria-1]  if _safe_len(row, COL_Loteria)  else "").strip()
    concurso = (row[COL_Concurso-1] if _safe_len(row, COL_Concurso) else "").strip()
    data_br  = (row[COL_Data-1]     if _safe_len(row, COL_Data)     else "").strip()
    numeros  = (row[COL_Numeros-1]  if _safe_len(row, COL_Numeros)  else "").strip()
    url      = (row[COL_URL-1]      if _safe_len(row, COL_URL)      else "").strip()

    # TÍTULO (ALT TEXT da imagem)
    partes_titulo = []
    if loteria:  partes_titulo.append(loteria)
    if concurso: partes_titulo.append(f"Concurso {concurso}")
    if data_br:  partes_titulo.append(data_br)
    titulo = " - ".join(partes_titulo).strip() or "Resultado da Loteria"

    # LEGENDA (texto do tweet)
    partes_legenda = []
    if numeros:
        nums_formatados = " ".join(numeros.split())
        partes_legenda.append(f"Números: {nums_formatados}")
    if url:
        partes_legenda.append(url)
    partes_legenda.append("#PortalSimonSports")

    legenda = "\n".join(partes_legenda).strip()
    if len(legenda) > 260:
        legenda = legenda[:257] + "..."

    return titulo, legenda

# =========================
# OUTRAS REDES (stubs)
# =========================
def publicar_discord(row, texto) -> bool:
    _log("[Discord] Stub — não implementado.")
    return False

def publicar_pinterest(row, texto) -> bool:
    _log("[Pinterest] Stub — não implementado.")
    return False

def publicar_facebook(row, texto) -> bool:
    _log("[Facebook] Stub — não implementado.")
    return False

# =========================
# KEEPALIVE (para Render/Replit pinger)
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
        # Usa PORT do ambiente (Render/Replit definem PORT)
        port = int(os.getenv("PORT", str(KEEPALIVE_PORT or 5000)))
        app.run(host="0.0.0.0", port=port)

    th = Thread(target=run, daemon=False)  # não-daemon para manter vivo
    th.start()
    _log(f"Keepalive Flask ativo em 0.0.0.0:{os.getenv('PORT', KEEPALIVE_PORT)} (/ e /ping)")
    return th

# =========================
# EXECUÇÃO
# =========================
def publicar_em_x(sh, ws, candidatos):
    contas = build_x_accounts()
    publicados = 0

    for acc in contas:
        _recent_tweets_cache[acc.label] = x_load_recent_texts(acc, max_results=50)
        _log(f"Conta {acc.label} conectada como {acc.handle} (id={acc.user_id}) — cache {len(_recent_tweets_cache[acc.label])} textos")

    acc_idx = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))

    for rownum, row in candidatos[:limite]:
        acc = contas[acc_idx % len(contas)]
        acc_idx += 1

        titulo, legenda = montar_texto_e_legenda(row)
        media_ids = x_upload_media_if_any(acc, row, alt_text=titulo)

        resp = x_create_tweet(acc, legenda, media_ids=media_ids)
        tweet_url = None
        if resp and isinstance(resp, dict):
            # DRY_RUN retorna dict compatível
            tweet_id = (resp.get("data") or {}).get("id")
            if tweet_id and tweet_id != "DRY_RUN":
                tweet_url = f"https://x.com/i/web/status/{tweet_id}"
        elif resp is not None:
            try:
                tweet_id = (resp.data or {}).get("id")
                if tweet_id:
                    tweet_url = f"https://x.com/i/web/status/{tweet_id}"
            except Exception:
                tweet_url = None

        if resp is not None:
            publicados += 1
            marcar_publicado(ws, rownum)
            log_publicacao(sh, row, "X", tweet_url=tweet_url, status="OK")

        time.sleep(PAUSA_ENTRE_POSTS)

    return publicados

def publicar_em_outras_redes(sh, ws, candidatos):
    publicados = 0
    for rownum, row in candidatos[:MAX_PUBLICACOES_RODADA]:
        titulo, legenda = montar_texto_e_legenda(row)
        texto = f"{titulo}\n\n{legenda}"
        ok = False
        if TARGET_NETWORK == "DISCORD":
            ok = publicar_discord(row, texto)
        elif TARGET_NETWORK == "PINTEREST":
            ok = publicar_pinterest(row, texto)
        elif TARGET_NETWORK == "FACEBOOK":
            ok = publicar_facebook(row, texto)

        if ok:
            publicados += 1
            marcar_publicado(ws, rownum)
            log_publicacao(sh, row, TARGET_NETWORK, tweet_url=None, status="OK")
        time.sleep(0.5)
    return publicados

def main():
    _log(f"Implantando... Origem={BOT_ORIGEM} | DRY_RUN={DRY_RUN} | Rede={TARGET_NETWORK}")
    keepalive_thread = None
    if ENABLE_KEEPALIVE:
        keepalive_thread = start_keepalive()

    sh, ws = _open_sh_and_ws()
    candidatos = coletar_candidatos(ws)
    _log(f"Candidatas: {len(candidatos)} (limite {MAX_PUBLICACOES_RODADA})")

    if not candidatos:
        _log("Nenhuma linha candidata.")
        # Mantém processo vivo para o pinger do Render/Replit, se habilitado
        if ENABLE_KEEPALIVE:
            _log("Aguardando pings (KEEPALIVE ativo).")
            try:
                while True:
                    time.sleep(600)
            except KeyboardInterrupt:
                pass
        return

    total = 0
    if TARGET_NETWORK == "X":
        total += publicar_em_x(sh, ws, candidatos)
    else:
        total += publicar_em_outras_redes(sh, ws, candidatos)

    _log(f"Resumo: publicados nesta rodada = {total}")
    # Mesmo após publicar, se KEEPALIVE estiver ativo, mantém vivo:
    if ENABLE_KEEPALIVE:
        _log("Execução concluída. Mantendo processo vivo para pings.")
        try:
            while True:
                time.sleep(600)
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log(f"[FATAL] {e}")
        # Tenta logar a falha (sem parar a subida)
        try:
            sh, _ = _open_sh_and_ws()
            # Como não temos a linha/row aqui, registra um log genérico (se houver LOG_SHEET_TAB)
            if LOG_SHEET_TAB:
                ws_log = sh.worksheet(LOG_SHEET_TAB)
                linha = [_ts_br(), BOT_ORIGEM, TARGET_NETWORK, "", "", "", "", "ERRO", "", str(e)]
                if not DRY_RUN:
                    ws_log.append_row(linha, value_input_option="USER_ENTERED")
                else:
                    _log(f"[DRY_RUN] (não escrever) LOG append_row erro: {linha}")
        except Exception as e2:
            _log(f"[FATAL][LOG] {e2}")
        raise
