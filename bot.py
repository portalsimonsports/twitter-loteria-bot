# bot.py — Portal SimonSports — Publicador Automático (X, Facebook, Telegram, Discord, Pinterest)
# Rev: 2025-11-18 — SEM FILTRO DE DADOS + LIMPEZA DE CARACTERES INVISÍVEIS NA COLUNA DE STATUS
# + TEXTO MINIMAL (APENAS LINK DO RESULTADO)
#
# Planilha: ImportadosBlogger2
# Colunas: A=Loteria B=Concurso C=Dados D=Números E=URL
# Status por rede (padrÃµes): H=8 (X), M=13 (Discord), N=14 (Pinterest), O=15 (Facebook), J=10 (Telegram)
#
# de publicação:
# - PUBLICA SEMPRE que a coluna da REDE alvo estiver VAZIA (após remover espaços e caracteres invisíveis)
# - NÃƒO olhar coluna de â€œEnfileiradoâ€
# - NÃƒO restrinja mais por data / horÃ¡rio (BACKLOG_DAYS ignorado)
# - Texto padrão da publicação: APENAS o link do resultado (sem cabeço, sem lista de números)
# â†' Para mandar só uma imagem, use GLOBAL_TEXT_MODE=IMAGE_ONLY no .env

importar os
importar re
importar io
importar glob
importar json
tempo de importação
importar base64
importar pytz
importar tweepy
solicitações de importação
importar datetime como dt
from threading import Thread
from collections import defaultdict
from dotenv import load_dotenv

# Planilhas Google
importar gspread
from oauth2client.service_account import ServiceAccountCredentials

# Imagem oficial (padrão aprovado)
de app.imaging importar gerar_imagem_loteria

# =========================
# CONFIGURAÇÃO / AMBIENTE
# =========================

carregar_dotenv()
TZ = pytz.timezone("America/Sao_Paulo")

SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
SHEET_TAB = os.getenv("SHEET_TAB", "ImportadosBlogger2").strip()

# Redes alvo (X, FACEBOOK, TELEGRAM, DISCORD, PINTEREST)
REDES_ALVO = [
    s.strip().upper()
    para s em os.getenv("TARGET_NETWORKS", "X").split(",")
    se s.strip()
]

# BACKLOG_DAYS agora é ignorado, mas deixei leitura para não quebrar .env
DIAS_DE_ATRASO = int(os.getenv("DIAS_DE_ATRASO", "7"))
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() == "true"

# ===== Modo de TEXTO (GLOBAL e por rede) =====

GLOBAL_TEXT_MODE = (os.getenv("GLOBAL_TEXT_MODE", "") ou "").strip().upper() # opcional

# por rede (se vazio, herdado do GLOBAL ou usa TEXT_AND_IMAGE como padrão)
X_TEXT_MODE = (os.getenv("X_TEXT_MODE", "") ou "").strip().upper()
FACEBOOK_TEXT_MODE = (os.getenv("FACEBOOK_TEXT_MODE", "") ou "").strip().upper()
MODO_TEXTO_TELEGRAM = (os.getenv("MODO_TEXTO_TELEGRAM", "") ou "").strip().upper()
DISCORD_TEXT_MODE = (os.getenv("DISCORD_TEXT_MODE", "") ou "").strip().upper()
PINTEREST_TEXT_MODE = (os.getenv("PINTEREST_TEXT_MODE", "") ou "").strip().upper()

MODOS_DE_TEXTO_VÁLIDOS = {"SOMENTE_IMAGEM", "TEXTO_E_IMAGEM", "SOMENTE_TEXTO"}


def get_text_mode(rede: str) -> str:
    """
    Prioridade: modo específico da rede -> GLOBAL_TEXT_MODE -> 'TEXT_AND_IMAGE'
    """
    específico = {
        "X": X_TEXT_MODE,
        "FACEBOOK": FACEBOOK_TEXT_MODE,
        "TELEGRAM": TELEGRAM_TEXT_MODE,
        "DISCORD": DISCORD_TEXT_MODE,
        "PINTEREST": PINTEREST_TEXT_MODE,
    }.get(rede, "")

    modo = (específico ou GLOBAL_TEXT_MODE ou "TEXTO E IMAGEM").upper()
    retornar modo se modo em VALID_TEXT_MODES senão "TEXTO E IMAGEM"


# ===== X (Twitter) =====

