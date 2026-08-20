from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import os
import requests

import daily_queue_v19 as queue
import daily_calendar_api_v21 as cal
from post_video import _cofre_get_safe, listar_contas_youtube
from youtube_auth import get_access_token
from youtube_upload import upload_thumbnail
from youtube_thumbnail_v24 import gerar_capa_live

API = "https://www.googleapis.com/youtube/v3"


def _today(tz: str) -> str:
    return datetime.now(ZoneInfo(tz)).strftime("%d/%m/%Y")


def _uploads_playlist(token: str) -> str:
    r = requests.get(
        f"{API}/channels",
        headers={"Authorization": f"Bearer {token}"},
        params={"part": "contentDetails", "mine": "true"},
        timeout=30,
    )
    r.raise_for_status()
    items = r.json().get("items") or []
    return (((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") or "") if items else ""


def _today_alert_id(token: str, date: str) -> str:
    playlist = _uploads_playlist(token)
    if not playlist:
        return ""
    r = requests.get(
        f"{API}/playlistItems",
        headers={"Authorization": f"Bearer {token}"},
        params={"part": "snippet,contentDetails", "playlistId": playlist, "maxResults": 25},
        timeout=30,
    )
    r.raise_for_status()
    for item in r.json().get("items") or []:
        title = str((item.get("snippet") or {}).get("title") or "")
        if date in title and "Loterias de Hoje" in title:
            return str((item.get("contentDetails") or {}).get("videoId") or "").strip()
    return ""


def main() -> int:
    cfg = queue.carregar_config()
    client = queue._google_client()
    cofre_cache, cofre_get = queue._load_cofre(client, cfg)

    api_sheet_id = os.getenv("YOUTUBE_API_CALENDAR_SHEET_ID", cal.API_CALENDAR_SHEET_ID_DEFAULT).strip()
    api_tab = os.getenv("YOUTUBE_API_CALENDAR_TAB", cal.API_CALENDAR_TAB_DEFAULT).strip()
    values = client.open_by_key(api_sheet_id).worksheet(api_tab).get_all_values()

    date = _today(cfg.timezone)
    targets = cal.targets_for_date(values, date)
    prize = cal.largest_prize_for_date(values, date, targets)
    thumb = gerar_capa_live(date, targets, prize_highlight=prize)

    updated = 0
    for account in listar_contas_youtube(cofre_cache):
        cid = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
        sec = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
        ref = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
        if not (cid and sec and ref):
            continue

        token = get_access_token(cid, sec, ref)
        vid = _today_alert_id(token, date)
        if not vid:
            continue

        upload_thumbnail(token, vid, thumb)
        updated += 1
        print(f"[REPAIR V26] Capa atualizada: https://www.youtube.com/watch?v={vid}", flush=True)

    if updated == 0:
        raise RuntimeError(f"Nenhum vídeo 'Loterias de Hoje' de {date} foi encontrado para atualizar a capa.")
    return updated


if __name__ == "__main__":
    main()
