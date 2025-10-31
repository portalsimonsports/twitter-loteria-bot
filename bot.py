# bot.py — Portal SimonSports — Publicador de Loterias (X/Twitter) — 1 TWEET (layout unificado)
# Rev: 2025-10-31 — TZ America/Sao_Paulo — FULL (multi-contas, imagem, sem LOG_SHEET_TAB)
# - 1 único tweet com: título + números + link + canais (opcionais) + imagem (coluna 6/7)
# - X_POST_IN_ALL_ACCOUNTS=true: publica a MESMA linha em TODAS as contas; senão, round-robin
# - Anti-duplicados, backlog por data, marcação na planilha e keepalive opcional

import os, io, json, time, pytz, tweepy, requests, datetime as dt
from threading import Thread
from collections import defaultdict
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()
TZ = pytz.timezone("America/Sao_Paulo")

SHEET_ID   = os.getenv("GOOGLE_SHEET_ID", "").strip()
SHEET_TAB  = os.getenv("SHEET_TAB", "ImportadosBlogger2").strip()
TARGET_NETWORK = os.getenv("TARGET_NETWORK", "X").strip().upper()

BACKLOG_DAYS   = int(os.getenv("BACKLOG_DAYS", "2"))
POST_X_WITH_IMAGE = os.getenv("POST_X_WITH_IMAGE", "false").strip().lower() == "true"
X_POST_IN_ALL_ACCOUNTS = os.getenv("X_POST_IN_ALL_ACCOUNTS", "true").strip().lower() == "true"

ENABLE_KEEPALIVE = os.getenv("ENABLE_KEEPALIVE", "false").strip().lower() == "true"
KEEPALIVE_PORT   = int(os.getenv("KEEPALIVE_PORT", "8080"))

MAX_PUBLICACOES_RODADA = int(os.getenv("MAX_PUBLICACOES_RODADA", "30"))
PAUSA_ENTRE_POSTS = float(os.getenv("PAUSA_ENTRE_POSTS", "2.0"))

TELEGRAM_CANAL_1 = (os.getenv("TELEGRAM_CANAL_1", "") or "").strip()
TELEGRAM_CANAL_2 = (os.getenv("TELEGRAM_CANAL_2", "") or "").strip()

def _detect_origem():
    if os.getenv("BOT_ORIGEM"): return os.getenv("BOT_ORIGEM").strip()
    if os.getenv("GITHUB_ACTIONS"): return "GitHub"
    if os.getenv("REPL_ID") or os.getenv("REPLIT_DB_URL"): return "Replit"
    if os.getenv("RENDER"): return "Render"
    return "Local"
BOT_ORIGEM = _detect_origem()

# Colunas 1-based
COL_Loteria, COL_Concurso, COL_Data, COL_Numeros, COL_URL, COL_URL_Imagem, COL_Imagem = 1,2,3,4,5,6,7
COL_STATUS_REDES = {"X":8, "DISCORD":13, "PINTEREST":14, "FACEBOOK":15}

TW1 = {
    "API_KEY":os.getenv("TWITTER_API_KEY_1",""), "API_SECRET":os.getenv("TWITTER_API_SECRET_1",""),
    "ACCESS_TOKEN":os.getenv("TWITTER_ACCESS_TOKEN_1",""), "ACCESS_SECRET":os.getenv("TWITTER_ACCESS_SECRET_1",""),
}
TW2 = {
    "API_KEY":os.getenv("TWITTER_API_KEY_2",""), "API_SECRET":os.getenv("TWITTER_API_SECRET_2",""),
    "ACCESS_TOKEN":os.getenv("TWITTER_ACCESS_TOKEN_2",""), "ACCESS_SECRET":os.getenv("TWITTER_ACCESS_SECRET_2",""),
}

