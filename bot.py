# bot.py — Publicação automática (Twitter v2 + Telegram + Discord + Pinterest + Facebook)
# Texto padronizado com "Confira:" no topo, regra 22h45, planilha ImportadosBlogger2
import os
import json
import time
import gspread
import datetime
import pytz
import tweepy
import requests
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# CONFIG INICIAL
# =========================
load_dotenv()
TZ = pytz.timezone("America/Sao_Paulo")

SHEET_ID = "16NcdSwX6q_EQ2XjS1KNIBe6C3Piq-lCBgA38TMszXCI"
ABA = "ImportadosBlogger2"
COLUNA_PUBLICADOS = 8  # H (1-based)

def _int(v, dflt):
    try:
        return int(str(v).strip())
    except Exception:
        return dflt

BACKLOG_DAYS = _int(os.getenv("BACKLOG_DAYS", "0"), 0)

# Limites/pausas anti rate-limit
MAX_TWEETS_PER_RUN = _int(os.getenv("MAX_TWEETS_PER_RUN", "30"), 30)     # máx por execução
RATE_DELAY_SECONDS = _int(os.getenv("RATE_DELAY_SECONDS", "75"), 75)     # pausa entre tweets
RATE_BACKOFF_SECONDS = _int(os.getenv("RATE_BACKOFF_SECONDS", "900"), 900)  # espera após 429 (15min)

# =========================
# GOOGLE SERVICE JSON
# =========================
_gsj = os.getenv("GOOGLE_SERVICE_JSON")
if not _gsj:
    raise RuntimeError(
        "Faltando secret GOOGLE_SERVICE_JSON. "
        "No Replit/Render, adicione o conteúdo do JSON inteiro na key GOOGLE_SERVICE_JSON."
    )
try:
    SERVICE_JSON = json.loads(_gsj)
except Exception as e:
    raise RuntimeError("GOOGLE_SERVICE_JSON inválido (não é JSON).") from e

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(SERVICE_JSON, scope)
gs = gspread.authorize(creds)
SHEET = gs.open_by_key(SHEET_ID)
ABA_DADOS = SHEET.worksheet(ABA)

# =========================
# HELPERS
# =========================
def _first_nonempty(*vals):
    for v in vals:
        if v and str(v).strip():
            return str(v).strip()
    return ""

def limpar_lista(val):
    return (val or "").strip()

def ler_registros_sem_duplicados():
    rows = ABA_DADOS.get_all_values()
    if not rows:
        return []
    header_raw = rows[0]
    usados, headers = {}, []
    for h in header_raw:
        k = (h or "").strip() or "col"
        n = usados.get(k, 0) + 1
        usados[k] = n
        if n > 1:
            k = f"{k}_{n}"
        headers.append(k)
    return [dict(zip(headers, r)) for r in rows[1:]]

def _depois_2245(agora):
    return (agora.hour > 22) or (agora.hour == 22 and agora.minute >= 45)

# =========================
# TEXTO DA POSTAGEM (com "Confira:")
# =========================
EMOJIS = {
    "mega-sena": "💰",
    "lotofácil": "🍀",
    "lotofacil": "🍀",
    "quina": "🎯",
    "lotomania": "🔢",
    "dia de sorte": "🌞",
    "dupla sena": "🎲",
    "super sete": "🎰",
    "loteca": "⚽",
}

def montar_texto(loteria, concurso, data, numeros, url):
    loteria_fmt = limpar_lista(loteria).title()
    concurso_fmt = limpar_lista(concurso)
    data_fmt = limpar_lista(data)
    numeros_fmt = limpar_lista(numeros).replace(",", " • ")
    url_fmt = limpar_lista(url)

    emoji = EMOJIS.get(loteria_fmt.lower(), "🎟️")
    # "Confira:" como PRIMEIRA linha
    partes = []
    if url_fmt:
        partes.append(f"Confira: {url_fmt}")
    partes.append(f"{emoji} Resultado da {loteria_fmt}")
    if concurso_fmt or data_fmt:
        partes.append(f"📅 Concurso {concurso_fmt} — {data_fmt}".strip(" — "))
    if numeros_fmt:
        partes.append(f"🔹 Números: {numeros_fmt}")
    # Hashtags
    if loteria_fmt:
        partes.append(f"#LoteriasCaixa #{loteria_fmt.replace(' ', '')} #PortalSimonSports")

    texto = "\n".join(partes)
    if len(texto) > 280:
        texto = texto[:277] + "..."
    return texto

# =========================
# TWITTER v2 (multi-contas)
# =========================
def _criar_client_v2(key, secret, token, tokensecret):
    return tweepy.Client(
        consumer_key=key,
        consumer_secret=secret,
        access_token=token,
        access_token_secret=tokensecret,
        wait_on_rate_limit=True
    )