X_POST_IN_ALL_ACCOUNTS = os.getenv("X_POST_IN_ALL_ACCOUNTS", "true").strip().lower() == "true"
POST_X_WITH_IMAGE = os.getenv("POST_X_WITH_IMAGE", "true").strip().lower() == "true"
COL_STATUS_X = int(os.getenv("COL_STATUS_X", "8")) # H

# ===== Facebook (Páginas) =====

POST_FB_WITH_IMAGE = os.getenv("POST_FB_WITH_IMAGE", "true").strip().lower() == "true"
COL_STATUS_FACEBOOK = int(os.getenv("COL_STATUS_FACEBOOK", "15")) # O
FB_PAGE_IDS = [
    s.strip()
    para s em os.getenv("FB_PAGE_IDS", os.getenv("FB_PAGE_ID", "")).split(",")
    se s.strip()
]
FB_PAGE_TOKENS = [
    s.strip()
    para s em os.getenv("FB_PAGE_TOKENS", os.getenv("FB_PAGE_TOKEN", "")).split(",")
    se s.strip()
]

# ===== Telegram =====

POST_TG_WITH_IMAGE = os.getenv("POST_TG_WITH_IMAGE", "true").strip().lower() == "true"
COL_STATUS_TELEGRAM = int(os.getenv("COL_STATUS_TELEGRAM", "10")) # J
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
TG_CHAT_IDS = [s.strip() para s em os.getenv("TG_CHAT_IDS", "").split(",") se s.strip()]

# ===== Discord =====

COL_STATUS_DISCORD = int(os.getenv("COL_STATUS_DISCORD", "13")) # M
DISCORD_WEBHOOKS = [s.strip() para s em os.getenv("DISCORD_WEBHOOKS", "").split(",") se s.strip()]

# ===== Pinterest =====

COL_STATUS_PINTEREST = int(os.getenv("COL_STATUS_PINTEREST", "14")) # N
PINTEREST_ACCESS_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "").strip()
PINTEREST_BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "").strip()
POST_PINTEREST_WITH_IMAGE = os.getenv("POST_PINTEREST_WITH_IMAGE", "true").strip().lower() == "true"

# ===== KIT (HTML/CSS) /saída =====

USE_KIT_IMAGE_FIRST = os.getenv("USE_KIT_IMAGE_FIRST", "false").strip().lower() == "true"
KIT_OUTPUT_DIR = os.getenv("KIT_OUTPUT_DIR", "output").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip() # (reservado para uso futuro se precisar)

# ===== Manter ativo (Dividir/Renderizar) =====

ENABLE_KEEPALIVE = os.getenv("ENABLE_KEEPALIVE", "false").strip().lower() == "true"
KEEPALIVE_PORT = int(os.getenv("KEEPALIVE_PORT", "8080"))

# Limites

MAX_PUBLICACOES_RODADA = int(os.getenv("MAX_PUBLICACOES_RODADA", "30"))
PAUSA_ENTRE_POSTS = float(os.getenv("PAUSA_ENTRE_POSTS", "2.0"))


def _detect_origem():
    se os.getenv("BOT_ORIGEM"):
        retornar os.getenv("BOT_ORIGEM").strip()
    se os.getenv("GITHUB_ACTIONS"):
        retornar "GitHub"
    se os.getenv("REPL_ID") ou os.getenv("REPLIT_DB_URL"):
        retornar "Dividir"
    se os.getenv("RENDER"):
        retornar "Renderizar"
    retornar "Local"


BOT_ORIGEM = _detect_origem()

# =========================
# Planilha — colunas (base 1)
# =========================

COL_Loteria, COL_Concurso, COL_Data, COL_Números, COL_URL = 1, 2, 3, 4, 5
COL_URL_Imagem, COL_Imagem = 6, 7 # indiretamente (não obrigatórios)

COL_STATUS_REDES = {
    "X": COL_STATUS_X, # H
    "FACEBOOK": COL_STATUS_FACEBOOK, # O
    "TELEGRAM": COL_STATUS_TELEGRAM, #J
    "DISCORD": COL_STATUS_DISCORD, # M
    "PINTEREST": COL_STATUS_PINTEREST, # N
}

# =========================
# Utilitários
# =========================


def _not_empty(v):
    retornar bool(str(v ou "").strip())


def _is_empty_status(v):
    """
    Considere a célula VAZIA mesmo se tiver espaços ou caracteres invisíveis
    comuns (largura zero, BOM, etc).
    Usado para decidir se a coluna de status está realmente vazia.
    """
    se v for None:
        retornar Verdadeiro

    s = str(v)
    #limpa espaços normais nas pontas
    s = s.strip()
    # remove caracteres invisíveis mais comuns
    invisiveis = ["\u200B", "\u200C", "\u200D", "\uFEFF", "\u2060"]
    para ch em invisiveis:
        s = s.replace(ch, "")

    retornar s == ""


