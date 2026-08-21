from __future__ import annotations

"""Patch V22 LIVE: mantém uma única Live por dia, aplica a capa uma vez e registra o aviso."""

import os
from datetime import datetime
from typing import Any, Dict, Sequence, Tuple
from zoneinfo import ZoneInfo

import youtube_daily_live_v22 as live
from post_video import _cofre_get_safe, listar_contas_youtube
from youtube_auth import get_access_token
from youtube_upload import build_watch_url, upload_thumbnail
from youtube_thumbnail_v24 import gerar_capa_live

_ORIGINAL_ENSURE = live.ensure_daily_lives
_ORIGINAL_PUBLISH = live.publish_day_as_live
ALERT_SHEET_DEFAULT = "YOUTUBE_ALERTAS"
API_CALENDAR_SHEET_ID_DEFAULT = "1gHenJLO5Qr23wWLgmRUXHldaDsUdKcICeFR1Ee621X8"


def _account_credentials(cofre_get, account: str):
    client_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
    client_secret = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
    refresh_token = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
    privacy = _cofre_get_safe(cofre_get, "YOUTUBE", "PRIVACY_STATUS", conta=account, default="public") or "public"
    return client_id, client_secret, refresh_token, privacy


def _registrar_alerta(date: str, account: str, video_id: str, timezone: str) -> None:
    if not video_id:
        return
    try:
        client = live.queue._google_client()
        sheet_id = os.getenv("YOUTUBE_API_CALENDAR_SHEET_ID", API_CALENDAR_SHEET_ID_DEFAULT).strip()
        tab = os.getenv("YOUTUBE_DAILY_ALERT_SHEET", ALERT_SHEET_DEFAULT).strip() or ALERT_SHEET_DEFAULT
        ws = client.open_by_key(sheet_id).worksheet(tab)
        values = ws.get_all_values()
        headers = [str(x or "").strip().casefold() for x in (values[0] if values else [])]
        required = ["data", "conta", "assinatura", "url", "publicadoem", "status"]
        if not all(name in headers for name in required):
            live.queue._log(f"[{account}] YOUTUBE_ALERTAS com cabeçalhos inválidos; registro não gravado.")
            return
        idx = {name: headers.index(name) for name in required}
        url = build_watch_url(video_id)
        stamp = datetime.now(ZoneInfo(timezone)).strftime("%d/%m/%Y %H:%M")
        signature = f"LIVE-{date.replace('/', '')}-{video_id[:6]}"
        for sheet_row, row in enumerate(values[1:], start=2):
            row_date = str(row[idx["data"]] if idx["data"] < len(row) else "").strip()
            row_account = str(row[idx["conta"]] if idx["conta"] < len(row) else "").strip().casefold()
            if row_date == date and row_account == str(account).strip().casefold():
                ws.update_cell(sheet_row, idx["url"] + 1, url)
                ws.update_cell(sheet_row, idx["status"] + 1, "AGUARDANDO_RESULTADOS")
                return
        row = [""] * len(headers)
        row[idx["data"]] = date
        row[idx["conta"]] = account
        row[idx["assinatura"]] = signature
        row[idx["url"]] = url
        row[idx["publicadoem"]] = stamp
        row[idx["status"]] = "AGUARDANDO_RESULTADOS"
        ws.append_row(row, value_input_option="USER_ENTERED")
        live.queue._log(f"[{account}] Aviso diário registrado em YOUTUBE_ALERTAS: {url}")
    except Exception as exc:
        live.queue._log(f"[{account}] Falha ao registrar aviso diário: {exc}")


def ensure_daily_lives(
    date: str,
    targets: Sequence[Tuple[str, str, str]],
    cofre_get,
    cofre_cache: Dict[str, Any],
    *,
    timezone: str,
    prize_highlight: Dict[str, str] | None = None,
):
    existing_before = set()
    tokens: Dict[str, str] = {}

    for account in listar_contas_youtube(cofre_cache):
        client_id, client_secret, refresh_token, _privacy = _account_credentials(cofre_get, account)
        if not (client_id and client_secret and refresh_token):
            continue
        try:
            token = get_access_token(client_id, client_secret, refresh_token)
            tokens[account] = token
            if live._find_daily_broadcast(token, date):
                existing_before.add(account)
        except Exception as exc:
            live.queue._log(f"[{account}] Não foi possível verificar Live existente: {exc}")

    urls = _ORIGINAL_ENSURE(date, targets, cofre_get, cofre_cache, timezone=timezone)

    thumb = None
    found_count = 0
    for account, token in tokens.items():
        try:
            broadcast = live._find_daily_broadcast(token, date)
            if not broadcast:
                live.queue._log(f"[{account}] ERRO: Live de {date} não encontrada após ensure_daily_lives.")
                continue
            video_id = str(broadcast.get("id") or "").strip()
            if not video_id:
                continue
            found_count += 1
            _registrar_alerta(date, account, video_id, timezone)
            if account in existing_before:
                live.queue._log(f"[{account}] Live já existia; thumbnail não será reenviada.")
                continue
            if thumb is None:
                thumb = gerar_capa_live(date, targets, prize_highlight=prize_highlight or {})
            try:
                upload_thumbnail(token, video_id, thumb)
                live.queue._log(f"[{account}] Capa aplicada uma única vez na nova Live: {video_id}")
            except Exception as exc:
                live.queue._log(f"[{account}] Capa da nova Live não aplicada: {exc}")
        except Exception as exc:
            live.queue._log(f"[{account}] Falha pós-criação da Live: {exc}")

    if tokens and found_count == 0:
        raise RuntimeError(f"Nenhuma Live/aviso de {date} foi criada ou localizada.")
    return urls


def publish_day_as_live(
    date,
    targets,
    rows,
    worksheet,
    daily_index,
    cofre_get,
    cofre_cache: Dict[str, Any],
    *,
    dry_run,
    pause,
    timezone,
    prize_highlight=None,
):
    return _ORIGINAL_PUBLISH(
        date,
        targets,
        rows,
        worksheet,
        daily_index,
        cofre_get,
        cofre_cache,
        dry_run=dry_run,
        pause=pause,
        timezone=timezone,
    )


live.ensure_daily_lives = ensure_daily_lives
live.publish_day_as_live = publish_day_as_live
