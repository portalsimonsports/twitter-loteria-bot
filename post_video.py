import os
import time
import datetime as dt

from youtube_auth import get_access_token
from youtube_upload import upload_video, build_watch_url

# Importa seu gerador de vídeo
from gerador_video import executar as gerar_video  # ajuste se seu arquivo/função tiver outro nome

def _tz_now_str():
    # simples; se você já tem TZ no bot, pode usar o mesmo
    return dt.datetime.now().strftime("%d/%m/%Y %H:%M")

def _log(*a):
    print(f"[YOUTUBE] ", *a, flush=True)

def _parse_tags(v: str):
    if not v:
        return []
    # aceita "a,b,c" ou "a; b; c"
    v = v.replace(";", ",")
    return [t.strip() for t in v.split(",") if t.strip()]

def _cofre_get_safe(_cofre_get, rede: str, chave: str, conta: str = None, default: str = ""):
    v = (_cofre_get(rede, chave, conta=conta, default=default) or "").strip()
    if v:
        return v
    # fallback global (conta vazia)
    return (_cofre_get(rede, chave, default=default) or "").strip()

def _listar_contas_youtube(_cofre_cache):
    """
    Descobre as contas YOUTUBE existentes no Cofre pela presença de REFRESH_TOKEN por conta.
    Retorna lista de contas (strings).
    """
    creds_rc = _cofre_cache.get("creds_rc", {}) or {}
    contas = set()
    for (r, c, k), v in creds_rc.items():
        if (r or "").strip().upper() == "YOUTUBE" and (k or "").strip().upper() == "REFRESH_TOKEN" and v:
            contas.add((c or "").strip())
    return sorted([c for c in contas if c])

def publicar_video_em_multicanais(
    dados_video: dict,
    cofre_get_fn,
    cofre_cache: dict
):
    """
    Gera vídeo e publica em TODOS os canais YOUTUBE cadastrados no Cofre.
    """
    contas = _listar_contas_youtube(cofre_cache)
    if not contas:
        _log("Nenhuma conta YOUTUBE com REFRESH_TOKEN no Cofre. Pulando.")
        return []

    # 1) Gera o vídeo 1x (mesmo arquivo serve para todos canais)
    video_path = gerar_video(dados_video)

    resultados = []
    for conta in contas:
        client_id     = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "CLIENT_ID", conta=conta)
        client_secret = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "CLIENT_SECRET", conta=conta)
        refresh_token = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "REFRESH_TOKEN", conta=conta)

        if not (client_id and client_secret and refresh_token):
            _log(f"[{conta}] Credenciais incompletas (CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN). Pulando.")
            continue

        privacy = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "PRIVACY_STATUS", conta=conta, default="unlisted") or "unlisted"
        cat_id  = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "CATEGORY_ID", conta=conta, default="17") or "17"
        tags_s  = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "TAGS", conta=conta, default="")
        tags    = _parse_tags(tags_s)

        # Título/descrição sugeridos
        title = dados_video.get("title") or f"{dados_video.get('loteria','Loteria')} — Concurso {dados_video.get('concurso','')}"
        desc  = dados_video.get("description") or f"Resultado completo: {dados_video.get('url','')}\n\nPortal SimonSports\nGerado em {_tz_now_str()}"

        try:
            access_token = get_access_token(client_id, client_secret, refresh_token)
            vid = upload_video(
                access_token=access_token,
                video_path=video_path,
                title=title,
                description=desc,
                tags=tags,
                category_id=cat_id,
                privacy_status=privacy
            )
            url = build_watch_url(vid)
            _log(f"[{conta}] OK → {url}")
            resultados.append({"conta": conta, "video_id": vid, "url": url, "status": "OK"})
        except Exception as e:
            _log(f"[{conta}] ERRO: {e}")
            resultados.append({"conta": conta, "video_id": "", "url": "", "status": f"ERRO: {e}"})

        time.sleep(1.0)

    return resultados