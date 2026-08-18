from __future__ import annotations

import os
import subprocess
import time
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, List, Sequence, Tuple
from zoneinfo import ZoneInfo

import requests

import daily_queue_v19 as queue
from daily_video_v19 import gerar_pacote_diario
from post_video import _cofre_get_safe, _parse_tags, _ts_br, _unique_tags, listar_contas_youtube
from youtube_auth import get_access_token
from youtube_upload import build_watch_url, upload_thumbnail, upload_video

API = "https://www.googleapis.com/youtube/v3"
LIVE_MARKER = "LIVE DIÁRIA LOTERIAS"


def _request(method: str, url: str, *, token: str, params=None, json_body=None, timeout: int = 60) -> Dict[str, Any]:
    response = requests.request(
        method,
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params=params,
        json=json_body,
        timeout=timeout,
    )
    if not response.ok:
        try:
            detail = response.json()
        except Exception:
            detail = response.text[:1500]
        raise RuntimeError(f"YouTube Live API HTTP {response.status_code}: {detail}")
    if not response.content:
        return {}
    return response.json() or {}


def _local_now(timezone: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(timezone))
    except Exception:
        return datetime.now()


def _scheduled_start_iso(timezone: str) -> str:
    now = _local_now(timezone)
    hour = max(0, min(23, int(os.getenv("YOUTUBE_DAILY_LIVE_SCHEDULE_HOUR", "21") or "21")))
    scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if scheduled <= now:
        scheduled = now + timedelta(minutes=10)
    return scheduled.isoformat()


def _alert_metadata(date: str, targets: Sequence[Tuple[str, str, str]]) -> Dict[str, str]:
    names: List[str] = []
    lines: List[str] = []
    for _key, display, contest in targets:
        if display not in names:
            names.append(display)
        lines.append(f"• {display} — concurso {contest}")
    joined = ", ".join(names[:4]) + (" e Mais" if len(names) > 4 else "")
    title = f"Loterias de Hoje — {joined} | Resultados em atualização | {date}"
    if len(title) > 95:
        title = f"Loterias de Hoje — Resultados em atualização | {date}"
    description = "\n".join([
        f"ALERTA DO DIA — sorteios previstos para {date}:",
        "",
        *lines,
        "",
        "Esta transmissão será atualizada automaticamente assim que todos os resultados oficiais previstos para hoje estiverem disponíveis.",
        "O mesmo endereço será mantido para o resultado consolidado do dia.",
        "",
        "Portal SimonSports — Loterias Caixa",
        "https://www.portalsimonsports.com/search/label/Loterias%20Caixa?m=1",
        "Fonte: CAIXA Loterias. Conteúdo informativo.",
    ])
    return {"title": title[:95], "description": description[:4500]}


def _list_upcoming(token: str) -> List[Dict[str, Any]]:
    payload = _request(
        "GET",
        f"{API}/liveBroadcasts",
        token=token,
        params={"part": "id,snippet,status,contentDetails", "broadcastStatus": "upcoming", "mine": "true", "maxResults": 50},
    )
    return list(payload.get("items") or [])


def _find_daily_broadcast(token: str, date: str) -> Dict[str, Any] | None:
    for item in _list_upcoming(token):
        snippet = item.get("snippet") or {}
        title = str(snippet.get("title") or "")
        description = str(snippet.get("description") or "")
        if date in title and LIVE_MARKER in description:
            return item
    return None


def _create_stream(token: str, date: str) -> Dict[str, Any]:
    body = {
        "snippet": {"title": f"SimonSports Loterias {date}"},
        "cdn": {
            "frameRate": "30fps",
            "ingestionType": "rtmp",
            "resolution": "1080p",
        },
        "contentDetails": {"isReusable": False},
    }
    payload = _request(
        "POST",
        f"{API}/liveStreams",
        token=token,
        params={"part": "id,snippet,cdn,contentDetails,status"},
        json_body=body,
    )
    if not payload.get("id"):
        raise RuntimeError(f"Criação do liveStream não retornou id: {payload}")
    return payload