def _now():
    retornar dt.datetime.now(TZ)


def _ts():
    retornar _now().strftime("%Y-%m-%d %H:%M:%S")


def _ts_br():
    retornar _now().strftime("%d/%m/%Y %H:%M")


def _safe_len(row, idx):
    retornar len(linha) >= idx


def _log(*a):
    print(f"[{_ts()}]", *a, flush=True)


# =========================
# Planilhas Google
# =========================


def _gs_client():
    sa_json = os.getenv("GOOGLE_SERVICE_JSON", "").strip()
    escopos = [
        "https://www.googleapis.com/auth/spreadsheets"
        "https://www.googleapis.com/auth/drive",
    ]

    se sa_json:
        info = json.loads(sa_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scopes)
    outro:
        caminho = "service_account.json"
        se não os.path.exists(path):
            raise RuntimeError(
                "Credencial Google ausente (definida GOOGLE_SERVICE_JSON ou service_account.json)"
            )
        creds = ServiceAccountCredentials.from_json_keyfile_name(path, scopes)

    retornar gspread.authorize(credenciais)


def _open_ws():
    se não for SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID não definido.")
    sh = _gs_client().open_by_key(SHEET_ID)
    retornar sh.worksheet(SHEET_TAB)


def marcar_publicado(ws, rownum, rede, valor=Nenhum):
    col = COL_STATUS_REDES.get(rede,Nenhum)
    se não for col:
        retornar
    valor = value or f"Publicado {rede} via {BOT_ORIGEM} em {_ts_br()}"
    ws.update_cell(rownum, col, valor)


