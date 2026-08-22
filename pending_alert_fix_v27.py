from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Sequence, Tuple
from zoneinfo import ZoneInfo

import caixa_direct_fallback_v23 as caixa_fallback
import daily_calendar_api_v21 as cal
import daily_queue_v19 as queue
import youtube_daily_live_v22 as live

ALERT_SHEET_DEFAULT = "YOUTUBE_ALERTAS"
FINAL_WORDS = (
    "FINALIZADO",
    "CONCLUIDO",
    "PUBLICADO YOUTUBE DIÁRIO",
    "PUBLICADO YOUTUBE DIARIO",
    "RECUPERADO_EM_NOVO_VIDEO",
)


def _date_obj(value: str):
    try:
        return datetime.strptime(str(value or "").strip(), "%d/%m/%Y")
    except ValueError:
        return None


def _last_result_targets(calendar_values: List[List[str]], date: str) -> List[Tuple[str, str, str]]:
    if not calendar_values:
        return []
    headers = calendar_values[0]
    i_lottery = cal._header_index(headers, "loteria")
    i_contest = cal._header_index(headers, "concursoAtual", "concurso atual")
    i_date = cal._header_index(headers, "dataUltimoConcurso", "data ultimo concurso", "data último concurso")

    targets: List[Tuple[str, str, str]] = []
    for row in calendar_values[1:]:
        lottery = cal._cell(row, i_lottery)
        contest = cal._contest_key(cal._cell(row, i_contest))
        result_date = cal._cell(row, i_date)
        key = queue._lottery_key(lottery)
        if not lottery or not contest or result_date != date:
            continue
        if key == "loteca":
            continue
        if not cal._allowed_lottery_on_date(key, result_date):
            continue
        targets.append((key, queue._display_lottery(lottery), contest))
    return targets


def _alert_rows(api_spreadsheet):
    name = os.getenv("YOUTUBE_DAILY_ALERT_SHEET", ALERT_SHEET_DEFAULT).strip() or ALERT_SHEET_DEFAULT
    ws = api_spreadsheet.worksheet(name)
    values = ws.get_all_values()
    if not values:
        return ws, [], {}
    headers = [str(x or "").strip().casefold() for x in values[0]]
    idx = {name: headers.index(name) for name in ("data", "status") if name in headers}
    rows = []
    for sheet_row, row in enumerate(values[1:], start=2):
        date = str(row[idx["data"]] if "data" in idx and idx["data"] < len(row) else "").strip()
        status = str(row[idx["status"]] if "status" in idx and idx["status"] < len(row) else "").strip()
        if date:
            rows.append((sheet_row, date, status))
    return ws, rows, idx


def _upsert_alert_status(api_spreadsheet, date: str, url: str, status: str, timezone: str) -> None:
    name = os.getenv("YOUTUBE_DAILY_ALERT_SHEET", ALERT_SHEET_DEFAULT).strip() or ALERT_SHEET_DEFAULT
    ws = api_spreadsheet.worksheet(name)
    values = ws.get_all_values()
    headers = list(values[0]) if values else []
    wanted = ["Data", "Conta", "Assinatura", "URL", "PublicadoEm", "Status"]
    if not headers:
        ws.append_row(wanted)
        headers = wanted

    norm = [str(x or "").strip().casefold() for x in headers]

    def idx(label: str) -> int:
        try:
            return norm.index(label.casefold())
        except ValueError:
            return -1

    i_date, i_url, i_status = idx("Data"), idx("URL"), idx("Status")
    stamp = datetime.now(ZoneInfo(timezone)).strftime("%d/%m/%Y %H:%M:%S")
    found_row = 0
    for sheet_row, row in enumerate(values[1:], start=2):
        row_date = str(row[i_date] if i_date >= 0 and i_date < len(row) else "").strip()
        if row_date == date:
            found_row = sheet_row
            break

    if found_row:
        if i_url >= 0 and url:
            ws.update_cell(found_row, i_url + 1, url)
        if i_status >= 0:
            ws.update_cell(found_row, i_status + 1, status)
    else:
        ws.append_row([date, "", "LIVE_V27", url, stamp, status])


def _is_final(status: str) -> bool:
    text = str(status or "").upper()
    return any(word in text for word in FINAL_WORDS)