def _create_broadcast(token: str, date: str, targets: Sequence[Tuple[str, str, str]], timezone: str, privacy: str) -> Dict[str, Any]:
    meta = _alert_metadata(date, targets)
    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"] + f"\n\n{LIVE_MARKER}",
            "scheduledStartTime": _scheduled_start_iso(timezone),
        },
        "status": {
            "privacyStatus": privacy if privacy in {"public", "unlisted", "private"} else "public",
            "selfDeclaredMadeForKids": False,
        },
        "contentDetails": {
            "enableAutoStart": False,
            "enableAutoStop": False,
            "enableDvr": True,
            "enableEmbed": True,
            "recordFromStart": True,
            "monitorStream": {"enableMonitorStream": False},
        },
    }
    payload = _request(
        "POST",
        f"{API}/liveBroadcasts",
        token=token,
        params={"part": "id,snippet,status,contentDetails"},
        json_body=body,
    )
    if not payload.get("id"):
        raise RuntimeError(f"Criação do liveBroadcast não retornou id: {payload}")
    return payload


def _bind(token: str, broadcast_id: str, stream_id: str) -> Dict[str, Any]:
    return _request(
        "POST",
        f"{API}/liveBroadcasts/bind",
        token=token,
        params={"part": "id,snippet,status,contentDetails", "id": broadcast_id, "streamId": stream_id},
    )


def ensure_daily_live_for_account(
    token: str,
    date: str,
    targets: Sequence[Tuple[str, str, str]],
    timezone: str,
    privacy: str,
) -> Dict[str, Any]:
    existing = _find_daily_broadcast(token, date)
    if existing:
        bound = str((existing.get("contentDetails") or {}).get("boundStreamId") or "").strip()
        if bound:
            existing["_stream_id"] = bound
            return existing
        stream = _create_stream(token, date)
        bound_broadcast = _bind(token, existing["id"], stream["id"])
        bound_broadcast["_stream_id"] = stream["id"]
        return bound_broadcast

    broadcast = _create_broadcast(token, date, targets, timezone, privacy)
    stream = _create_stream(token, date)
    broadcast = _bind(token, broadcast["id"], stream["id"])
    broadcast["_stream_id"] = stream["id"]
    return broadcast


def ensure_daily_lives(
    date: str,
    targets: Sequence[Tuple[str, str, str]],
    cofre_get,
    cofre_cache: Dict[str, Any],
    *,
    timezone: str,
) -> List[str]:
    urls: List[str] = []
    accounts = listar_contas_youtube(cofre_cache)
    for account in accounts:
        client_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
        client_secret = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
        refresh_token = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
        privacy = _cofre_get_safe(cofre_get, "YOUTUBE", "PRIVACY_STATUS", conta=account, default="public") or "public"
        if not (client_id and client_secret and refresh_token):
            continue
        try:
            token = get_access_token(client_id, client_secret, refresh_token)
            broadcast = ensure_daily_live_for_account(token, date, targets, timezone, privacy)
            url = build_watch_url(str(broadcast.get("id") or ""))
            urls.append(url)
            queue._log(f"[{account}] Live diária preparada: {url}")
        except Exception as error:
            queue._log(f"[{account}] Não foi possível preparar a live diária: {error}")
            traceback.print_exc()
    return urls


def _stream_details(token: str, stream_id: str) -> Dict[str, Any]:
    payload = _request(
        "GET",
        f"{API}/liveStreams",
        token=token,
        params={"part": "id,cdn,status", "id": stream_id},
    )
    items = list(payload.get("items") or [])
    if not items:
        raise RuntimeError(f"liveStream {stream_id} não encontrado")
    return items[0]


def _wait_stream_active(token: str, stream_id: str, timeout_seconds: int = 120) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last = {}
    while time.time() < deadline:
        last = _stream_details(token, stream_id)
        status = str((last.get("status") or {}).get("streamStatus") or "").lower()
        if status == "active":
            return last
        time.sleep(5)
    raise RuntimeError(f"Stream não ficou ativo em {timeout_seconds}s. Último estado: {last.get('status')}")


