# post_video.py — Portal SimonSports — YouTube Multi-Canal (Cofre Only)
# Rev: 2026-07-29 — Shorts públicos com metadados e tags padrão

import datetime as dt
import time
from typing import Any, Dict, List, Optional

from gerador_video import executar as gerar_video
from youtube_auth import get_access_token
from youtube_upload import build_watch_url, upload_video


def _now_br(tz_name: str = "America/Sao_Paulo") -> dt.datetime:
    try:
        import pytz
        return dt.datetime.now(pytz.timezone(tz_name))
    except Exception:
        return dt.datetime.now()


def _ts_br(tz_name: str = "America/Sao_Paulo") -> str:
    return _now_br(tz_name).strftime("%d/%m/%Y %H:%M")


def _log(*args: Any) -> None:
    print("[YOUTUBE]", *args, flush=True)


def _parse_tags(value: str) -> List[str]:
    if not value:
        return []
    return [tag.strip() for tag in value.replace(";", ",").split(",") if tag.strip()]


def _cofre_get_safe(cofre_get_fn, rede: str, chave: str, conta: Optional[str] = None, default: str = "") -> str:
    value = (cofre_get_fn(rede, chave, conta=conta, default="") or "").strip()
    if value:
        return value
    return (cofre_get_fn(rede, chave, default=default) or "").strip()


def listar_contas_youtube(cofre_cache: Dict[str, Any]) -> List[str]:
    creds_rc = cofre_cache.get("creds_rc", {}) or {}
    accounts = set()
    for (network, account, key), value in creds_rc.items():
        if (network or "").strip().upper() == "YOUTUBE" and (key or "").strip().upper() == "REFRESH_TOKEN" and value:
            accounts.add((account or "").strip())
    return sorted(account for account in accounts if account)


def publicar_video_em_multicanais(
    dados_video: Dict[str, Any],
    cofre_get_fn,
    cofre_cache: Dict[str, Any],
    *,
    dry_run: bool = False,
    sleep_between_channels: float = 1.0,
    tz_name: str = "America/Sao_Paulo",
) -> Dict[str, Any]:
    accounts = listar_contas_youtube(cofre_cache)
    if not accounts:
        message = "Nenhuma conta YOUTUBE com REFRESH_TOKEN no Cofre. Pulando."
        _log(message)
        return {
            "ok_any": False,
            "video_path": "",
            "results": [],
            "mark_value": f"Sem contas YOUTUBE no Cofre em {_ts_br(tz_name)}",
        }

    try:
        if dry_run:
            video_path = "DRYRUN_resultado_loteria.mp4"
            _log("DRY_RUN: pulando geração real do vídeo.")
        else:
            video_path = gerar_video(dados_video)
    except Exception as error:
        _log("Erro ao gerar vídeo:", error)
        return {
            "ok_any": False,
            "video_path": "",
            "results": [],
            "mark_value": f"Erro ao gerar vídeo: {error}",
        }

    results: List[Dict[str, Any]] = []
    ok_any = False

    lottery = str(dados_video.get("loteria") or "Loteria").strip()
    contest = str(dados_video.get("concurso") or "").strip()
    reference_url = str(dados_video.get("url") or "https://www.portalsimonsports.com/").strip()

    default_title = f"Resultado {lottery} — Concurso {contest} #Shorts".strip(" —")
    default_description = (
        f"Resultado da {lottery} — Concurso {contest}.\n"
        f"Confira o resultado completo: {reference_url}\n\n"
        "Portal SimonSports — conteúdo informativo sobre resultados de loterias.\n"
        "#Shorts #Loterias #Resultados #PortalSimonSports"
    )
    default_tags = [
        "Shorts", "loterias", "resultado", "resultados de loterias",
        lottery, f"concurso {contest}", "Portal SimonSports",
    ]

    for account in accounts:
        client_id = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "CLIENT_ID", conta=account)
        client_secret = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "CLIENT_SECRET", conta=account)
        refresh_token = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "REFRESH_TOKEN", conta=account)

        if not (client_id and client_secret and refresh_token):
            _log(f"[{account}] Credenciais incompletas (CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN).")
            results.append({
                "conta": account,
                "status": "ERRO",
                "video_id": "",
                "url": "",
                "error": "Credenciais incompletas",
            })
            continue

        privacy = _cofre_get_safe(
            cofre_get_fn,
            "YOUTUBE",
            "PRIVACY_STATUS",
            conta=account,
            default="public",
        ) or "public"
        category_id = _cofre_get_safe(
            cofre_get_fn,
            "YOUTUBE",
            "CATEGORY_ID",
            conta=account,
            default="24",
        ) or "24"
        custom_tags = _parse_tags(
            _cofre_get_safe(cofre_get_fn, "YOUTUBE", "TAGS", conta=account, default="")
        )
        tags = custom_tags or default_tags

        title = str(dados_video.get("title") or default_title)[:100]
        if "#Shorts" not in title and len(title) <= 92:
            title = f"{title} #Shorts"
        description = str(dados_video.get("description") or default_description)
        if "#Shorts" not in description:
            description += "\n\n#Shorts #Loterias #PortalSimonSports"
        description = description[:4500]

        try:
            if dry_run:
                video_id = f"DRYRUN_{account.replace(' ', '_')}"
                watch_url = build_watch_url(video_id)
                _log(f"[{account}] DRY_RUN OK → {watch_url}")
                ok_any = True
                results.append({
                    "conta": account,
                    "status": "OK",
                    "video_id": video_id,
                    "url": watch_url,
                    "error": "",
                })
            else:
                access_token = get_access_token(client_id, client_secret, refresh_token)
                video_id = upload_video(
                    access_token=access_token,
                    video_path=video_path,
                    title=title,
                    description=description,
                    tags=tags,
                    category_id=category_id,
                    privacy_status=privacy,
                )
                watch_url = build_watch_url(video_id)
                _log(f"[{account}] OK → {watch_url}")
                ok_any = True
                results.append({
                    "conta": account,
                    "status": "OK",
                    "video_id": video_id,
                    "url": watch_url,
                    "error": "",
                })
        except Exception as error:
            _log(f"[{account}] ERRO:", error)
            results.append({
                "conta": account,
                "status": "ERRO",
                "video_id": "",
                "url": "",
                "error": str(error),
            })

        time.sleep(sleep_between_channels)

    published_links = [
        f"{result['conta']}: {result['url']}"
        for result in results
        if result.get("status") == "OK" and result.get("url")
    ]
    if published_links:
        summary = " | ".join(published_links[:3])
        mark_value = f"Publicado YOUTUBE em {_ts_br(tz_name)} | {summary}"
    else:
        errors = [
            f"{result['conta']}: {result.get('error', '')}"
            for result in results
            if result.get("status") == "ERRO"
        ]
        mark_value = f"Falha YOUTUBE em {_ts_br(tz_name)} | " + " | ".join(errors[:2])

    return {
        "ok_any": ok_any,
        "video_path": video_path,
        "results": results,
        "mark_value": mark_value,
    }
