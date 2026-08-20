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


def _alert_record_for_date(api_spreadsheet, date: str):
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
    i_status = idx("Status")
    if i_date < 0 or i_url < 0:
        raise RuntimeError(f"Cabeçalhos inválidos na aba {sheet_name}: {headers}")

    for sheet_row, row in reversed(list(enumerate(values[1:], start=2))):
        def cell(i: int) -> str:
            return str(row[i] if i >= 0 and i < len(row) else "").strip()
        if cell(i_date) != date:
            continue
        url = cell(i_url)
        video_id = _extract_video_id(url)
        if video_id:
            return ws, sheet_row, i_status, cell(i_account), video_id, url

    raise RuntimeError(f"Nenhum registro de {date} encontrado em {sheet_name}.")


def _set_status(ws, row: int, status_index: int, text: str) -> None:
    if status_index < 0:
        return
    try:
        ws.update_cell(row, status_index + 1, str(text)[:500])
    except Exception as exc:
        print(f"[REPAIR V26] não foi possível gravar diagnóstico: {exc}", flush=True)


def main() -> int:
    cfg = queue.carregar_config()
    client = queue._google_client()
    cofre_cache, cofre_get = queue._load_cofre(client, cfg)

    api_sheet_id = os.getenv("YOUTUBE_API_CALENDAR_SHEET_ID", cal.API_CALENDAR_SHEET_ID_DEFAULT).strip()
    api_tab = os.getenv("YOUTUBE_API_CALENDAR_TAB", cal.API_CALENDAR_TAB_DEFAULT).strip()
    api_spreadsheet = client.open_by_key(api_sheet_id)
    calendar_values = api_spreadsheet.worksheet(api_tab).get_all_values()

    date = _today(cfg.timezone)
    targets = cal.targets_for_date(calendar_values, date)
    if not targets:
        print(f"[REPAIR V26] sem loterias válidas em {date}; reparo ignorado", flush=True)
        return 0

    prize = cal.largest_prize_for_date(calendar_values, date, targets)
    ws, sheet_row, status_index, sheet_account, video_id, video_url = _alert_record_for_date(api_spreadsheet, date)

    print(f"[REPAIR V26] alvo={video_url} videoId={video_id} conta_registrada={sheet_account}", flush=True)
    print(f"[REPAIR V26] targets={targets}", flush=True)
    print(f"[REPAIR V26] prize={prize}", flush=True)

    thumb = gerar_capa_live(date, targets, prize_highlight=prize)
    size = os.path.getsize(thumb)
    print(f"[REPAIR V26] thumbnail={thumb} tamanho={size} bytes", flush=True)

    if size > 2_000_000:
        msg = f"ERRO_THUMBNAIL: arquivo {size} bytes excede 2 MB"
        _set_status(ws, sheet_row, status_index, msg)
        print(f"[REPAIR V26] {msg}", flush=True)
        return 0

    accounts = listar_contas_youtube(cofre_cache)
    if not accounts:
        msg = "ERRO_THUMBNAIL: nenhuma conta YouTube com REFRESH_TOKEN no Cofre"
        _set_status(ws, sheet_row, status_index, msg)
        print(f"[REPAIR V26] {msg}", flush=True)
        return 0

    wanted = str(sheet_account or "").strip().casefold()
    accounts = sorted(accounts, key=lambda a: 0 if str(a).strip().casefold() == wanted else 1)

    errors = []
    for account in accounts:
        try:
            client_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
            client_secret = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
            refresh_token = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
            if not (client_id and client_secret and refresh_token):
                errors.append(f"{account}: credenciais incompletas")
                continue

            token = get_access_token(client_id, client_secret, refresh_token)
            upload_thumbnail(token, video_id, thumb)
            msg = f"CAPA_ATUALIZADA | {datetime.now(ZoneInfo(cfg.timezone)).strftime('%d/%m/%Y %H:%M:%S')} | {account}"
            _set_status(ws, sheet_row, status_index, msg)
            print(f"[REPAIR V26] SUCESSO conta={account} url={video_url}", flush=True)
            return 1
        except Exception as exc:
            msg = f"{account}: {type(exc).__name__}: {exc}"
            errors.append(msg)
            print(f"[REPAIR V26] falhou {msg}", flush=True)

    final = "ERRO_THUMBNAIL: " + " | ".join(errors)
    _set_status(ws, sheet_row, status_index, final)
    print(f"[REPAIR V26] {final}", flush=True)
    # Não bloqueia o fluxo Live. O diagnóstico fica persistido na planilha.
    return 0


if __name__ == "__main__":
    main()
