from __future__ import annotations

import os
from datetime import timedelta

import pending_alert_fix_v27 as base


_original_pending_dates = base._pending_dates


def _pending_dates_recent_only(api_spreadsheet, today: str):
    """Mantém auditoria, mas impede pendências antigas de travarem o dia atual."""
    dates = _original_pending_dates(api_spreadsheet, today)
    today_dt = base._date_obj(today)
    if not today_dt:
        return dates
    cutoff = today_dt - timedelta(days=1)
    filtered = []
    for date in dates:
        dt = base._date_obj(date)
        if dt and dt >= cutoff:
            filtered.append(date)
        else:
            base.queue._log(f"{date}: pendência histórica não bloqueante ignorada pelo V28.")
    return filtered


def _process_date_decoupled(
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
    """Live é somente chamada; resultados usam o publicador normal e independente."""
    is_today = date == today
    targets = base.cal.targets_for_date(calendar_values, date) if is_today else base._last_result_targets(calendar_values, date)
    if not targets:
        if not is_today:
            base._mark_orphan_alert_ignored(api_spreadsheet, date, config.timezone)
        else:
            base.queue._log(f"{date}: sem concursos previstos para chamada/publicação.")
        return 0

    prize_highlight = base.cal.largest_prize_for_date(calendar_values, date, targets) if is_today else {}

    imported = base.cal.history_imported_map(history_values)
    waiting_history = [f"{display} {contest}" for key, display, contest in targets if imported.get(key) != contest]
    if waiting_history:
        try:
            inserted = base.caixa_fallback.append_missing_results(
                worksheet,
                values,
                targets,
                expected_date=date,
                log=base.queue._log,
            )
            if inserted:
                values = worksheet.get_all_values()
        except Exception as error:
            base.queue._log(f"Fallback CAIXA {date} falhou: {error}")

    headers = list(values[0])
    daily_column = os.getenv("PUBLICADO_YT_DIARIO_COL", base.queue.DAILY_COLUMN_DEFAULT)
    daily_index = base.queue._ensure_column(worksheet, headers, daily_column)
    rows, missing_rows = base.cal._find_today_rows(values, headers, daily_index, date, targets)

    if is_today:
        try:
            live_urls = base.live.ensure_daily_lives(
                date,
                targets,
                cofre_get,
                cofre_cache,
                timezone=config.timezone,
                prize_highlight=prize_highlight,
            )
            live_url = live_urls[0] if live_urls else ""
            base._upsert_alert_status(
                api_spreadsheet,
                date,
                live_url,
                "CHAMADA_CRIADA | resultados publicados separadamente",
                config.timezone,
            )
            base.queue._log(f"{date}: Live/chamada independente preparada: {live_url}")
        except Exception as error:
            base._upsert_alert_status(
                api_spreadsheet,
                date,
                "",
                f"ERRO_CHAMADA_NAO_BLOQUEANTE: {type(error).__name__}: {error}"[:4500],
                config.timezone,
            )
            base.queue._log(f"{date}: chamada falhou, mas o fluxo de resultados continuará: {error}")

    if not rows:
        if missing_rows == ["JÁ PUBLICADO"]:
            base._mark_alert_final(api_spreadsheet, date, config.timezone)
            return 0
        base.queue._log(f"{date}: aguardando resultados para publicação independente: " + ", ".join(missing_rows))
        return 0

    base.queue._log(
        f"SINAL VERDE {date}: {len(targets)} concurso(s) completo(s); publicando resultado fora da Live/chamada."
    )
    result = base.queue._publish_day(
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
    if result:
        base._mark_alert_final(api_spreadsheet, date, config.timezone)
    return result


def processar_resumo_por_calendario_api_v28() -> int:
    """Executa chamada do dia + publicações independentes, sem bloqueio entre datas."""
    base._pending_dates = _pending_dates_recent_only

    config = base.queue.carregar_config()
    client = base.queue._google_client()
    cofre_cache, cofre_get = base.queue._load_cofre(client, config)

    main_spreadsheet = client.open_by_key(config.google_sheet_id)
    worksheet = main_spreadsheet.worksheet(config.sheet_tab)
    values = worksheet.get_all_values()
    if not values:
        raise RuntimeError("A planilha principal está vazia.")

    api_sheet_id = os.getenv("YOUTUBE_API_CALENDAR_SHEET_ID", base.cal.API_CALENDAR_SHEET_ID_DEFAULT).strip()
    api_calendar_tab = os.getenv("YOUTUBE_API_CALENDAR_TAB", base.cal.API_CALENDAR_TAB_DEFAULT).strip()
    api_history_tab = os.getenv("YOUTUBE_API_HISTORY_CONFIG_TAB", base.cal.API_HISTORY_CONFIG_TAB_DEFAULT).strip()
    api_spreadsheet = client.open_by_key(api_sheet_id)
    calendar_values = api_spreadsheet.worksheet(api_calendar_tab).get_all_values()
    history_values = api_spreadsheet.worksheet(api_history_tab).get_all_values()

    today = base.cal._today(config.timezone)
    pending = _pending_dates_recent_only(api_spreadsheet, today)
    previous_dates = [d for d in pending if d != today]

    published = 0
    for date in previous_dates:
        current_values = worksheet.get_all_values()
        published += _process_date_decoupled(
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

    current_values = worksheet.get_all_values()
    published += _process_date_decoupled(
        today,
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
    return published