# =========================
# Auxiliares de lesma (KIT)
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
    s = (s ou "").lower()
    s = re.sub(r"[Ã¡Ã Ã¢Ã£Ã¤]", "a", s)
    s = re.sub(r"[éÃ¨êÃ«]", "e", s)
    s = re.sub(r"[ÃÃ¬Ã®Ã¯]", "i", s)
    s = re.sub(r"[Ã³Ã²Ã´ÃµÃ¶]", "o", s)
    s = re.sub(r"[ÃºÃ¹Ã»Ã¼]", "u", s)
    s = re.sub(r"Ã§", "c", s)
    s = re.sub(r"[^a-z0-9- ]+", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    retornar s


def _guess_slug(name: str) -> str:
    p = (nome ou "").minúsculo()
    para k, v em _LOTERIA_SLUGS.items():
        se k em p:
            retornar v
    return _slugify(nome ou "loteria")


# =========================
# IMAGEM: KIT /saída -> imagem oficial.py
# =========================


def _try_load_kit_image(row):
    """
    Se USE_KIT_IMAGE_FIRST, tente localizar o arquivo no KIT_OUTPUT_DIR usando slug e concurso/data.
    Retornar BytesIO ou Nenhum.
    """
    se não USE_KIT_IMAGE_FIRST:
        retornar Nenhum

    tentar:
        loteria = linha[COL_Loteria - 1] se _safe_len(linha, COL_Loteria) senão ""
        concurso = linha[COL_Concurso - 1] if _safe_len(linha, COL_Concurso) else ""
        data_br = linha[COL_Data - 1] se _safe_len(linha, COL_Data) senão ""
        slug = _guess_slug(loteria)

        padrões = []

        se concurso:
            padrões.adicionar(
                os.path.join(KIT_OUTPUT_DIR, f"*{slug}*{_slugify(concurso)}*.jp*g")
            )
            padrões.adicionar(
                os.path.join(KIT_OUTPUT_DIR, f"{slug}-{_slugify(concurso)}*.jp*g")
            )

        se data_br:
            padrões.adicionar(
                os.path.join(KIT_OUTPUT_DIR, f"*{slug}*{_slugify(data_br)}*.jp*g")
            )

        # fallback genérico por slug
        patterns.append(os.path.join(KIT_OUTPUT_DIR, f"{slug}*.jp*g"))

        para padrões de pat:
            arquivos = classificados(glob.glob(pat))
            se arquivos:
                caminho = arquivos[0]
                com open(path, "rb") como f:
                    buf = io.BytesIO(f.read())
                    buf.seek(0)
                    retornar buffer

        retornar Nenhum
    exceto Exception como e:
        _log(f"[KIT] erro ao tentar carregar imagem: {e}")
        retornar Nenhum


def _build_image_from_row(row):
    """
    Retornar BytesIO (PNG ou JPG).
    Prioriza KIT /saída (se habilitado); se não encontrar, gera imagem oficial via gerar_imagem_loteria.
    """
    buf = _try_load_kit_image(row)
    se buf:
        retornar buf # JPG/PNG para KIT

    # Gera imagem oficial (PNG) via Pillow/imaging.py
    loteria = linha[COL_Loteria - 1] se _safe_len(linha, COL_Loteria) senão "Loteria"
    concurso = linha[COL_Concurso - 1] if _safe_len(linha, COL_Concurso) else "0000"
    data_br = linha[COL_Data - 1] se _safe_len(linha, COL_Data) senão _now().strftime(
        "%d/%m/%Y"
    )
    numeros = linha[COL_Numeros - 1] if _safe_len(linha, COL_Numeros) else ""
    url_res = linha[COL_URL - 1] se _safe_len(linha, COL_URL) senão ""

    # gerar_imagem_loteria deve retornar BytesIO já posicionado
    retornar gerar_imagem_loteria(
        str(loteria), str(concurso), str(dados_br), str(números), str(url_res)
    )


# =========================
# Texto (tweet/post/legenda)
# =========================


def montar_texto_base(linha) -> str:
    """
    TEXTO MÍNIMO:
    - Apenas o link do resultado (coluna E)
    - Sem cabealho, sem números, sem 'Resultado completo:'
    - Para mandar só uma imagem, use GLOBAL_TEXT_MODE=IMAGE_ONLY no .env
    """
    url = (row[COL_URL - 1] if _safe_len(row, COL_URL) else "").strip()

    se a URL:
        URL de retorno

    retornar ""


# =========================
# Coleta de linhas candidatas (por REDE)
# =========================


def coleção_candidatos_para(ws, rede: str):
    """
    Retorna lista de tuplas (rownum, row) somente onde:
      - status da REDE (coluna específica) está VAZIO (após remover caracteres invisíveis)

    NÃƒO olhar coluna de ENFILEIRADO.
    NÃƒO filtra por dados (BACKLOG_DAYS ignorado).
    """
    linhas = ws.get_all_values()
    se len(linhas) <= 1:
        _log(f"[{rede}] Planilha sem dados.")
        retornar []

    dados = linhas[1:]
    cand = []
    col_status = COL_STATUS_REDES.get(rede)
    se não col_status:
        _log(f"[{rede}] Coluna de status não definida.")
        retornar []

    total = len(dados)
    0
    ss = 0

    para rindex, linha em enumerate(data, start=2):
        status_val = linha[coluna_status - 1] se len(linha) >= coluna_status senão ""
        tem_status = não _é_status_vazio(status_val)

        se não tem_status:
            cand.append((rindex, linha))
            vazios += 1
        outro:
            colocars += 1
            pré-visualização = str(status_val)
            pré-visualização = pré-visualização.replace("\n", "\\n")
            _registro(
                f"[{rede}] SKIP L{rindex}: status col {col_status} preenchido ({preview[:40]})"
            )

    _registro(
        f"[{rede}] Candidatas (sem filtro de dados): {vazias}/{total} | status necessário: {preenchidas}"
    )
    devolver cand


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


classe XAccount:
    def __init__(self, label, api_key, api_secret, access_token, access_secret):
        self.label = label
        self.client_v2 = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            token_de_acesso=token_de_acesso,
            access_token_secret=access_secret,
        )
        auth = tweepy.OAuth1UserHandler(
            chave_api,
            segredo_da_api,
            token_de_acesso,
            segredo_de_acesso,
        )
        self.api_v1 = tweepy.API(auth)
        tentar:
            eu = self.client_v2.get_me()
            self.user_id = me.data.id se me e me.data senão None
            self.handle = "@" + (me.data.username if me and me.data else label)
        exceto Exceção:
            self.user_id = None
            self.handle = f"@{label}"


def build_x_accounts():
    accs = []

    def ok(d):
        retornar todos(d.get(k) para k em ("api_key", "api_secret", "access_token", "access_secret"))

    se ok(TW1):
        accs.append(XAccount("ACC1", **TW1))
    outro:
        _log("Conta ACC1 incompleta nos Secrets — verifique *_1.")

    se ok(TW2):
        accs.append(XAccount("ACC2", **TW2))
    outro:
        _log("Conta ACC2 incompleta nos Secrets — verifique *_2.")

    se não for acesso:
        raise RuntimeError("Nenhuma conta X configurada.")
    contas de retorno