def _transition(token: str, broadcast_id: str, status: str) -> Dict[str, Any]:
    return _request(
        "POST",
        f"{API}/liveBroadcasts/transition",
        token=token,
        params={"part": "id,snippet,status,contentDetails", "id": broadcast_id, "broadcastStatus": status},
    )


def _update_video_metadata(token: str, video_id: str, meta: Dict[str, Any], category_id: str, tags: Sequence[str]) -> None:
    body = {
        "id": video_id,
        "snippet": {
            "title": str(meta.get("title") or "")[:95],
            "description": str(meta.get("description") or "")[:5000],
            "categoryId": str(category_id or "24"),
            "tags": list(tags)[:25],
        },
    }
    _request("PUT", f"{API}/videos", token=token, params={"part": "snippet"}, json_body=body)


def _rtmp_target(stream: Dict[str, Any]) -> str:
    info = (stream.get("cdn") or {}).get("ingestionInfo") or {}
    address = str(info.get("rtmpsIngestionAddress") or info.get("ingestionAddress") or "").rstrip("/")
    name = str(info.get("streamName") or "").strip()
    if not address or not name:
        raise RuntimeError(f"Ingestion info incompleta: {info}")
    return f"{address}/{name}"


def _start_ffmpeg(video_path: str, target: str) -> subprocess.Popen:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-re", "-i", video_path,
        "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high", "-level", "4.1",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60", "-keyint_min", "60",
        "-b:v", "4500k", "-maxrate", "4500k", "-bufsize", "9000k",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-f", "flv", target,
    ]
    return subprocess.Popen(cmd)


def _publish_fallback_regular(
    token: str,
    package: Dict[str, str],
    full_meta: Dict[str, Any],
    short_meta: Dict[str, Any] | None,
    gerar_short: bool,
    category_id: str,
    privacy: str,
    tags: Sequence[str],
) -> Tuple[str, str]:
    full_id = upload_video(
        access_token=token,
        video_path=package["completo"],
        title=full_meta["title"],
        description=full_meta["description"],
        tags=tags,
        category_id=category_id,
        privacy_status=privacy,
    )
    upload_thumbnail(token, full_id, package["poster"])
    short_url = ""
    if gerar_short and short_meta:
        short_id = upload_video(
            access_token=token,
            video_path=package["short"],
            title=short_meta["title"],
            description=short_meta["description"],
            tags=short_meta["tags"],
            category_id=category_id,
            privacy_status=privacy,
        )
        short_url = build_watch_url(short_id)
    return build_watch_url(full_id), short_url