def _pending_dates(api_spreadsheet, today: str) -> List[str]:
    _ws, rows, _idx = _alert_rows(api_spreadsheet)
    today_dt = _date_obj(today)
    dates = set()
    for _row, date, status in rows:
        dt = _date_obj(date)
        if not dt or (today_dt and dt > today_dt) or _is_final(status):
            continue
        dates.add(date)
    return sorted(dates, key=lambda x: _date_obj(x) or datetime.max)


def _mark_alert_final(api_spreadsheet, date: str, timezone: str) -> None:
    ws, rows, idx = _alert_rows(api_spreadsheet)
    if "status" not in idx:
        return
    stamp = datetime.now(ZoneInfo(timezone)).strftime("%d/%m/%Y %H:%M:%S")
    for sheet_row, row_date, status in rows:
        if row_date == date and not _is_final(status):
            ws.update_cell(sheet_row, idx["status"] + 1, f"FINALIZADO | {stamp} | resultado consolidado na Live do dia")


def _publish_legacy_recovery(
    date: str,
    rows,
    worksheet,
    daily_index: int,
    api_spreadsheet,
    cofre_get,
    cofre_cache,
    config,
) -> int:
    """Recupera dias antigos cujo 'alerta' foi um upload comum, não uma Live.

    Um MP4 de upload comum não pode receber outro arquivo no mesmo videoId. Para não deixar
    o resultado do dia sem publicação, publica o consolidado usando o OAuth de upload já válido.
    Este caminho existe somente para corrigir o legado de 20/08; dias novos continuam LIVE.
    """
    result = queue._publish_day(
        date,
        rows,
        worksheet,
        daily_index,
        cofre_get,
        cofre_cache,
        dry_run=config.dry_run,
        pause=config.pausa,
        timezone=config.timezone,
    )
    if not result:
        return 0

    result_url = ""
    for sheet_row, _data in rows:
        marker = worksheet.cell(sheet_row, daily_index + 1).value or ""
        result_url = queue._partial_full_url(marker)
        if result_url:
            break

    stamp = datetime.now(ZoneInfo(config.timezone)).strftime("%d/%m/%Y %H:%M:%S")
    status = (
        f"RECUPERADO_EM_NOVO_VIDEO | {stamp} | alerta antigo era upload comum e não podia receber novo MP4"
        + (f" | resultado={result_url}" if result_url else "")
    )
    _upsert_alert_status(api_spreadsheet, date, result_url, status, config.timezone)
    queue._log(f"{date}: recuperação concluída por upload consolidado: {result_url or 'URL gravada nas linhas da base'}")
    return result