_recent_tweets_cache = defaultdict(set)
_postados_nesta_execucao = defaultdict(set)


def x_load_recent_texts(acc: XAccount, max_results=50):
    tentar:
        resp = acc.client_v2.get_users_tweets(
            id=acc.user_id,
            max_results=min(max_results, 100),
            tweet_fields=["texto"],
        )
        saída = conjunto()
        se resp e resp.data:
            para tw em resp.data:
                t = (tw.text ou "").strip()
                se t:
                    fora.adicionar(t)
        _recent_tweets_cache[acc.label] = set(list(out)[-50:])
        retornar _recent_tweets_cache[acc.label]
    exceto Exception como e:
        _log(f"[{acc.handle}] warning: falha ao ler tweets recentes: {e}")
        retornar conjunto()


def x_is_dup(acc: XAccount, text: str) -> bool:
    t = (texto ou "").strip()
    se não t:
        retornar Falso
    retornar (t em _recent_tweets_cache[acc.label]) ou (t em _postados_nesta_execucao[acc.label])


def x_upload_media_if_any(acc: XAccount, row):
    se não for POST_X_WITH_IMAGE ou DRY_RUN:
        retornar Nenhum
    tentar:
        buf = _build_image_from_row(row)
        mídia = acc.api_v1.media_upload(filename="resultado.png", file=buf)
        retornar [media.media_id_string]
    exceto Exception como e:
        _log(f"[{acc.handle}] Erro imagem: {e}")
        retornar Nenhum


def publicar_em_x(ws, candidatos):
    contas = construir_x_contas()
    para contas em contas:
        _recent_tweets_cache[acc.label] = x_load_recent_texts(acc, 50)
        _log(f"[X] Conta conectada: {acc.handle}")

    publicados = 0
    acc_idx = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    modo = obter_modo_texto("X")

    para rownum, linha em candidatos[:limite]:
        texto_full = montar_texto_base(linha)
        texto_para_postar = "" if mode == "IMAGE_ONLY" else texto_full
        ok_qualquer = Falso

        se X_POST_IN_ALL_ACCOUNTS:
            para contas em contas:
                media_ids = x_upload_media_if_any(acc, linha)
                tentar:
                    se DRY_RUN:
                        _log(f"[X][{acc.handle}] TESTE DE SIMULAÇÃO")
                        ok = Verdadeiro
                    outro:
                        if texto_para_postar e x_is_dup(acc, texto_para_postar):
                            _log(f"[X][{acc.handle}] SKIP duplicado.")
                            ok = Falso
                        outro:
                            resp = acc.client_v2.create_tweet(
                                text=(texto_para_postar ou Nenhum)
                                se o modo for diferente de "SOMENTE IMAGEM"
                                caso contrário, nenhum.
                                media_ids=media_ids se POST_X_WITH_IMAGE senão None,
                            )
                            se texto_para_postar:
                                _postados_nesta_execucao[acc.label].add(texto_para_postar)
                                _recent_tweets_cache[acc.label].add(texto_para_postar)
                            _log(f"[X][{acc.handle}] OK â†' {resp.data['id']}")
                            ok = Verdadeiro
                exceto Exception como e:
                    _log(f"[X][{acc.handle}] erro: {e}")
                    ok = Falso

                ok_qualquer = ok_qualquer ou ok
                tempo.dormir(0.7)
        outro:
            acc = contas[acc_idx % len(contas)]
            acc_idx += 1
            media_ids = x_upload_media_if_any(acc, linha)
            tentar:
                se DRY_RUN:
                    _log(f"[X][{acc.handle}] TESTE DE SIMULAÇÃO")
                    ok_qualquer = Verdadeiro
                outro:
                    if texto_para_postar e x_is_dup(acc, texto_para_postar):
                        _log(f"[X][{acc.handle}] SKIP duplicado.")
                        ok_qualquer = Falso
                    outro:
                        resp = acc.client_v2.create_tweet(
                            text=(texto_para_postar ou Nenhum)
                            se o modo for diferente de "SOMENTE IMAGEM"
                            caso contrário, nenhum.
                            media_ids=media_ids se POST_X_WITH_IMAGE senão None,
                        )
                        se texto_para_postar:
                            _postados_nesta_execucao[acc.label].add(texto_para_postar)
                            _recent_tweets_cache[acc.label].add(texto_para_postar)
                        _log(f"[X][{acc.handle}] OK â†' {resp.data['id']}")
                        ok_qualquer = Verdadeiro
            exceto Exception como e:
                _log(f"[X][{acc.handle}] erro: {e}")
                ok_qualquer = Falso

        se ok_any e não DRY_RUN:
            marcar_publicado(ws, rownum, "X")
            publicados += 1

        tempo.dormir(PAUSA_ENTRE_POSTS)

    _log(f"[X] Publicados: {publicados}")
    retornar publicados


