# bot.py — Publicador Loterias + Loteca (thread) — X v2 + redes extras
# Rev: 2025-10-28 — Portal SimonSports
# ---------------------------------------------------------------

import os, json, time, datetime, re, requests, pytz, gspread, tweepy
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# CONFIG INICIAL
# =========================
load_dotenv()
TZ = pytz.timezone("America/Sao_Paulo")

# Planilha
SHEET_ID = "16NcdSwX6q_EQ2XjS1KNIBe6C3Piq-lCBgA38TMszXCI"
ABA      = "ImportadosBlogger2"

# Colunas por rede (1-based). Se os cabeçalhos existirem, detectamos por nome.
COLUNA_X            = 8   # H  -> "Publicados_X"
COLUNA_DISCORD      = 13  # M  -> "Publicado_Discord"
COLUNA_PINTEREST    = 14  # N  -> "Publicado_Pinterest"
COLUNA_FACEBOOK     = 15  # O  -> "Publicado_Facebook"

# Janela e ritmo
def _int(v, dflt): 
    try: return int(str(v).strip())
    except: return dflt

BACKLOG_DAYS          = _int(os.getenv("BACKLOG_DAYS", "1"), 1)
MAX_TWEETS_PER_RUN    = _int(os.getenv("MAX_TWEETS_PER_RUN", "30"), 30)
RATE_DELAY_SECONDS    = _int(os.getenv("RATE_DELAY_SECONDS", "120"), 120)      # pausa entre posts
RATE_BACKOFF_SECONDS  = _int(os.getenv("RATE_BACKOFF_SECONDS", "900"), 900)    # 15 min ao 429
LOOP_MODE             = os.getenv("LOOP_MODE", "false").lower() in {"1","true","yes","on"}
LOOP_INTERVAL_SECONDS = _int(os.getenv("LOOP_INTERVAL_SECONDS", "900"), 900)
PUBLISH_ANYTIME       = os.getenv("PUBLISH_ANYTIME", "true").lower() == "true"

# Links de canais Telegram (para rodapé opcional nos tweets)
TELEGRAM_LINKS = [
    "https://t.me/portalsimonsportsdicasesportivas",
    "https://t.me/portalsimonsports",
]

# Google Sheets
_gsj = os.getenv("GOOGLE_SERVICE_JSON")
if not _gsj:
    raise RuntimeError("Faltando GOOGLE_SERVICE_JSON (cole o JSON inteiro nos Secrets).")
SERVICE_JSON = json.loads(_gsj)

scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(SERVICE_JSON, scope)
gs = gspread.authorize(creds)
WS = gs.open_by_key(SHEET_ID).worksheet(ABA)

# =========================
# HELPERS — planilha e util
# =========================
def limpar(v): 
    return (v or "").strip()

def _first_nonempty(*vals):
    for v in vals:
        if v and str(v).strip(): 
            return str(v).strip()
    return ""

def fetch_rows():
    rows = WS.get_all_values()
    if not rows: 
        return [], [], {}
    hdr = rows[0]
    dados = rows[1:]
    # mapear cabeçalhos -> índice 1-based
    header_map = {}
    usados = {}
    for idx, h in enumerate(hdr, start=1):
        k = (h or "").strip()
        if not k: 
            k = f"col{idx}"
        n = usados.get(k, 0) + 1
        usados[k] = n
        if n > 1:
            k = f"{k}_{n}"
        header_map[k] = idx
    return hdr, dados, header_map

def get_idx(header_map, default_idx, *names):
    for nm in names:
        if nm in header_map: 
            return header_map[nm]
    return default_idx

