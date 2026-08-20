from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import os
import re

import daily_queue_v19 as queue
import daily_calendar_api_v21 as cal
from post_video import _cofre_get_safe, listar_contas_youtube
from youtube_auth import get_access_token
from youtube_upload import upload_thumbnail
from youtube_thumbnail_v24 import gerar_capa_live

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


def _alert_record_for_date(api_spreadsheet, date: str) -> tuple[str, str, str]:
    sheet_name = os.getenv("YOUTUBE_DAILY_ALERT_SHEET", ALERT_SHEET_DEFAULT).strip() or ALERT_SHEET_DEFAULT
    ws = api_spreadsheet.worksheet(sheet_name)
    values = ws.get_all_values()
    if not values:
        raise RuntimeError(f"Aba {sheet_name} está vazia.")

    headers = [str(x or "").strip().casefold() for x in values[0]]

    def idx(name: str) -> int:
        try:
            return headers.index(name.casefold())
        except ValueError:
            return -1

    i_date = idx("Data")
    i_account = idx("Conta")
    i_url = idx("URL")
    if min(i_date, i_account, i_url) < 0:
        raise RuntimeError(f"Cabeçalhos inválidos na aba {sheet_name}: {headers}")

    for row in reversed(values[1:]):
        def cell(i: int) -> str:
            return str(row[i] if i < len(row) else "").strip()

        if cell(i_date) != date:
            continue
        url = cell(i_url)
        video_id = _extract_video_id(url)
        if video_id:
            return cell(i_account), video_id, url

    raise RuntimeError(f"Nenhum registro de {date} encontrado em {sheet_name}.")


def _credentials_for_account(cofre_get, cofre_cache, sheet_account: str):
    accounts = listar_contas_youtube(cofre_cache)
    if not accounts:
        raise RuntimeError("Nenhuma conta YouTube encontrada no Cofre.")

    wanted = str(sheet_account or "").strip().casefold()
    ordered = sorted(accounts, key=lambda a: 0 if str(a).strip().casefold() == wanted else 1)

    for account in ordered:
        cid = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
        sec = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
        ref = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
        if cid and sec and ref:
            return account, cid, sec, ref

    raise RuntimeError(f"Credenciais YouTube incompletas. Conta da aba: {sheet_account}; contas no Cofre: {accounts}")


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
    sheet_account, video_id, video_url = _alert_record_for_date(api_spreadsheet, date)

    print(f"[REPAIR V26] Data: {date}", flush=True)
    print(f"[REPAIR V26] Registro: conta={sheet_account} videoId={video_id} url={video_url}", flush=True)
    print(f"[REPAIR V26] Loterias: {', '.join(display + ' ' + contest for _key, display, contest in targets)}", flush=True)
    if prize:
        print(f"[REPAIR V26] Maior prêmio: {prize.get('loteria')} {prize.get('premio')}", flush=True)

    thumb = gerar_capa_live(date, targets, prize_highlight=prize)
    print(f"[REPAIR V26] Capa gerada: {thumb}", flush=True)

    account, cid, sec, ref = _credentials_for_account(cofre_get, cofre_cache, sheet_account)
    print(f"[REPAIR V26] Usando credenciais da conta: {account}", flush=True)

    token = get_access_token(cid, sec, ref)
    upload_thumbnail(token, video_id, thumb)

    print(f"[REPAIR V26] SUCESSO: capa aplicada em https://www.youtube.com/watch?v={video_id}", flush=True)
    return 1


if __name__ == "__main__":
    main()
