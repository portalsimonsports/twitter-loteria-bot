# post_video.py — Portal SimonSports — YouTube Multi-Canal (Cofre Only)
# Rev: 2026-01-20a
# - Publica em TODOS os canais/contas do YOUTUBE cadastrados no Cofre (por Conta)
# - Gera o vídeo 1x e reutiliza
# - Retorna resultados e um resumo pronto para marcar 1 coluna (Publicado_YOUTUBE)
#
# Dependências:
# - youtube_auth.py  -> get_access_token(client_id, client_secret, refresh_token) -> str
# - youtube_upload.py -> upload_video(...)-> video_id | build_watch_url(video_id)-> url
# - gerador_video.py -> executar(dados)-> caminho mp4

import os
import time
import datetime as dt
from typing import Dict, List, Any, Optional

from youtube_auth import get_access_token
from youtube_upload import upload_video, build_watch_url

from gerador_video import executar as gerar_video


def _now_br(tz_name: str = "America/Sao_Paulo") -> dt.datetime:
    try:
        import pytz
        tz = pytz.timezone(tz_name)
        return dt.datetime.now(tz)
    except Exception:
        return dt.datetime.now()


def _ts_br(tz_name: str = "America/Sao_Paulo") -> str:
    return _now_br(tz_name).strftime("%d/%m/%Y %H:%M")


def _log(*a):
    print("[YOUTUBE]", *a, flush=True)


def _parse_tags(v: str) -> List[str]:
    if not v:
        return []
    v = v.replace(";", ",")
    return [t.strip() for t in v.split(",") if t.strip()]


def _cofre_get_safe(cofre_get_fn, rede: str, chave: str, conta: Optional[str] = None, default: str = "") -> str:
    """
    Busca no Cofre tentando:
    1) rede+conta+chave
    2) rede+chave (conta vazia)
    """
    v = (cofre_get_fn(rede, chave, conta=conta, default="") or "").strip()
    if v:
        return v
    return (cofre_get_fn(rede, chave, default=default) or "").strip()


def listar_contas_youtube(cofre_cache: Dict[str, Any]) -> List[str]:
    """
    Descobre contas YOUTUBE existentes no Cofre pela presença de REFRESH_TOKEN por conta.
    Retorna lista de contas (strings).
    """
    creds_rc = cofre_cache.get("creds_rc", {}) or {}
    contas = set()
    for (r, c, k), v in creds_rc.items():
        if (r or "").strip().upper() == "YOUTUBE" and (k or "").strip().upper() == "REFRESH_TOKEN" and v:
            contas.add((c or "").strip())
    return sorted([c for c in contas if c])


def publicar_video_em_multicanais(
    dados_video: Dict[str, Any],
    cofre_get_fn,
    cofre_cache: Dict[str, Any],
    *,
    dry_run: bool = False,
    sleep_between_channels: float = 1.0,
    tz_name: str = "America/Sao_Paulo"
) -> Dict[str, Any]:
    """
    Gera vídeo e publica em TODOS os canais YOUTUBE cadastrados no Cofre.

    Retorno:
    {
      "ok_any": bool,
      "video_path": str,
      "results": [ {conta, status, video_id, url, error} ],
      "mark_value": str   # resumo curto para marcar 1 coluna
    }
    """
    contas = listar_contas_youtube(cofre_cache)
    if not contas:
        msg = "Nenhuma conta YOUTUBE com REFRESH_TOKEN no Cofre. Pulando."
        _log(msg)
        return {"ok_any": False, "video_path": "", "results": [], "mark_value": f"Sem contas YOUTUBE no Cofre em {_ts_br(tz_name)}"}

    # 1) Gera o vídeo 1x
    try:
        if dry_run:
            video_path = "DRYRUN_resultado_loteria.mp4"
            _log("DRY_RUN: pulando geração real do vídeo.")
        else:
            video_path = gerar_video(dados_video)
    except Exception as e:
        _log("Erro ao gerar vídeo:", e)
        return {"ok_any": False, "video_path": "", "results": [], "mark_value": f"Erro ao gerar vídeo: {e}"}

    results: List[Dict[str, Any]] = []
    ok_any = False

    # Defaults por vídeo (se não vierem)
    loteria = str(dados_video.get("loteria") or "Loteria")
    concurso = str(dados_video.get("concurso") or "")
    url_ref = str(dados_video.get("url") or "")

    default_title = dados_video.get("title") or f"{loteria} — Concurso {concurso}".strip()
    default_desc = dados_video.get("description") or f"Resultado completo: {url_ref}\n\nPortal SimonSports\nGerado em {_ts_br(tz_name)}"

    for conta in contas:
        client_id = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "CLIENT_ID", conta=conta)
        client_secret = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "CLIENT_SECRET", conta=conta)
        refresh_token = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "REFRESH_TOKEN", conta=conta)

        if not (client_id and client_secret and refresh_token):
            _log(f"[{conta}] Credenciais incompletas (CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN).")
            results.append({"conta": conta, "status": "ERRO", "video_id": "", "url": "", "error": "Credenciais incompletas"})
            continue

        privacy = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "PRIVACY_STATUS", conta=conta, default="unlisted") or "unlisted"
        cat_id = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "CATEGORY_ID", conta=conta, default="17") or "17"
        tags_s = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "TAGS", conta=conta, default="")
        tags = _parse_tags(tags_s)

        title = str(dados_video.get("title") or default_title)[:100]
        desc = str(dados_video.get("description") or default_desc)[:4500]

        try:
            if dry_run:
                vid = f"DRYRUN_{conta.replace(' ', '_')}"
                watch_url = build_watch_url(vid)
                _log(f"[{conta}] DRY_RUN OK → {watch_url}")
                ok_any = True
                results.append({"conta": conta, "status": "OK", "video_id": vid, "url": watch_url, "error": ""})
            else:
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
                watch_url = build_watch_url(vid)
                _log(f"[{conta}] OK → {watch_url}")
                ok_any = True
                results.append({"conta": conta, "status": "OK", "video_id": vid, "url": watch_url, "error": ""})
        except Exception as e:
            _log(f"[{conta}] ERRO:", e)
            results.append({"conta": conta, "status": "ERRO", "video_id": "", "url": "", "error": str(e)})

        time.sleep(sleep_between_channels)

    # 3) Monta mark_value curto (para célula única)
    ok_links = [f"{r['conta']}: {r['url']}" for r in results if r.get("status") == "OK" and r.get("url")]
    if ok_links:
        resumo = " | ".join(ok_links[:3])  # limita 3 links para não estourar célula
        mark_value = f"Publicado YOUTUBE em {_ts_br(tz_name)} | {resumo}"
    else:
        # pega até 2 erros para resumo
        errs = [f"{r['conta']}: {r.get('error','')}" for r in results if r.get("status") == "ERRO"]
        mark_value = f"Falha YOUTUBE em {_ts_br(tz_name)} | " + " | ".join(errs[:2])

    return {
        "ok_any": ok_any,
        "video_path": video_path,
        "results": results,
        "mark_value": mark_value
    }