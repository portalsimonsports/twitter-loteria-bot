from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import os
import re
import requests

import daily_queue_v19 as queue
import daily_calendar_api_v21 as cal
from post_video import _cofre_get_safe, listar_contas_youtube
from youtube_auth import get_access_token
from youtube_upload import upload_thumbnail
from youtube_thumbnail_v24 import gerar_capa_live

API = "https://www.googleapis.com/youtube/v3"
ALERT_SHEET_DEFAULT = "YOUTUBE_ALERTAS"


def _today(tz: str) -> str:
    return datetime.now(ZoneInfo(tz)).strftime("%d/%m/%Y")


def _extract_video_id(value: str) -> str:
    text = str(value or "").strip()
    for pattern in (
        r"youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})",
        r"youtu\.be/([A-Za-z0-9_-]{6,})",
    ):
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return ""


def _video_id_from_alert_sheet(api_spreadsheet, date: str, account: str) -> str:
    sheet_name = os.getenv("YOUTUBE_DAILY_ALERT_SHEET", ALERT_SHEET_DEFAULT).strip() or ALERT_SHEET_DEFAULT
    try:
        ws = api_spreadsheet.worksheet(sheet_name)
    except Exception as exc:
        print(f"[REPAIR V26] Aba {sheet_name} não encontrada: {exc}", flush=True)
        return ""

    values = ws.get_all_values()
    if not values:
        return ""
    headers = [str(x or "").strip().casefold() for x in values[0]]

    def idx(name: str) -> int:
        try:
            return headers.index(name.casefold())
        except ValueError:
            return -1

    i_date = idx("Data")
    i_account = idx("Conta")
    i_url = idx("URL")

    for row in reversed(values[1:]):
        def cell(i: int) -> str:
            return str(row[i] if i >= 0 and i < len(row) else "").strip()
        if cell(i_date) != date:
            continue
        row_account = cell(i_account)
        if row_account and account and row_account != account:
            continue
        video_id = _extract_video_id(cell(i_url))
        if video_id:
            print(f"[REPAIR V26] [{account}] vídeo localizado pela aba {sheet_name}: {video_id}", flush=True)
            return video_id
    return ""


def _video_id_from_recent_uploads(token: str) -> str:
    try:
        r = requests.get(
            f"{API}/channels",
            headers={"Authorization": f"Bearer {token}"},
            params={"part": "contentDetails", "mine": "true"},
            timeout=30,
        )
        if not r.ok:
            print(f"[REPAIR V26] Busca via channels indisponível: HTTP {r.status_code}", flush=True)
            return ""
        items = r.json().get("items") or []
        if not items:
            return ""
        playlist = (((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") or "")
        if not playlist:
            return ""
        r = requests.get(
            f"{API}/playlistItems",
            headers={"Authorization": f"Bearer {token}"},
            params={"part": "snippet,contentDetails", "playlistId": playlist, "maxResults": 25},
            timeout=30,
        )
        if not r.ok:
            return ""
        for item in r.json().get("items") or []:
            title = str((item.get("snippet") or {}).get("title") or "").strip().casefold()
            if "loterias de hoje" in title:
                return str((item.get("contentDetails") or {}).get("videoId") or "").strip()
    except Exception as exc:
        print(f"[REPAIR V26] Busca via YouTube ignorada: {exc}", flush=True)
    return ""


def _try_update_metadata(token: str, video_id: str, date: str, targets, prize: dict) -> None:
    names = ", ".join(display for _key, display, _contest in targets[:4])
    title = f"Loterias de Hoje — {names} | {date}" if names else f"Loterias de Hoje | {date}"
    if len(title) > 95:
        title = f"Loterias de Hoje — Sorteios e Resultados | {date}"
    lines = [f"Loterias programadas para hoje, {date}:"]
    for _key, display, contest in targets:
        lines.append(f"• {display} — concurso {contest}")
    if prize:
        lines += ["", f"Maior prêmio estimado do dia: {prize.get('loteria','')} — {prize.get('premio','')}"]
    lines += ["", "Inscreva-se no canal e ative o sino para receber as atualizações assim que os resultados oficiais forem confirmados."]
    body = {"id": video_id, "snippet": {"title": title[:95], "description": "\n".join(lines)[:4500], "categoryId": "24"}}
    r = requests.put(
        f"{API}/videos",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        params={"part": "snippet"},
        json=body,
        timeout=60,
    )
    if r.ok:
        print(f"[REPAIR V26] Metadados atualizados: {video_id}", flush=True)
    else:
        print(f"[REPAIR V26] Metadados não atualizados (não bloqueante): HTTP {r.status_code} {r.text[:500]}", flush=True)


def main() -> int:
    cfg = queue.carregar_config()
    client = queue._google_client()
    cofre_cache, cofre_get = queue._load_cofre(client, cfg)

    api_sheet_id = os.getenv("YOUTUBE_API_CALENDAR_SHEET_ID", cal.API_CALENDAR_SHEET_ID_DEFAULT).strip()
    api_tab = os.getenv("YOUTUBE_API_CALENDAR_TAB", cal.API_CALENDAR_TAB_DEFAULT).strip()
    api_spreadsheet = client.open_by_key(api_sheet_id)
    values = api_spreadsheet.worksheet(api_tab).get_all_values()

    date = _today(cfg.timezone)
    targets = cal.targets_for_date(values, date)
    if not targets:
        raise RuntimeError(f"Nenhuma loteria válida encontrada para {date}.")

    prize = cal.largest_prize_for_date(values, date, targets)
    thumb = gerar_capa_live(date, targets, prize_highlight=prize)
    print(f"[REPAIR V26] Capa gerada: {thumb}", flush=True)
    if prize:
        print(f"[REPAIR V26] Destaque: {prize.get('loteria')} {prize.get('premio')}", flush=True)

    updated = 0
    errors = []
    for account in listar_contas_youtube(cofre_cache):
        cid = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
        sec = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
        ref = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
        if not (cid and sec and ref):
            continue
        try:
            token = get_access_token(cid, sec, ref)
            # Primeiro usa o URL que o próprio publicador gravou na planilha. Isso não exige
            # escopo YouTube de leitura e funciona com o refresh token antigo de upload.
            vid = _video_id_from_alert_sheet(api_spreadsheet, date, account)
            if not vid:
                vid = _video_id_from_recent_uploads(token)
            if not vid:
                errors.append(f"{account}: videoId não localizado")
                continue

            _try_update_metadata(token, vid, date, targets, prize)
            upload_thumbnail(token, vid, thumb)
            updated += 1
            print(f"[REPAIR V26] CAPA ATUALIZADA: https://www.youtube.com/watch?v={vid}", flush=True)
        except Exception as exc:
            errors.append(f"{account}: {exc}")
            print(f"[REPAIR V26] [{account}] ERRO: {exc}", flush=True)

    if updated == 0:
        raise RuntimeError("Falha ao atualizar a capa do alerta. " + " | ".join(errors))
    return updated


if __name__ == "__main__":
    main()