def carregar_contas_twitter():
    contas = []
    idx = 1
    while True:
        key = os.getenv(f"TWITTER_API_KEY_{idx}")
        sec = os.getenv(f"TWITTER_API_SECRET_{idx}")
        tok = os.getenv(f"TWITTER_ACCESS_TOKEN_{idx}")
        toksec = _first_nonempty(
            os.getenv(f"TWITTER_ACCESS_TOKEN_SECRET_{idx}"),
            os.getenv(f"TWITTER_ACCESS_SECRET_{idx}")
        )
        if not all([key, sec, tok, toksec]):
            break
        try:
            api = _criar_client_v2(key, sec, tok, toksec)
            me = api.get_me().data
            handle = me.username
            uid = me.id
            print(f"✅ Conta #{idx} conectada como @{handle} (id={uid})")
            contas.append({"idx": idx, "api": api, "handle": handle})
        except Exception as e:
            print(f"❌ Erro conectando conta #{idx}: {e}")
        idx += 1

    if not contas:
        key = os.getenv("TWITTER_API_KEY")
        sec = os.getenv("TWITTER_API_SECRET")
        tok = os.getenv("TWITTER_ACCESS_TOKEN")
        toksec = _first_nonempty(
            os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
            os.getenv("TWITTER_ACCESS_SECRET")
        )
        if all([key, sec, tok, toksec]):
            try:
                api = _criar_client_v2(key, sec, tok, toksec)
                me = api.get_me().data
                handle = me.username
                uid = me.id
                print(f"✅ Conta #1 (legacy) conectada como @{handle} (id={uid})")
                contas.append({"idx": 1, "api": api, "handle": handle})
            except Exception as e:
                print(f"❌ Erro conectando conta #1 (legacy): {e}")

    if not contas:
        raise RuntimeError("Nenhuma conta X/Twitter encontrada (tokens v2 ausentes).")
    return contas

CONTAS_TWITTER = carregar_contas_twitter()

def _tweet_link(handle, tweet_id):
    return f"https://x.com/{handle}/status/{tweet_id}" if handle and tweet_id else ""

# =========================
# PUBLICADORES GRATUITOS (opcionais)
# =========================
def publicar_telegram(texto, image_url):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return
    try:
        if image_url:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "photo": image_url, "caption": texto}
            )
        else:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": texto}
            )
        print("📨 Telegram:", resp.status_code)
    except Exception as e:
        print("⚠️ Telegram erro:", e)

def publicar_discord(texto, image_url):
    webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook:
        return
    try:
        payload = {"content": texto}
        if image_url:
            payload = {"content": texto, "embeds": [{"image": {"url": image_url}}]}
        resp = requests.post(webhook, json=payload)
        print("📨 Discord:", resp.status_code)
    except Exception as e:
        print("⚠️ Discord erro:", e)

def publicar_pinterest(texto, image_url):
    token = os.getenv("PINTEREST_ACCESS_TOKEN")
    board_id = os.getenv("PINTEREST_BOARD_ID")
    if not (token and board_id and image_url):
        return
    try:
        url = "https://api.pinterest.com/v5/pins"
        headers = {"Authorization": f"Bearer {token}"}
        data = {
            "board_id": board_id,
            "title": (texto.split("\n")[1] if "\n" in texto else texto)[:100],
            "description": texto[:300],
            "media_source": {"source_type": "image_url", "url": image_url}
        }
        resp = requests.post(url, headers=headers, json=data)
        print("📨 Pinterest:", resp.status_code, str(resp.text)[:120])
    except Exception as e:
        print("⚠️ Pinterest erro:", e)

def publicar_facebook(texto, image_url):
    page_id = os.getenv("FB_PAGE_ID")
    page_token = os.getenv("FB_PAGE_ACCESS_TOKEN")
    if not (page_id and page_token and image_url):
        return
    try:
        url = f"https://graph.facebook.com/{page_id}/photos"
        resp = requests.post(url, data={
            "url": image_url,
            "caption": texto,
            "access_token": page_token
        })
        print("📨 Facebook:", resp.status_code, str(resp.text)[:120])
    except Exception as e:
        print("⚠️ Facebook erro:", e)

# =========================
# REGISTRO DE PUBLICAÇÃO
# =========================
def registrar_publicacao(linha, loteria, concurso, url_postagem, link_primeira_conta=""):
    ABA_DADOS.update_cell(linha, COLUNA_PUBLICADOS, "Sim")
    print(f"✅ Marcado como Publicado: {loteria} {concurso}")
    if link_primeira_conta:
        print(f"🔗 Link (1ª conta): {link_primeira_conta}")
    from datetime import datetime as _dt
    with open("log_publicacoes.txt", "a", encoding="utf-8") as log:
        log.write(f"{_dt.now()} | {loteria} {concurso} | {url_postagem} | {link_primeira_conta}\n")