def _not_empty(v): return bool(str(v or "").strip())
def _status_col_for_target(): return COL_STATUS_REDES.get(TARGET_NETWORK,8)
def _now(): return dt.datetime.now(TZ)
def _ts(): return _now().strftime("%Y-%m-%d %H:%M:%S")
def _ts_br(): return _now().strftime("%d/%m/%Y %H:%M")
def _parse_date_br(s):
    s=str(s or "").strip()
    try:
        d,m,y=s.split("/")
        return dt.date(int(y),int(m),int(d))
    except Exception: return None
def _within_backlog(date_br,days):
    if days<=0: return True
    d=_parse_date_br(date_br)
    if not d: return True
    return (_now().date()-d).days<=days
def _safe_len(row,idx): return len(row)>=idx
def _log(*a): print(f"[{_ts()}]",*a,flush=True)

def _gs_client():
    sa_json=os.getenv("GOOGLE_SERVICE_JSON","").strip()
    scopes=['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive']
    if sa_json:
        info=json.loads(sa_json)
        creds=ServiceAccountCredentials.from_json_keyfile_dict(info,scopes)
    else:
        if not os.path.exists("service_account.json"):
            raise RuntimeError("Credencial Google ausente (GOOGLE_SERVICE_JSON ou service_account.json).")
        creds=ServiceAccountCredentials.from_json_keyfile_name("service_account.json",scopes)
    return gspread.authorize(creds)

def _open_ws():
    if not SHEET_ID: raise RuntimeError("GOOGLE_SHEET_ID não definido.")
    sh=_gs_client().open_by_key(SHEET_ID)
    return sh.worksheet(SHEET_TAB)

def marcar_publicado(ws,rownum,value=None):
    col=_status_col_for_target()
    valor=value or f"Publicado via {BOT_ORIGEM} em {_ts_br()}"
    ws.update_cell(rownum,col,valor)

class XAccount:
    def __init__(self,label,api_key,api_secret,access_token,access_secret):
        self.label=label
        self.client_v2=tweepy.Client(consumer_key=api_key,consumer_secret=api_secret,
                                     access_token=access_token,access_token_secret=access_secret)
        auth=tweepy.OAuth1UserHandler(api_key,api_secret,access_token,access_secret)
        self.api_v1=tweepy.API(auth)
        try:
            me=self.client_v2.get_me(); self.user_id=me.data.id if me and me.data else None
            self.handle="@"+(me.data.username if me and me.data else label)
        except Exception:
            self.user_id=None; self.handle=f"@{label}"
    def __repr__(self): return f"<XAccount {self.label} {self.handle} id={self.user_id}>"

def build_x_accounts():
    accs=[]
    if all(TW1.values()): accs.append(XAccount("ACC1",TW1["API_KEY"],TW1["API_SECRET"],TW1["ACCESS_TOKEN"],TW1["ACCESS_SECRET"]))
    if all(TW2.values()): accs.append(XAccount("ACC2",TW2["API_KEY"],TW2["API_SECRET"],TW2["ACCESS_TOKEN"],TW2["ACCESS_SECRET"]))
    if not accs: raise RuntimeError("Nenhuma conta X configurada.")
    return accs

_recent_tweets_cache=defaultdict(set)
_postados_nesta_execucao=defaultdict(set)

def x_load_recent_texts(acc,max_results=50):
    try:
        r=acc.client_v2.get_users_tweets(id=acc.user_id,max_results=min(max_results,100),tweet_fields=["created_at","text"])
        s=set()
        if r and r.data:
            for tw in r.data:
                t=(tw.text or "").strip()
                if t: s.add(t)
        return s
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            _log(f"[{acc.handle}] aviso: leitura 401 ignorada.")
            return set()
        _log(f"[{acc.handle}] warn: cache tweets: {e}"); return set()

def x_is_dup(acc,text):
    t=(text or "").strip()
    return bool(t) and (t in _recent_tweets_cache[acc.label] or t in _postados_nesta_execucao[acc.label])