def linhas_pendentes_por_data(dados, header_map, inicio, hoje):
    # Cabeçalhos relevantes (com fallback)
    idx_loteria = get_idx(header_map, 1, "Loteria")
    idx_conc    = get_idx(header_map, 2, "Concurso")
    idx_data    = get_idx(header_map, 3, "Data")
    idx_nums    = get_idx(header_map, 4, "Números", "Numeros")
    idx_url     = get_idx(header_map, 5, "URL", "Url")
    idx_img     = get_idx(header_map, 7, "IMAGEM", "URL IMAGEM", "Url Imagem", "Imagem")
    idx_x       = get_idx(header_map, COLUNA_X, "Publicados_X")
    idx_discord = get_idx(header_map, COLUNA_DISCORD, "Publicado_Discord")
    idx_pint    = get_idx(header_map, COLUNA_PINTEREST, "Publicado_Pinterest")
    idx_face    = get_idx(header_map, COLUNA_FACEBOOK, "Publicado_Facebook")

    pendentes = []
    for i, row in enumerate(dados, start=2):  # linha real na planilha
        try:
            txt_data = limpar(row[idx_data-1])
            d = datetime.datetime.strptime(txt_data, "%d/%m/%Y").date()
        except:
            continue

        if not (inicio <= d <= hoje):
            continue

        # Empacotar item com todos os índices que usaremos
        item = {
            "linha": i,
            "loteria": limpar(row[idx_loteria-1]),
            "concurso": limpar(row[idx_conc-1]),
            "data_txt": limpar(row[idx_data-1]),
            "numeros": limpar(row[idx_nums-1]),
            "url": limpar(row[idx_url-1]),
            "image_url": limpar(row[idx_img-1]),
            "x_flag": limpar(row[idx_x-1]),
            "dc_flag": limpar(row[idx_discord-1]),
            "pt_flag": limpar(row[idx_pint-1]),
            "fb_flag": limpar(row[idx_face-1]),
            # guardamos índices das colunas p/ atualização
            "col_x": idx_x,
            "col_dc": idx_discord,
            "col_pt": idx_pint,
            "col_fb": idx_face
        }
        pendentes.append(item)
    return pendentes

def marcar(linha, coluna, valor="Sim"):
    # gspread >= update(range_name, values) — ordem de argumentos mudou (emitindo DeprecationWarning)
    WS.update(range_name=f"{_a1(linha, coluna)}", values=[[valor]])