# --- Facebook ---


def _fb_post_text(page_id, page_token, message: str, link: str | None = None):
    url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
    dados = {"mensagem": mensagem, "token_de_acesso": token_da_página}
    se houver link:
        dados["link"] = link
    r = requests.post(url, data=data, timeout=25)
    r.raise_for_status()
    retornar r.json().get("id")


def _fb_post_photo(page_id, page_token, caption: str, image_bytes: bytes):
    url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
    arquivos = {"source": ("resultado.png", image_bytes, "image/png")}
    dados = {"legenda": legenda, "publicado": "verdadeiro", "token_de_acesso": token_da_página}
    r = requests.post(url, data=data, files=files, timeout=40)
    r.raise_for_status()
    retornar r.json().get("id")


def publicar_em_facebook(ws, candidatos):
    se não FB_PAGE_IDS ou não FB_PAGE_TOKENS ou len(FB_PAGE_IDS) != len(FB_PAGE_TOKENS):
        raise RuntimeError("Facebook: configure FB_PAGE_IDS e FB_PAGE_TOKENS (mesmo tamanho).")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    modo = get_text_mode("FACEBOOK")

    para rownum, linha em candidatos[:limite]:
        base = montar_texto_base(linha)
        msg = "" se mode == "IMAGE_ONLY" senão base
        ok_qualquer = Falso

        para pid, ptoken em zip(FB_PAGE_IDS, FB_PAGE_TOKENS):
            tentar:
                se DRY_RUN:
                    _log(f"[Facebook][{pid}] TESTE DE FRIO")
                    ok = Verdadeiro
                outro:
                    se POST_FB_WITH_IMAGE:
                        buf = _build_image_from_row(row)
                        fb_id = _fb_post_photo(pid, ptoken, msg, buf.getvalue())
                    outro:
                        url_post = linha[COL_URL - 1] se _safe_len(linha, COL_URL) senão ""
                        fb_id = _fb_post_text(pid, ptoken, msg, link=url_post ou None)
                    _log(f"[Facebook][{pid}] OK â†' {fb_id}")
                    ok = Verdadeiro
            exceto Exception como e:
                _log(f"[Facebook][{pid}] erro: {e}")
                ok = Falso

            ok_qualquer = ok_qualquer ou ok
            tempo.dormir(0.7)

        se ok_any e não DRY_RUN:
            marcar_publicado(ws, rownum, "FACEBOOK")
            publicados += 1

        tempo.dormir(PAUSA_ENTRE_POSTS)

    _log(f"[Facebook] Publicados: {publicados}")
    retornar publicados


# --- Telegram ---


def _tg_send_photo(token, chat_id, caption, image_bytes):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    arquivos = {"foto": ("resultado.png", image_bytes, "image/png")}
    dados = {"chat_id": chat_id, "caption": caption}
    r = requests.post(url, data=data, files=files, timeout=40)
    r.raise_for_status()
    return r.json().get("result", {}).get("message_id")