def _row_img_url(row):
    url=""
    if _safe_len(row,COL_URL_Imagem) and str(row[COL_URL_Imagem-1]).strip():
        url=str(row[COL_URL_Imagem-1]).strip()
    elif _safe_len(row,COL_Imagem) and str(row[COL_Imagem-1]).strip():
        url=str(row[COL_Imagem-1]).strip()
    return url

def x_upload_media_if_any(acc,row,alt_text=""):
    if not POST_X_WITH_IMAGE: return None
    url=_row_img_url(row)
    if not url: return None
    try:
        r=requests.get(url,timeout=25); r.raise_for_status()
        bio=io.BytesIO(r.content)
        media=acc.api_v1.media_upload(filename="loteria.jpg",file=bio,media_category="tweet_image")
        return [media.media_id_string] if media else None
    except Exception as e:
        _log(f"[{acc.handle}] warn: imagem: {e}"); return None

def x_tweet(acc,text,media_ids=None):
    t=(text or "").strip()
    if not t: return None
    if x_is_dup(acc,t): _log(f"[{acc.handle}] SKIP duplicado."); return None
    try:
        r=acc.client_v2.create_tweet(text=t,media_ids=media_ids) if media_ids else acc.client_v2.create_tweet(text=t)
        _postados_nesta_execucao[acc.label].add(t); _recent_tweets_cache[acc.label].add(t)
        _log(f"[{acc.handle}] OK → {r.data}"); return r
    except tweepy.Forbidden as e:
        _log(f"[{acc.handle}] 403: {e}"); return None
    except Exception as e:
        _log(f"[{acc.handle}] erro: {e}"); return None

# -------- Layout: 1 tweet unificado --------
def _fmt_numeros(numeros_raw:str)->str:
    if not numeros_raw: return ""
    if "," in numeros_raw or ";" in numeros_raw:
        parts=[p.strip() for p in numeros_raw.replace(";",",").split(",") if p.strip()]
        return ", ".join(parts)
    return " ".join(numeros_raw.split())

def montar_corpo_unico(row)->str:
    loteria  = (row[COL_Loteria-1]  if _safe_len(row,COL_Loteria)  else "").strip()
    concurso = (row[COL_Concurso-1] if _safe_len(row,COL_Concurso) else "").strip()
    data_br  = (row[COL_Data-1]     if _safe_len(row,COL_Data)     else "").strip()
    numeros  = (row[COL_Numeros-1]  if _safe_len(row,COL_Numeros)  else "").strip()
    url      = (row[COL_URL-1]      if _safe_len(row,COL_URL)      else "").strip()

    linhas = [
        f"🟩 {loteria} — Concurso {concurso} — ({data_br})",
        "🖼️ Imagem oficial da loteria (logo + resultado)" if POST_X_WITH_IMAGE and _row_img_url(row) else "",
        f"🎯 Números: {_fmt_numeros(numeros)}" if numeros else "",
        "",
    ]
    if url:
        linhas += ["Confira o resultado completo aqui 👇", f"🔗 {url}", ""]
    if TELEGRAM_CANAL_1 or TELEGRAM_CANAL_2:
        linhas += ["💬 Inscreva-se nos canais do Telegram e receba as publicações em primeira mão — simples, grátis e divertido:"]
        if TELEGRAM_CANAL_1: linhas.append(f"📢 {TELEGRAM_CANAL_1}")
        if TELEGRAM_CANAL_2: linhas.append(f"📢 {TELEGRAM_CANAL_2}")

    texto="\n".join([l for l in linhas if l!=""]).strip()
    if len(texto)>280:
        # prioriza título, números e link
        base=[]
        for l in [linhas[0],linhas[1] if linhas[1] else None,linhas[2], "", (f"🔗 {url}" if url else "")]:
            if not l: continue
            base.append(l)
            if len("\n".join(base))>265: break
        texto="\n".join([b for b in base if b]).strip()
        if len(texto)>280: texto = texto[:277] + "..."
    return texto