def _a1(lin, col):
    # converte (lin, col) para A1 (ex.: 2,8 -> H2)
    letters = ""
    while col > 0:
        col, rem = divmod(col-1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{lin}"

# =========================
# TEXTO — normal + rodapé
# =========================
EMOJIS = {
    "mega-sena":"💰","lotofácil":"🍀","lotofacil":"🍀","quina":"🎯","lotomania":"🔢",
    "dia de sorte":"🌞","dupla sena":"🎲","super sete":"🎰","loteca":"⚽"
}

def montar_texto_normal(loteria, concurso, data, numeros, url):
    lot = limpar(loteria).title()
    conc = limpar(concurso)
    dt   = limpar(data)
    nums = limpar(numeros).replace(",", " • ")
    link = limpar(url)
    emoji = EMOJIS.get(lot.lower(),"🎟️")

    partes = []
    # Título/link no topo
    if link:
        partes.append(f"Acesse: {link}")
    # Demais infos abaixo do logo (na visualização do X, a imagem/link do post aparece abaixo)
    partes.append(f"{emoji} Resultado da {lot}")
    if conc or dt:
        partes.append(f"🗓️ Concurso {conc} — {dt}".strip(" — "))
    if nums:
        partes.append(f"🔹 Números: {nums}")

    # rodapé com canais (se couber)
    footer = " | ".join([f"Telegram: {t}" for t in TELEGRAM_LINKS])
    corpo  = "\n".join(partes)
    texto  = (corpo + ("\n" + footer if len(corpo) + len("\n"+footer) <= 280 else ""))
    return texto if len(texto) <= 280 else texto[:277] + "..."

# =========================
# LOTECA — formatação e thread
# =========================
def parse_loteca_numeros(numeros_str):
    """
    Espera algo como:
    Palmeiras (BRA) 0 x 0 Cruzeiro (BRA) (Seg 27/10) | Athletico (BRA) 1 x 0 Ceará (BRA) (Seg 27/10) | ...
    Retorna lista de dicts: [{"n":1,"home":"Palmeiras","g1":"0","g2":"0","away":"Cruzeiro","data":"Seg 27/10"}, ...]
    """
    jogos = []
    if not numeros_str:
        return jogos
    pedacos = [p.strip() for p in numeros_str.split("|") if p.strip()]
    # regex captura: Time A ... golsA x golsB Time B ... (Data)
    rx = re.compile(r"^(?P<home>.+?)\s+(\(.+?\))?\s+(?P<g1>\d+)\s*[xX]\s*(?P<g2>\d+)\s+(?P<away>.+?)\s+(\(.+?\))?\s*(?:\((?P<data>[^)]*)\))?$")
    for i, seg in enumerate(pedacos, start=1):
        m = rx.search(seg)
        if not m:
            # fallback burro: "A 1 x 0 B"
            try:
                lados = seg.split("x")
                esq  = lados[0].rsplit(" ", 1)
                dir  = lados[1].split(" ", 1)
                g1   = esq[-1].strip()
                g2   = dir[0].strip()
                home = " ".join(esq[:-1]).strip()
                away = dir[1].strip()
                jogos.append({"n":i,"home":home,"g1":g1,"g2":g2,"away":away,"data":""})
                continue
            except:
                jogos.append({"n":i,"home":seg,"g1":"","g2":"","away":"","data":""})
                continue
        jogos.append({
            "n": i,
            "home": limpar(m.group("home")),
            "g1": limpar(m.group("g1")),
            "g2": limpar(m.group("g2")),
            "away": limpar(m.group("away")),
            "data": limpar(m.group("data") or "")
        })
    return jogos

def montar_thread_loteca(loteria, concurso, data, numeros, url):
    """
    Retorna lista de tweets (2 ou 3 partes).
    Parte 1: título + link
    Parte 2: jogos 1–7 (um por linha)
    Parte 3: jogos 8–14 (um por linha), se necessário
    """
    lot = "Loteca"
    conc = limpar(concurso)
    dt   = limpar(data)
    link = limpar(url)
    jogos = parse_loteca_numeros(numeros)

    header = []
    if link:
        header.append(f"Acesse: {link}")
    header.append(f"⚽ Resultado da {lot}")
    if conc or dt:
        header.append(f"🗓️ Concurso {conc} — {dt}".strip(" — "))

    # rodapé (se couber)
    header_txt = "\n".join(header)
    footer = " | ".join([f"Telegram: {t}" for t in TELEGRAM_LINKS])
    if len(header_txt) + len("\n"+footer) <= 280:
        header_txt = header_txt + "\n" + footer
    elif len(header_txt) > 280:
        header_txt = header_txt[:277] + "..."

    # blocos 1–7 e 8–14
    bloco1 = []
    bloco2 = []
    for j in jogos:
        linha = f"{j['n']}) {j['home']} {j['g1']}–{j['g2']} {j['away']}" + (f" ({j['data']})" if j['data'] else "")
        if j["n"] <= 7: bloco1.append(linha)
        else: bloco2.append(linha)

    body1 = "\n".join(bloco1)[:280]
    partes = [header_txt, body1]

    if bloco2:
        body2 = "\n".join(bloco2)[:280]
        partes.append(body2)

    return partes

# =========================
# X (Twitter) v2 — contas + round-robin
# =========================
def _criar_client_v2(key, secret, token, tokensecret):
    return tweepy.Client(
        consumer_key=key, consumer_secret=secret,
        access_token=token, access_token_secret=tokensecret,
        wait_on_rate_limit=True
    )

def carregar_contas_twitter():
    contas=[]; idx=1
    while True:
        key=os.getenv(f"TWITTER_API_KEY_{idx}")
        sec=os.getenv(f"TWITTER_API_SECRET_{idx}")
        tok=os.getenv(f"TWITTER_ACCESS_TOKEN_{idx}")
        toksec=_first_nonempty(os.getenv(f"TWITTER_ACCESS_SECRET_{idx}"),
                               os.getenv(f"TWITTER_ACCESS_TOKEN_SECRET_{idx}"))
        if not all([key,sec,tok,toksec]): break
        try:
            api=_criar_client_v2(key,sec,tok,toksec)
            me=api.get_me().data; handle=me.username; uid=me.id
            print(f"✅ Conta #{idx} conectada como @{handle} (id={uid})")
            contas.append({"idx":idx,"api":api,"handle":handle})
        except Exception as e:
            print(f"❌ Erro conectando conta #{idx}: {e}")
        idx+=1
    if not contas:
        key=os.getenv("TWITTER_API_KEY"); sec=os.getenv("TWITTER_API_SECRET")
        tok=os.getenv("TWITTER_ACCESS_TOKEN")
        toksec=_first_nonempty(os.getenv("TWITTER_ACCESS_SECRET"),
                               os.getenv("TWITTER_ACCESS_TOKEN_SECRET"))
        if all([key,sec,tok,toksec]):
            try:
                api=_criar_client_v2(key,sec,tok,toksec)
                me=api.get_me().data; handle=me.username; uid=me.id
                print(f"✅ Conta #1 (legacy) conectada como @{handle} (id={uid})")
                contas.append({"idx":1,"api":api,"handle":handle})
            except Exception as e:
                print(f"❌ Erro conectando conta #1 (legacy): {e}")
    if not contas: 
        raise RuntimeError("Nenhuma conta X/Twitter encontrada (tokens v2 ausentes).")
    return contas

CONTAS_TWITTER = carregar_contas_twitter()
RR_IDX = 0  # ponteiro do round-robin

def _tweet_link(handle, tweet_id):
    return f"https://x.com/{handle}/status/{tweet_id}" if handle and tweet_id else ""

def publicar_x_round_robin(texto):
    """Um único tweet. Retorna (ok, link)."""
    global RR_IDX
    n=len(CONTAS_TWITTER)
    if n==0: return False, ""
    tentativas = 0
    start_idx = RR_IDX
    while tentativas < n:
        i = (start_idx + tentativas) % n
        conta = CONTAS_TWITTER[i]
        try:
            resp = conta["api"].create_tweet(text=texto)
            tweet_id = (resp.data or {}).get("id")
            link = _tweet_link(conta["handle"], tweet_id)
            print(f"✅ [X] @{conta['handle']} publicou. {('→ '+link) if link else ''}")
            RR_IDX = (i + 1) % n  # avança o ponteiro só após sucesso
            time.sleep(RATE_DELAY_SECONDS)  # espaçamento entre posts
            return True, link
        except tweepy.TooManyRequests:
            print(f"⏳ [X] 429 @{conta['handle']}: aguardando {RATE_BACKOFF_SECONDS}s")
            time.sleep(RATE_BACKOFF_SECONDS)
            tentativas += 1
        except tweepy.Forbidden as e:
            msg=str(e)
            if "duplicate" in msg.lower():
                print(f"⚠️  [X] Duplicado em @{conta['handle']} — tenta próxima conta.")
            elif "453" in msg or "subset of X API" in msg:
                print(f"❌ [X] Plano/permissão insuficiente em @{conta['handle']}.")
            else:
                print(f"⚠️  [X] Forbidden @{conta['handle']}: {e}")
            tentativas += 1
            time.sleep(5)
        except Exception as e:
            print(f"⚠️  [X] Falha @{conta['handle']}: {e}")
            tentativas += 1
            time.sleep(5)
    return False, ""

def publicar_thread_x(partes):
    """
    Publica uma thread (lista de textos). 
    Retorna (ok, [links]).
    """
    global RR_IDX
    n=len(CONTAS_TWITTER)
    if n==0: return False, []
    tentativas = 0
    start_idx = RR_IDX
    while tentativas < n:
        i = (start_idx + tentativas) % n
        conta = CONTAS_TWITTER[i]
        try:
            links=[]
            prev_id=None
            for k, txt in enumerate(partes, start=1):
                if prev_id:
                    resp = conta["api"].create_tweet(
                        text=txt, 
                        reply={"in_reply_to_tweet_id": prev_id}
                    )
                else:
                    resp = conta["api"].create_tweet(text=txt)
                tweet_id = (resp.data or {}).get("id")
                prev_id = tweet_id
                links.append(_tweet_link(conta["handle"], tweet_id))
                time.sleep(2)  # mini pausa interna
            print(f"✅ [X] Thread publicada por @{conta['handle']}")
            RR_IDX = (i + 1) % n
            time.sleep(RATE_DELAY_SECONDS)
            return True, links
        except tweepy.TooManyRequests:
            print(f"⏳ [X] 429 @{conta['handle']}: aguardando {RATE_BACKOFF_SECONDS}s")
            time.sleep(RATE_BACKOFF_SECONDS)
            tentativas += 1
        except Exception as e:
            print(f"⚠️  [X] Falha thread @{conta['handle']}: {e}")
            tentativas += 1
            time.sleep(5)
    return False, []

# =========================
# REDES GRATUITAS (opcionais)
# =========================
def publicar_discord(texto, image_url):
    hook=os.getenv("DISCORD_WEBHOOK_URL")
    if not hook: return False, ""
    try:
        payload={"content":texto}
        if image_url:
            payload={"content":texto,"embeds":[{"image":{"url":image_url}}]}
        r=requests.post(hook,json=payload,timeout=30)
        ok = (200 <= r.status_code < 300)
        print("📨 Discord:", r.status_code)
        return ok, ""
    except Exception as e: 
        print("⚠️ Discord:", e)
        return False, ""

def publicar_pinterest(texto, image_url):
    tok=os.getenv("PINTEREST_ACCESS_TOKEN"); board=os.getenv("PINTEREST_BOARD_ID")
    if not (tok and board and image_url): return False, ""
    try:
        url="https://api.pinterest.com/v5/pins"
        hdr={"Authorization":f"Bearer {tok}"}
        data={"board_id":board,"title":(texto.split("\n")[0])[:100],
              "description":texto[:300],"media_source":{"source_type":"image_url","url":image_url}}
        r=requests.post(url,headers=hdr,json=data,timeout=30)
        ok = (200 <= r.status_code < 300)
        print("📨 Pinterest:", r.status_code)
        return ok, ""
    except Exception as e: 
        print("⚠️ Pinterest:", e)
        return False, ""

def publicar_facebook(texto, image_url):
    page=os.getenv("FB_PAGE_ID"); token=os.getenv("FB_PAGE_ACCESS_TOKEN")
    if not (page and token and image_url): return False, ""
    try:
        r=requests.post(f"https://graph.facebook.com/{page}/photos",
                        data={"url":image_url,"caption":texto,"access_token":token},
                        timeout=30)
        ok = (200 <= r.status_code < 300)
        print("📨 Facebook:", r.status_code)
        return ok, ""
    except Exception as e: 
        print("⚠️ Facebook:", e)
        return False, ""

# =========================
# EXECUÇÃO
# =========================
def publicar_em_redes(item, texto, image_url):
    """
    Publica nas redes faltantes (colunas vazias). 
    Marca cada rede individualmente ao sucesso.
    """
    linha = item["linha"]

    # X
    if not item["x_flag"]:
        ok_x = False
        link_x = ""
        if item["loteria"].lower() == "loteca":
            partes = montar_thread_loteca(item["loteria"], item["concurso"], item["data_txt"], item["numeros"], item["url"])
            ok_x, links = publicar_thread_x(partes)
            link_x = links[0] if links else ""
        else:
            ok_x, link_x = publicar_x_round_robin(texto)
        if ok_x:
            marcar(linha, item["col_x"], "Sim")
            print(f"✅ Planilha: marcado X em {_a1(linha, item['col_x'])} — {link_x}")

    # Discord
    if not item["dc_flag"]:
        ok, _ = publicar_discord(texto, image_url)
        if ok:
            marcar(linha, item["col_dc"], "Sim")
            print(f"✅ Planilha: marcado Discord em {_a1(linha, item['col_dc'])}")

    # Pinterest
    if not item["pt_flag"]:
        ok, _ = publicar_pinterest(texto, image_url)
        if ok:
            marcar(linha, item["col_pt"], "Sim")
            print(f"✅ Planilha: marcado Pinterest em {_a1(linha, item['col_pt'])}")

    # Facebook
    if not item["fb_flag"]:
        ok, _ = publicar_facebook(texto, image_url)
        if ok:
            marcar(linha, item["col_fb"], "Sim")
            print(f"✅ Planilha: marcado Facebook em {_a1(linha, item['col_fb'])}")

def run_once():
    agora = datetime.datetime.now(TZ)
    if not PUBLISH_ANYTIME:
        if agora.hour < 22 or (agora.hour == 22 and agora.minute < 45):
            print("⏳ Aguardando 22h45 para publicação...")
            return

    hoje = agora.date()
    inicio = hoje - datetime.timedelta(days=max(BACKLOG_DAYS, 0))

    hdr, dados, header_map = fetch_rows()
    if not dados:
        print("✅ Planilha vazia.")
        return

    pend = linhas_pendentes_por_data(dados, header_map, inicio, hoje)
    if not pend:
        print("✅ Nenhuma pendência elegível encontrada.")
        return

    print(f"📅 Janela: {inicio.strftime('%d/%m/%Y')} → {hoje.strftime('%d/%m/%Y')}")
    print(f"📝 Candidatas: {len(pend)} (limite {MAX_TWEETS_PER_RUN})")

    publicados_no_run = 0
    for item in pend:
        if publicados_no_run >= MAX_TWEETS_PER_RUN:
            print(f"⛔ Limite por execução atingido ({MAX_TWEETS_PER_RUN}).")
            break

        loteria   = item["loteria"]
        concurso  = item["concurso"]
        data_txt  = item["data_txt"]
        numeros   = item["numeros"]
        url       = item["url"]
        image_url = item["image_url"]

        # Texto principal (para X e redes extras)
        if loteria.lower() == "loteca":
            # Para o X já montamos a thread dentro de publicar_em_redes()
            # Para redes extras, montamos um resumo compacto (primeiras 3 linhas)
            jogos = parse_loteca_numeros(numeros)
            linhas = [f"{j['n']}) {j['home']} {j['g1']}–{j['g2']} {j['away']}" for j in jogos[:3]]
            resumo = "\n".join(linhas)
            texto = f"Acesse: {url}\n⚽ Resultado da Loteca\n🗓️ Concurso {concurso} — {data_txt}\n{resumo}..."
        else:
            texto = montar_texto_normal(loteria, concurso, data_txt, numeros, url)

        publicar_em_redes(item, texto, image_url)
        publicados_no_run += 1

    print(f"🔎 Resumo: publicados nesta rodada = {publicados_no_run}")

# =========================
# ENTRYPOINT
# =========================
if __name__ == "__main__":
    if LOOP_MODE:
        print(f"🔁 LOOP_MODE ativo — checando pendências a cada {LOOP_INTERVAL_SECONDS}s")
        while True:
            run_once()
            print(f"⏳ Aguardando {LOOP_INTERVAL_SECONDS}s …")
            time.sleep(LOOP_INTERVAL_SECONDS)
    else:
        run_once()
