from __future__ import annotations

import os
import re
import traceback
from datetime import datetime
from typing import Any, Dict, List, Sequence, Tuple
from zoneinfo import ZoneInfo

import caixa_direct_fallback_v23 as caixa_fallback
import daily_queue_v19 as queue
import youtube_daily_alert_v25 as alert


API_CALENDAR_SHEET_ID_DEFAULT = "1gHenJLO5Qr23wWLgmRUXHldaDsUdKcICeFR1Ee621X8"
API_CALENDAR_TAB_DEFAULT = "API_CALENDARIO_LOTERIAS"
API_HISTORY_CONFIG_TAB_DEFAULT = "CONFIG_HISTORICO_CAIXA"


def _header_index(headers: Sequence[str], *names: str) -> int | None:
    normalized = [queue._normalize(item) for item in headers]
    for name in names:
        target = queue._normalize(name)
        if target in normalized:
            return normalized.index(target)
    return None


def _cell(row: Sequence[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _contest_key(value: Any) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    return digits or str(value or "").strip()


def _today(tz_name: str) -> str:
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = datetime.now()
    return now.strftime("%d/%m/%Y")


def targets_for_date(calendar_values: List[List[str]], date: str) -> List[Tuple[str, str, str]]:
    if not calendar_values:
        return []
    headers = calendar_values[0]
    i_lottery = _header_index(headers, "loteria")
    i_contest = _header_index(headers, "proximoConcurso", "proximo concurso")
    i_date = _header_index(headers, "dataProximoConcurso", "data proximo concurso")
    i_status = _header_index(headers, "statusCalendario", "status calendario")

    targets: List[Tuple[str, str, str]] = []
    for row in calendar_values[1:]:
        lottery = _cell(row, i_lottery)
        contest = _contest_key(_cell(row, i_contest))
        next_date = _cell(row, i_date)
        status = queue._normalize(_cell(row, i_status))
        key = queue._lottery_key(lottery)
        if not lottery or not contest or next_date != date:
            continue
        if status and "programado" not in status:
            continue
        if key == "loteca":
            continue
        targets.append((key, queue._display_lottery(lottery), contest))
    return targets


def history_imported_map(history_values: List[List[str]]) -> Dict[str, str]:
    if not history_values:
        return {}
    headers = history_values[0]
    i_lottery = _header_index(headers, "loteria")
    i_imported = _header_index(headers, "ultimoImportado", "ultimo importado")
    imported: Dict[str, str] = {}
    for row in history_values[1:]:
        key = queue._lottery_key(_cell(row, i_lottery))
        contest = _contest_key(_cell(row, i_imported))
        if key and contest:
            imported[key] = contest
    return imported


def _find_today_rows(values, headers, daily_index, date, targets):
    wanted = {(key, contest): display for key, display, contest in targets}
    found = {}
    for sheet_row, row in enumerate(values[1:], start=2):
        try:
            data = queue._row_data(row, headers)
            queue._validate_video_data(data)
        except Exception:
            continue
        if str(data.get("data") or "").strip() != date:
            continue
        key = queue._lottery_key(data.get("loteria"))
        contest = _contest_key(data.get("concurso"))
        pair = (key, contest)
        if pair not in wanted:
            continue
        marker = row[daily_index] if daily_index < len(row) else ""
        found[pair] = (sheet_row, data, marker)

    missing = [display for key, display, contest in targets if (key, contest) not in found]
    if missing:
        return [], missing

    ordered = []
    for key, _display, contest in targets:
        sheet_row, data, marker = found[(key, contest)]
        marker_upper = str(marker or "").upper()
        if queue._is_daily_final_marker(marker) or "YOUTUBE DIÁRIO V22 LIVE" in marker_upper or "YOUTUBE DIARIO V22 LIVE" in marker_upper:
            return [], ["JÁ PUBLICADO"]
        ordered.append((sheet_row, data))
    return ordered, []


def processar_resumo_por_calendario_api() -> int:
    config = queue.carregar_config()
    client = queue._google_client()
    cofre_cache, cofre_get = queue._load_cofre(client, config)

    main_spreadsheet = client.open_by_key(config.google_sheet_id)
    worksheet = main_spreadsheet.worksheet(config.sheet_tab)
    values = worksheet.get_all_values()
    if not values:
        raise RuntimeError("A planilha principal está vazia.")

    api_sheet_id = os.getenv("YOUTUBE_API_CALENDAR_SHEET_ID", API_CALENDAR_SHEET_ID_DEFAULT).strip()
    api_calendar_tab = os.getenv("YOUTUBE_API_CALENDAR_TAB", API_CALENDAR_TAB_DEFAULT).strip()
    api_history_tab = os.getenv("YOUTUBE_API_HISTORY_CONFIG_TAB", API_HISTORY_CONFIG_TAB_DEFAULT).strip()
    api_spreadsheet = client.open_by_key(api_sheet_id)
    calendar_values = api_spreadsheet.worksheet(api_calendar_tab).get_all_values()
    history_values = api_spreadsheet.worksheet(api_history_tab).get_all_values()

    date = _today(config.timezone)
    targets = targets_for_date(calendar_values, date)
    if not targets:
        message = f"{date}: nenhuma loteria comum programada na API_CALENDARIO_LOTERIAS."
        queue._log(message)
        queue._write_step_summary("## Calendário oficial", f"- {message}", "- Publicações: **0**")
        return 0

    # FASE 1 — publica uma única vez o vídeo de alerta do dia, a partir do calendário oficial.
    # O controle fica na aba YOUTUBE_ALERTAS e também reconcilia os uploads recentes do canal,
    # evitando duplicidade mesmo em execuções horárias.
    alert_urls: List[str] = []
    try:
        alert_urls = alert.ensure_daily_alerts(
            date,
            targets,
            cofre_get,
            cofre_cache,
            api_spreadsheet,
            dry_run=config.dry_run,
            timezone=config.timezone,
        )
    except Exception as error:
        queue._log(f"Alerta diário indisponível nesta execução: {error}")
        traceback.print_exc()

    imported = history_imported_map(history_values)
    waiting_history = [
        f"{display} {contest}"
        for key, display, contest in targets
        if imported.get(key) != contest
    ]

    # FASE 2 — se o Apps Script da base estiver atrasado/sem cota de UrlFetch,
    # o próprio GitHub consulta a API oficial da CAIXA. Quando o concurso já existe,
    # grava uma linha mínima em ImportadosBlogger2, sem enfileirar outras redes.
    if waiting_history:
        queue._log(
            "Histórico CAIXA ainda não atualizou: " + ", ".join(waiting_history) +
            ". Tentando fallback direto pela API oficial."
        )
        try:
            inserted = caixa_fallback.append_missing_results(
                worksheet,
                values,
                targets,
                expected_date=date,
                log=queue._log,
            )
            if inserted:
                queue._log(f"Fallback CAIXA inseriu {len(inserted)} resultado(s) oficial(is).")
                values = worksheet.get_all_values()
        except Exception as error:
            queue._log(f"Fallback direto CAIXA falhou sem interromper o workflow: {error}")
            traceback.print_exc()

    headers = list(values[0])
    daily_column = os.getenv("PUBLICADO_YT_DIARIO_COL", queue.DAILY_COLUMN_DEFAULT)
    daily_index = queue._ensure_column(worksheet, headers, daily_column)
    rows, missing_rows = _find_today_rows(values, headers, daily_index, date, targets)

    if not rows:
        if missing_rows == ["JÁ PUBLICADO"]:
            queue._log(f"Resumo diário {date} já publicado.")
            return 0
        queue._log("Aguardando resultados oficiais ainda indisponíveis: " + ", ".join(missing_rows))
        queue._write_step_summary(
            "## Aguardando resultados oficiais",
            f"- Data: **{date}**",
            "- Programadas: " + ", ".join(f"{display} {contest}" for _key, display, contest in targets),
            "- Ainda ausentes: " + ", ".join(missing_rows),
            f"- Alerta do dia: {alert_urls[0] if alert_urls else 'já existente, ainda não iniciado ou indisponível nesta execução'}",
            "- GitHub tentou a API CAIXA diretamente para contornar eventual atraso do Apps Script.",
        )
        return 0

    queue._log(
        f"SINAL VERDE {date}: todos os {len(targets)} concursos previstos estão na base."
    )

    # FASE 3 — publica um NOVO vídeo consolidado de resultados. O vídeo-alerta permanece
    # como chamada do dia; o YouTube não permite substituir o arquivo mantendo o mesmo URL.
    return queue._publish_day(
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


def main() -> None:
    processar_resumo_por_calendario_api()


if __name__ == "__main__":
    main()