# -------- Coleta / Publicação --------
def coletar_candidatos(ws):
    rows=ws.get_all_values()
    if not rows: return []
    data=rows[1:]; cand=[]; col_status=_status_col_for_target()
    for rindex,row in enumerate(data,start=2):
        if len(row)>=col_status and _not_empty(row[col_status-1]): continue
        data_br=row[COL_Data-1] if _safe_len(row,COL_Data) else ""
        if not _within_backlog(data_br,BACKLOG_DAYS): continue
        cand.append((rindex,row))
    return cand

def publicar_linha_em_conta(acc,row)->bool:
    if acc.label not in _recent_tweets_cache:
        _recent_tweets_cache[acc.label]=x_load_recent_texts(acc,50)
    corpo=montar_corpo_unico(row)
    media_ids=x_upload_media_if_any(acc,row,alt_text=corpo.split("\n",1)[0])
    resp=x_tweet(acc,corpo,media_ids=media_ids)
    return resp is not None

def publicar_em_x(ws,candidatos):
    contas=build_x_accounts()
    publicados=0
    for acc in contas:
        _recent_tweets_cache[acc.label]=x_load_recent_texts(acc,50)
        _log(f"Conta {acc.label} conectada como {acc.handle} (id={acc.user_id}) — cache {len(_recent_tweets_cache[acc.label])} textos")

    acc_idx=0
    limite=min(MAX_PUBLICACOES_RODADA,len(candidatos))
    for rownum,row in candidatos[:limite]:
        ok_any=False
        if X_POST_IN_ALL_ACCOUNTS:
            for acc in contas:
                if publicar_linha_em_conta(acc,row): ok_any=True
                time.sleep(0.7)
        else:
            acc=contas[acc_idx%len(contas)]; acc_idx+=1
            ok_any=publicar_linha_em_conta(acc,row)
        if ok_any:
            publicados+=1
            marcar_publicado(ws,rownum)
        time.sleep(PAUSA_ENTRE_POSTS)
    return publicados

def publicar_em_outras_redes(ws,candidatos):
    _log("Outras redes não implementadas nesta versão."); return 0

# -------- Keepalive (para Render/Replit) --------
def start_keepalive():
    try:
        from flask import Flask
    except Exception:
        _log("Flask não instalado; keepalive desativado."); return None

    app = Flask(__name__)

    @app.get("/")
    def root():
        return ("ok", 200)

    @app.get("/ping")
    def ping():
        return ("ok", 200)

    def run():
        port = int(os.getenv("PORT", str(KEEPALIVE_PORT or 5000)))
        app.run(host="0.0.0.0", port=port)

    th = Thread(target=run, daemon=False)
    th.start()
    _log(f"Keepalive Flask ativo em 0.0.0.0:{os.getenv('PORT', KEEPALIVE_PORT)} (/ e /ping)")
    return th

def main():
    _log(f"Implantando... Origem={BOT_ORIGEM} | Rede={TARGET_NETWORK} | 1-tweet | X_POST_IN_ALL_ACCOUNTS={X_POST_IN_ALL_ACCOUNTS}")
    if ENABLE_KEEPALIVE: start_keepalive()
    ws=_open_ws()
    candidatos=coletar_candidatos(ws)
    _log(f"Candidatas: {len(candidatos)} (limite {MAX_PUBLICACOES_RODADA})")
    if not candidatos:
        _log("Nenhuma linha candidata.")
        if ENABLE_KEEPALIVE:
            while True: time.sleep(600)
        return
    total=publicar_em_x(ws,candidatos) if TARGET_NETWORK=="X" else publicar_em_outras_redes(ws,candidatos)
    _log(f"Resumo: publicados nesta rodada = {total}")

if __name__=="__main__":
    try: main()
    except Exception as e:
        _log(f"[FATAL] {e}")
        raise