def publish_day_as_live(
    date: str,
    targets: Sequence[Tuple[str, str, str]],
    rows: Sequence[Tuple[int, Dict[str, Any]]],
    worksheet,
    daily_index: int,
    cofre_get,
    cofre_cache: Dict[str, Any],
    *,
    dry_run: bool,
    pause: float,
    timezone: str,
) -> int:
    resultados = [data for _sheet_row, data in rows]
    row_numbers = [sheet_row for sheet_row, _data in rows]
    gerar_short = queue._special_short(resultados)
    full_meta = queue._metadata(resultados, "completo")
    short_meta = queue._metadata(resultados, "short") if gerar_short else None

    if dry_run:
        queue._log(f"PREVISÃO LIVE: {date} com {len(resultados)} resultados.")
        return 0

    package = gerar_pacote_diario(resultados, output_dir="output", gerar_short=gerar_short)
    accounts = listar_contas_youtube(cofre_cache)
    if not accounts:
        raise RuntimeError("Nenhuma conta YOUTUBE com REFRESH_TOKEN no Cofre.")

    successes = 0
    first_full_url = ""
    first_short_url = ""

    for account in accounts:
        client_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
        client_secret = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
        refresh_token = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
        privacy = _cofre_get_safe(cofre_get, "YOUTUBE", "PRIVACY_STATUS", conta=account, default="public") or "public"
        category_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CATEGORY_ID", conta=account, default="24") or "24"
        custom_tags = _parse_tags(_cofre_get_safe(cofre_get, "YOUTUBE", "TAGS", conta=account, default=""))
        if not (client_id and client_secret and refresh_token):
            continue
        token = get_access_token(client_id, client_secret, refresh_token)
        full_tags = _unique_tags(custom_tags, full_meta["tags"])

        try:
            broadcast = ensure_daily_live_for_account(token, date, targets, timezone, privacy)
            broadcast_id = str(broadcast.get("id") or "").strip()
            stream_id = str(broadcast.get("_stream_id") or (broadcast.get("contentDetails") or {}).get("boundStreamId") or "").strip()
            if not broadcast_id or not stream_id:
                raise RuntimeError("Broadcast/stream sem identificadores após preparação.")

            stream = _stream_details(token, stream_id)
            target = _rtmp_target(stream)
            process = _start_ffmpeg(package["completo"], target)
            _wait_stream_active(token, stream_id)
            _transition(token, broadcast_id, "live")
            rc = process.wait()
            if rc != 0:
                raise RuntimeError(f"FFmpeg terminou com código {rc}")
            time.sleep(8)
            try:
                _transition(token, broadcast_id, "complete")
            except Exception as complete_error:
                queue._log(f"[{account}] Aviso ao encerrar live: {complete_error}")
            _update_video_metadata(token, broadcast_id, full_meta, category_id, full_tags)
            try:
                upload_thumbnail(token, broadcast_id, package["poster"])
            except Exception as thumbnail_error:
                queue._log(f"[{account}] Replay salvo, mas capa final não aplicada: {thumbnail_error}")

            short_url = ""
            if gerar_short and short_meta:
                short_id = upload_video(
                    access_token=token,
                    video_path=package["short"],
                    title=short_meta["title"],
                    description=short_meta["description"],
                    tags=_unique_tags(custom_tags, short_meta["tags"]),
                    category_id=category_id,
                    privacy_status=privacy,
                )
                short_url = build_watch_url(short_id)

            full_url = build_watch_url(broadcast_id)
            first_full_url = first_full_url or full_url
            first_short_url = first_short_url or short_url
            successes += 1
            queue._log(f"[{account}] Live diária concluída no mesmo URL: {full_url}")
        except Exception as live_error:
            queue._log(f"[{account}] Live não disponível; aplicando fallback de upload normal: {live_error}")
            traceback.print_exc()
            try:
                full_url, short_url = _publish_fallback_regular(
                    token, package, full_meta, short_meta, gerar_short, category_id, privacy, full_tags
                )
                first_full_url = first_full_url or full_url
                first_short_url = first_short_url or short_url
                successes += 1
                queue._log(f"[{account}] Fallback publicado: {full_url}")
            except Exception as fallback_error:
                queue._log(f"[{account}] Falha também no fallback: {fallback_error}")
                traceback.print_exc()
        time.sleep(max(0.5, min(pause, 15.0)))

    if successes <= 0 or not first_full_url:
        return 0

    final_mark = (
        f"Publicado YOUTUBE DIÁRIO V22 LIVE em {_ts_br(timezone)} | Completo: {first_full_url}"
    )
    if gerar_short:
        final_mark += f" | Short: {first_short_url or 'falhou'}"
    else:
        final_mark += " | Short: não necessário"
    queue._mark_rows(worksheet, row_numbers, daily_index, final_mark)
    queue._write_step_summary(
        "## Publicação diária V22",
        f"- Data: **{date}**",
        f"- Mesmo URL desde o alerta: {first_full_url}",
        f"- Resultados reunidos: **{len(resultados)}**",
        f"- Short: {first_short_url if gerar_short else 'não necessário'}",
        f"- Canais publicados: **{successes}**",
    )
    return 1