def _process_date(
    date: str,
    *,
    today: str,
    config,
    worksheet,
    values,
    api_spreadsheet,
    calendar_values,
    history_values,
    cofre_get,
    cofre_cache,
) -> int:
    is_today = date == today
    targets = cal.targets_for_date(calendar_values, date) if is_today else _last_result_targets(calendar_values, date)
    if not targets:
        queue._log(f"{date}: sem concursos recuperáveis para processamento do aviso.")
        return 0

    prize_highlight = cal.largest_prize_for_date(calendar_values, date, targets) if is_today else {}

    # Primeiro garante/importa os resultados; dias antigos precisam ser recuperados mesmo se
    # a autorização de Live de hoje estiver sem o escopo youtube.
    imported = cal.history_imported_map(history_values)
    waiting_history = [f"{display} {contest}" for key, display, contest in targets if imported.get(key) != contest]
    if waiting_history:
        try:
            inserted = caixa_fallback.append_missing_results(
                worksheet,
                values,
                targets,
                expected_date=date,
                log=queue._log,
            )
            if inserted:
                values = worksheet.get_all_values()
        except Exception as error:
            queue._log(f"Fallback CAIXA {date} falhou: {error}")

    headers = list(values[0])
    daily_column = os.getenv("PUBLICADO_YT_DIARIO_COL", queue.DAILY_COLUMN_DEFAULT)
    daily_index = queue._ensure_column(worksheet, headers, daily_column)
    rows, missing_rows = cal._find_today_rows(values, headers, daily_index, date, targets)

    # Dia antigo: o aviso de 20/08 foi publicado como vídeo normal de 13s. Não existe como
    # substituir esse MP4. Publica o consolidado agora usando upload scope e encerra o legado.
    if not is_today:
        if not rows:
            if missing_rows == ["JÁ PUBLICADO"]:
                _mark_alert_final(api_spreadsheet, date, config.timezone)
                return 0
            queue._log(f"{date}: recuperação aguardando resultados: " + ", ".join(missing_rows))
            return 0
        return _publish_legacy_recovery(
            date,
            rows,
            worksheet,
            daily_index,
            api_spreadsheet,
            cofre_get,
            cofre_cache,
            config,
        )

    # HOJE e próximos dias: exclusivamente LIVE, como definido pelo usuário.
    try:
        live_urls = live.ensure_daily_lives(
            date,
            targets,
            cofre_get,
            cofre_cache,
            timezone=config.timezone,
            prize_highlight=prize_highlight,
        )
        live_url = live_urls[0] if live_urls else ""
        _upsert_alert_status(api_spreadsheet, date, live_url, "LIVE_CRIADA", config.timezone)
        queue._log(f"{date}: aviso Live registrado: {live_url}")
    except Exception as error:
        message = f"ERRO_LIVE: {type(error).__name__}: {error}"
        _upsert_alert_status(api_spreadsheet, date, "", message[:4500], config.timezone)
        queue._log(f"Live-alerta de {date} FALHOU: {error}")
        raise

    if not rows:
        if missing_rows == ["JÁ PUBLICADO"]:
            _mark_alert_final(api_spreadsheet, date, config.timezone)
            return 0
        queue._log(f"{date}: aguardando resultados: " + ", ".join(missing_rows))
        return 0

    queue._log(f"SINAL VERDE {date}: {len(targets)} concursos completos; transmitindo no aviso Live do próprio dia.")
    result = live.publish_day_as_live(
        date,
        targets,
        rows,
        worksheet,
        daily_index,
        cofre_get,
        cofre_cache,
        dry_run=config.dry_run,
        pause=config.pausa,
        timezone=config.timezone,
        prize_highlight=prize_highlight,
    )
    if result:
        _mark_alert_final(api_spreadsheet, date, config.timezone)
    return result


def processar_resumo_por_calendario_api_v27() -> int:
    config = queue.carregar_config()
    client = queue._google_client()
    cofre_cache, cofre_get = queue._load_cofre(client, config)

    main_spreadsheet = client.open_by_key(config.google_sheet_id)
    worksheet = main_spreadsheet.worksheet(config.sheet_tab)
    values = worksheet.get_all_values()
    if not values:
        raise RuntimeError("A planilha principal está vazia.")

    api_sheet_id = os.getenv("YOUTUBE_API_CALENDAR_SHEET_ID", cal.API_CALENDAR_SHEET_ID_DEFAULT).strip()
    api_calendar_tab = os.getenv("YOUTUBE_API_CALENDAR_TAB", cal.API_CALENDAR_TAB_DEFAULT).strip()
    api_history_tab = os.getenv("YOUTUBE_API_HISTORY_CONFIG_TAB", cal.API_HISTORY_CONFIG_TAB_DEFAULT).strip()
    api_spreadsheet = client.open_by_key(api_sheet_id)
    calendar_values = api_spreadsheet.worksheet(api_calendar_tab).get_all_values()
    history_values = api_spreadsheet.worksheet(api_history_tab).get_all_values()

    today = cal._today(config.timezone)
    pending = _pending_dates(api_spreadsheet, today)

    # Recupera primeiro qualquer dia anterior. Assim um erro de OAuth Live de hoje não impede
    # a correção do resultado de ontem.
    dates = [d for d in pending if d != today]
    dates.append(today)

    published = 0
    first_error = None
    for date in dates:
        current_values = worksheet.get_all_values()
        try:
            published += _process_date(
                date,
                today=today,
                config=config,
                worksheet=worksheet,
                values=current_values,
                api_spreadsheet=api_spreadsheet,
                calendar_values=calendar_values,
                history_values=history_values,
                cofre_get=cofre_get,
                cofre_cache=cofre_cache,
            )
        except Exception as error:
            # Não desfaz nem impede recuperação já executada para datas anteriores.
            first_error = first_error or error
            queue._log(f"{date}: erro mantido para diagnóstico após processar pendências: {error}")

    if first_error:
        raise first_error
    return published


cal.processar_resumo_por_calendario_api = processar_resumo_por_calendario_api_v27