def _tg_send_text(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    dados = {"chat_id": chat_id, "text": texto, "disable_web_page_preview": False}
    r = requests.post(url, data=data, timeout=25)
    r.raise_for_status()
    return r.json().get("result", {}).get("message_id")


def publicar_em_telegram(ws, candidatos):
    se não for TG_BOT_TOKEN ou não for TG_CHAT_IDS:
        raise RuntimeError("Telegram: configure TG_BOT_TOKEN e TG_CHAT_IDS.")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    modo = obter_modo_texto("TELEGRAM")

    para rownum, linha em candidatos[:limite]:
        base = montar_texto_base(linha)
        msg = "" se mode == "IMAGE_ONLY" senão base
        ok_qualquer = Falso

        para chat_id em TG_CHAT_IDS:
            tentar:
                se DRY_RUN:
                    _log(f"[Telegram][{chat_id}] TESTE DE SIMULAÇÃO")
                    ok = Verdadeiro
                outro:
                    se POST_TG_WITH_IMAGE:
                        buf = _build_image_from_row(row)
                        msg_id = _tg_send_photo(TG_BOT_TOKEN, chat_id, msg, buf.getvalue())
                    outro:
                        url_post = linha[COL_URL - 1] se _safe_len(linha, COL_URL) senão ""
                        mensagem_final = mensagem
                        se url_post e final_msg:
                            mensagem_final = f"{mensagem_final}\n{url_post}"
                        senão se url_post e não final_msg:
                            mensagem_final = postagem_url
                        msg_id = _tg_send_text(TG_BOT_TOKEN, chat_id, final_msg or "")
                    _log(f"[Telegram][{chat_id}] OK â†' {msg_id}")
                    ok = Verdadeiro
            exceto Exception como e:
                _log(f"[Telegrama][{chat_id}] erro: {e}")
                ok = Falso

            ok_qualquer = ok_qualquer ou ok
            tempo.dormir(0.5)

        se ok_any e não DRY_RUN:
            marcar_publicado(ws, rownum, "TELEGRAM")
            publicados += 1

        tempo.dormir(PAUSA_ENTRE_POSTS)

    _log(f"[Telegrama] Publicados: {publicados}")
    retornar publicados


# --- Discord ---


def _discord_send(webhook_url, content=None, image_bytes=None):
    dados = {"conteúdo": conteúdo ou ""}
    arquivos = Nenhum
    se image_bytes:
        arquivos = {"arquivo": ("resultado.png", image_bytes, "image/png")}
    r = requests.post(webhook_url, data=data, files=files, timeout=30)
    r.raise_for_status()
    retornar Verdadeiro


def publicar_em_discord(ws, candidatos):
    se não DISCORD_WEBHOOKS:
        raise RuntimeError("Discord: definido DISCORD_WEBHOOKS (um ou mais, separados por vérgula).")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    modo = get_text_mode("DISCORD")

    para rownum, linha em candidatos[:limite]:
        base = montar_texto_base(linha)
        msg = "" se mode == "IMAGE_ONLY" senão base
        ok_qualquer = Falso

        tentar:
            se DRY_RUN:
                para wh em DISCORD_WEBHOOKS:
                    _log(f"[Discord] TESTE DE SOFRIMENTO â†' {wh[-18:]}")
                ok_qualquer = Verdadeiro
            outro:
                buf = _build_image_from_row(row)
                img_bytes = buf.getvalue()
                para wh em DISCORD_WEBHOOKS:
                    carga útil = mensagem
                    url_post = linha[COL_URL - 1] se _safe_len(linha, COL_URL) senão ""
                    se url_post e payload:
                        payload = f"{payload}\n{url_post}"
                    senão se url_post e não payload:
                        payload = url_post
                    _discord_send(wh, content=(payload or None), image_bytes=img_bytes)
                    _log(f"[Discord] OK â†' {wh[-18:]}")
                ok_qualquer = Verdadeiro
        exceto Exception como e:
            _log(f"[Discord] erro: {e}")
            ok_qualquer = Falso

        se ok_any e não DRY_RUN:
            marcar_publicado(ws, rownum, "DISCORD")
            publicados += 1

        tempo.dormir(PAUSA_ENTRE_POSTS)

    _log(f"[Discord] Publicados: {publicados}")
    retornar publicados


# --- Pinterest ---


def _pinterest_create_pin(
    ficha,
    id_do_board,
    título,
    descrição,
    link,
    image_bytes=None,
    url_da_imagem=Nenhum,
):
    url = "https://api.pinterest.com/v5/pins"
    cabeçalhos = {"Autorização": f"Portador {token}"}
    carga útil = {
        "board_id": board_id,
        "título": título[:100],
        "descrição": (descrição ou "")[:500],
    }
    se houver link:
        payload["link"] = link

    se image_bytes não for None:
        payload["media_source"] = {
            "source_type": "image_base64",
            "content_type": "image/png",
            "dados": base64.b64encode(image_bytes).decode("utf-8"),
        }
    senão se image_url:
        payload["media_source"] = {"source_type": "image_url", "url": image_url}
    outro:
        raise ValueError("Pinterest: informe image_bytes ou image_url.")

    r = requests.post(url, headers=headers, json=payload, timeout=40)
    r.raise_for_status()
    retornar r.json().get("id")


def publicar_em_pinterest(ws, candidatos):
    se não (PINTEREST_ACCESS_TOKEN e PINTEREST_BOARD_ID):
        raise RuntimeError("Pinterest: defina PINTEREST_ACCESS_TOKEN e PINTEREST_BOARD_ID.")

    publicados = 0
    limite = min(MAX_PUBLICACOES_RODADA, len(candidatos))
    modo = get_text_mode("PINTEREST")

    para rownum, linha em candidatos[:limite]:
        loteria = linha[COL_Loteria - 1] se _safe_len(linha, COL_Loteria) senão "Loteria"
        concurso = linha[COL_Concurso - 1] if _safe_len(linha, COL_Concurso) else "0000"
        title = f"{loteria} — Concurso {concurso}"
        desc_full = montar_texto_base(linha)
        desc = "" se mode == "IMAGE_ONLY" senão desc_full
        url_post = linha[COL_URL - 1] se _safe_len(linha, COL_URL) senão ""

        tentar:
            se DRY_RUN:
                _log(f"[Pinterest] TESTE DE SIMULAÇÃO: {title}")
                ok = Verdadeiro
            outro:
                se POST_PINTEREST_WITH_IMAGE:
                    buf = _build_image_from_row(row)
                    pin_id = _pinterest_create_pin(
                        PINTEREST_ACCESS_TOKEN,
                        ID_DO_QUADRO_DO_PINTEREST,
                        título,
                        desc,
                        url_post,
                        image_bytes=buf.getvalue(),
                    )
                outro:
                    pin_id = _pinterest_create_pin(
                        PINTEREST_ACCESS_TOKEN,
                        ID_DO_QUADRO_DO_PINTEREST,
                        título,
                        desc,
                        url_post,
                        image_url=url_post ou None,
                    )
                _log(f"[Pinterest] OK â†' {pin_id}")
                ok = Verdadeiro
        exceto Exception como e:
            _log(f"[Pinterest] erro: {e}")
            ok = Falso

        se estiver tudo bem e não for DRY_RUN:
            marcar_publicado(ws, rownum, "PINTEREST")
            publicados += 1

        tempo.dormir(PAUSA_ENTRE_POSTS)

    _log(f"[Pinterest] Publicados: {publicados}")
    retornar publicados


# =========================
# Keepalive (opcional)
# =========================


def iniciar_manter_vivo():
    tentar:
        from flask import Flask
    exceto ImportError:
        _log("Flask não instalado; keepalive desativado.")
        retornar Nenhum

    app = Flask(__name__)

    @app.route("/")
    @app.route("/ping")
    def raiz():
        retornar "ok", 200

    def executar():
        porta = int(os.getenv("PORTA", KEEPALIVE_PORTA))
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    th = Thread(target=run, daemon=True)
    th.start()
    _log(f"Keepalive Flask ativo em 0.0.0.0:{os.getenv('PORT', KEEPALIVE_PORT)}")
    retornar o


# =========================
# PRINCIPAL
# =========================


def main():
    _registro(
        "Iniciando bot..."
        f"Origem={BOT_ORIGEM} | Redes={','.join(TARGET_NETWORKS)} | DRY_RUN={DRY_RUN} | "
        f"GLOBAL_TEXT_MODE={GLOBAL_TEXT_MODE ou 'â-'} | KIT_FIRST={USE_KIT_IMAGE_FIRST}"
    )

    keepalive_thread = iniciar_keepalive() se ENABLE_KEEPALIVE senão None

    tentar:
        ws = _open_ws()

        para rede em TARGET_NETWORKS:
            se rede não estiver em COL_STATUS_REDES:
                _log(f"[{rede}] rede não suportada.")
                continuar

            candidatos = coleta_candidatos_para(ws, rede)
            se não forem candidatos:
                _log(f"[{rede}] Nenhuma candidata.")
                continuar

            se rede == "X":
                publicar_em_x(ws, candidatos)
            elif rede == "FACEBOOK":
                publicar_em_facebook(ws, candidatos)
            elif rede == "TELEGRAM":
                publicar_em_telegram(ws, candidatos)
            elif rede == "DISCORD":
                publicar_em_discord(ws, candidatos)
            elif rede == "PINTEREST":
                publicar_em_pinterest(ws, candidatos)
            outro:
                _log(f"[{rede}] não houve rupturas.")

        _log("Concluído.")
    exceto KeyboardInterrupt:
        _log("Interrompido pelo usuário.")
    exceto Exception como e:
        _log(f"[FATAL] {e}")
        elevação
    finalmente:
        se ENABLE_KEEPALIVE e keepalive_thread:
            tempo.dormir(1)


se __name__ == "__main__":
    principal()