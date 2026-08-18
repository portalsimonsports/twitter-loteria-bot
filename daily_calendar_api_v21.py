from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Sequence, Tuple
from zoneinfo import ZoneInfo

import daily_queue_v19 as queue


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
    """Retorna (chave_loteria, nome_exibicao, concurso) previstos exatamente para a data."""
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
        # Loteca mantém seu publicador específico já aprovado.
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


def _find_today_rows(
    values: List[List[str]],
    headers: List[str],
    daily_index: int,
    date: str,
    targets: Sequence[Tuple[str, str, str]],
) -> Tuple[List[Tuple[int, Dict[str, Any]]], List[str]]:
    wanted = {(key, contest): display for key, display, contest in targets}
    found: Dict[Tuple[str, str], Tuple[int, Dict[str, Any], str]] = {}

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

    ordered: List[Tuple[int, Dict[str, Any]]] = []
    for key, _display, contest in targets:
        sheet_row, data, marker = found[(key, contest)]
        if queue._is_daily_final_marker(marker):
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

    imported = history_imported_map(history_values)
    waiting_history = [
        f"{display} {contest}"
        for key, display, contest in targets
        if imported.get(key) != contest
    ]
    if waiting_history:
        queue._log("Aguardando atualização oficial: " + ", ".join(waiting_history))
        queue._write_step_summary(
            "## Aguardando resultados oficiais",
            f"- Data: **{date}**",
            "- Programadas: " + ", ".join(f"{display} {contest}" for _key, display, contest in targets),
            "- Ainda não importadas: " + ", ".join(waiting_history),
            "- Publicações: **0**",
        )
        return 0

    headers = list(values[0])
    daily_column = os.getenv("PUBLICADO_YT_DIARIO_COL", queue.DAILY_COLUMN_DEFAULT)
    daily_index = queue._ensure_column(worksheet, headers, daily_column)
    rows, missing_rows = _find_today_rows(values, headers, daily_index, date, targets)
    if not rows:
        if missing_rows == ["JÁ PUBLICADO"]:
            queue._log(f"Resumo diário {date} já publicado.")
            return 0
        queue._log("API já atualizada, mas a base de publicação ainda aguarda: " + ", ".join(missing_rows))
        queue._write_step_summary(
            "## API pronta; aguardando base de publicação",
            f"- Data: **{date}**",
            "- Pendências na ImportadosBlogger2: " + ", ".join(missing_rows),
            "- Publicações: **0**",
        )
        return 0

    queue._log(
        f"SINAL VERDE {date}: todos os {len(targets)} concursos previstos foram importados e estão na base. "
        "Gerando o resumo diário imediatamente."
    )
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