# =========================
# LOOP PRINCIPAL
# =========================
def run_once(force=False):
    agora = datetime.datetime.now(TZ)
    force_env = (os.getenv("FORCE_PUBLISH", "false").lower() in {"1", "true", "yes", "on"})
    if not (force or force_env) and not _depois_2245(agora):
        print("⏳ Aguardando 22h45 para iniciar publicação...")
        return

    dados = ler_registros_sem_duplicados()

    hoje = agora.date()
    inicio = hoje - datetime.timedelta(days=max(BACKLOG_DAYS, 0))
    print(f"📅 Janela de publicação: {inicio.strftime('%d/%m/%Y')} → {hoje.strftime('%d/%m/%Y')} (BACKLOG_DAYS={BACKLOG_DAYS})")

    candidatos = 0
    publicados = 0
    postados_no_run = 0

    for i, row in enumerate(dados, start=2):
        if (row.get("Publicados") or "").strip():
            continue

        data_txt = (row.get("Data") or "").strip()
        try:
            d = datetime.datetime.strptime(data_txt, "%d/%m/%Y").date()
        except Exception:
            continue
        if not (inicio <= d <= hoje):
            continue

        loteria = (row.get("Loteria") or "").strip()
        if loteria.lower() == "loteca":
            continue

        if postados_no_run >= MAX_TWEETS_PER_RUN:
            print(f"⛔ Limite por execução atingido (MAX_TWEETS_PER_RUN={MAX_TWEETS_PER_RUN}). Encerrando.")
            break

        numeros  = row.get("Números") or row.get("Numeros") or ""
        url      = row.get("URL") or row.get("Url") or ""
        concurso = (row.get("Concurso") or "").strip()
        image_url = (row.get("URL IMAGEM") or row.get("Url Imagem") or row.get("Imagem") or "").strip()

        texto = montar_texto(loteria, concurso, data_txt, numeros, url)
        candidatos += 1
        sucesso_alguma_conta = False
        first_link = ""

        # ====== TWITTER v2 (todas as contas carregadas)
        for conta in CONTAS_TWITTER:
            try:
                resp = conta["api"].create_tweet(text=texto)
                tweet_id = (resp.data or {}).get("id")
                link = _tweet_link(conta["handle"], tweet_id)
                print(f"✅ [X] @{conta['handle']}: {loteria} {concurso} {('→ '+link) if link else ''}")
                if not first_link and link:
                    first_link = link
                sucesso_alguma_conta = True
                postados_no_run += 1
                # pausa amigável entre tweets
                time.sleep(RATE_DELAY_SECONDS)
            except tweepy.TooManyRequests as e:
                print(f"⏳ [X] Rate limit @{conta['handle']}: {e} — aguardando {RATE_BACKOFF_SECONDS}s")
                time.sleep(RATE_BACKOFF_SECONDS)
            except tweepy.Forbidden as e:
                msg = str(e)
                if "453" in msg or "subset of X API" in msg:
                    print(f"❌ [X] Plano/permissão não permite post para @{conta['handle']}.")
                elif "duplicate" in msg.lower():
                    print(f"⚠️  [X] Conteúdo duplicado em @{conta['handle']}.")
                else:
                    print(f"⚠️  [X] Forbidden @{conta['handle']}: {e}")
            except Exception as e:
                print(f"⚠️  [X] Falha @{conta['handle']}: {e}")

            if postados_no_run >= MAX_TWEETS_PER_RUN:
                break

        # ====== OUTRAS REDES (opcionais — só rodam se houver Secrets)
        try:
            publicar_telegram(texto, image_url)
            publicar_discord(texto, image_url)
            publicar_pinterest(texto, image_url)
            publicar_facebook(texto, image_url)
        except Exception as e:
            print("⚠️ Erro em redes extras:", e)

        if sucesso_alguma_conta:
            registrar_publicacao(i, loteria, concurso, url, first_link)
            publicados += 1
        else:
            print(f"❌ Nenhuma conta publicou: {loteria} {concurso}")

        if postados_no_run >= MAX_TWEETS_PER_RUN:
            print(f"⛔ Limite por execução atingido (MAX_TWEETS_PER_RUN={MAX_TWEETS_PER_RUN}). Encerrando.")
            break

    print(f"🔎 Resumo: candidatos={candidatos}, publicados={publicados}")

# =========================
# ENTRYPOINT
# =========================
def publicar():
    # Produção: force=False (respeita 22h45). Para testes, defina FORCE_PUBLISH=true nos Secrets.
    run_once(force=False)

if __name__ == "__main__":
    publicar()