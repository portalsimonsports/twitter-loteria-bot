from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

import daily_queue_v19 as queue
from lottery_result_v18 import parse_lottery_result


DailyCandidate = Tuple[str, List[Tuple[int, Dict[str, Any]]], List[str]]


def _expected_by_date_without_loteca(calendar_values: List[List[str]]) -> Dict[str, List[str]]:
    expected = queue._expected_by_date_original(calendar_values)
    cleaned: Dict[str, List[str]] = {}
    for date, lotteries in expected.items():
        values = [item for item in lotteries if queue._lottery_key(item) != "loteca"]
        if values:
            cleaned[date] = values
    return cleaned


def _candidate_dates_without_loteca(
    values: List[List[str]],
    headers: List[str],
    daily_index: int,
    expected_map: Dict[str, List[str]],
    timezone: str = "America/Sao_Paulo",
) -> List[DailyCandidate]:
    start_date = queue._parse_date(
        queue.os.getenv("YOUTUBE_DAILY_START_DATE", queue.DAILY_START_DATE_DEFAULT)
    )
    now_local = queue._now_in_timezone(timezone)
    today = now_local.date()
    cutoff_hour = max(
        0,
        min(
            23,
            queue._env_int(
                "YOUTUBE_DAILY_CUTOFF_HOUR",
                queue.DAILY_CUTOFF_HOUR_DEFAULT,
            ),
        ),
    )
    grouped: Dict[str, Dict[Tuple[str, str], Tuple[int, Dict[str, Any], str]]] = {}

    for sheet_row, row in enumerate(values[1:], start=2):
        try:
            data = queue._row_data(row, headers)
            queue._validate_video_data(data)
        except Exception:
            continue

        lottery_key = queue._lottery_key(data.get("loteria"))
        if lottery_key == "loteca":
            continue

        date = str(data.get("data") or "").strip()
        parsed = queue._parse_date(date)
        if parsed is None or parsed.date() > today:
            continue
        if start_date is not None and parsed.date() < start_date.date():
            continue

        contest = (
            re.sub(r"\D+", "", str(data.get("concurso") or ""))
            or str(data.get("concurso") or "").strip()
        )
        if not lottery_key or not contest:
            continue

        marker = row[daily_index] if daily_index < len(row) else ""
        grouped.setdefault(date, {})[(lottery_key, contest)] = (
            sheet_row,
            data,
            marker,
        )

    candidates: List[DailyCandidate] = []
    for date, unique_rows in grouped.items():
        parsed_date = queue._parse_date(date)
        if parsed_date is None:
            continue

        rows = list(unique_rows.values())
        if any(
            queue._is_daily_final_marker(marker)
            for _sheet_row, _data, marker in rows
        ):
            continue

        actual_modalities = {
            queue._lottery_key(data.get("loteria"))
            for _sheet_row, data, _marker in rows
        }
        expected_order = [
            item
            for item in expected_map.get(date, [])
            if queue._lottery_key(item) != "loteca"
        ]
        is_past_day = parsed_date.date() < today

        if not is_past_day:
            if expected_order:
                missing = [
                    item for item in expected_order if item not in actual_modalities
                ]
                if missing:
                    queue._log(
                        f"Resumo diário {date} aguardando modalidades: "
                        + ", ".join(missing)
                    )
                    continue
            elif now_local.hour < cutoff_hour:
                queue._log(
                    f"Resumo diário {date} sem calendário fechado; aguardando "
                    f"o horário de corte das {cutoff_hour:02d}:00 em {timezone}."
                )
                continue
        else:
            missing = [
                item for item in expected_order if item not in actual_modalities
            ]
            if missing:
                queue._log(
                    f"Resumo diário atrasado {date}: calendário indicava "
                    f"{', '.join(missing)}, mas o dia já encerrou. "
                    "Publicando automaticamente os resultados existentes."
                )

        ordered_keys = [
            key for key in expected_order if key in actual_modalities
        ]
        remaining_keys = sorted(actual_modalities - set(ordered_keys))
        effective_order = ordered_keys + remaining_keys
        order_index = {
            key: index for index, key in enumerate(effective_order)
        }
        rows.sort(
            key=lambda item: (
                order_index.get(
                    queue._lottery_key(item[1].get("loteria")),
                    999,
                ),
                queue._display_lottery(item[1].get("loteria")),
                str(item[1].get("concurso") or ""),
            )
        )
        candidates.append(
            (
                date,
                [
                    (sheet_row, data)
                    for sheet_row, data, _marker in rows
                ],
                effective_order,
            )
        )

    candidates.sort(key=lambda item: queue._date_sort_key(item[0]))
    return candidates


def _compact_result_with_dupla(data: Dict[str, Any]) -> str:
    lottery = queue._display_lottery(data.get("loteria"))
    raw = (
        data.get("numeros")
        or data.get("descricao")
        or data.get("Descrição")
        or ""
    )
    parts = parse_lottery_result(lottery, raw)
    if not parts.second_draw_numbers:
        return queue._compact_result_original(data)

    contest = str(data.get("concurso") or "").strip()
    first = ", ".join(parts.main_numbers)
    second = ", ".join(parts.second_draw_numbers)
    result = (
        f"{lottery} {contest}: 1º sorteio: {first} | "
        f"2º sorteio: {second}"
    )
    prize = str(data.get("premiacao") or "").strip()
    winners = str(data.get("ganhadores") or "").strip()
    if prize:
        result += f" | Premiação: {prize}"
    if winners:
        result += f" | Ganhadores: {winners}"
    return result


def install_daily_policy_fix() -> None:
    if not hasattr(queue, "_expected_by_date_original"):
        queue._expected_by_date_original = queue._expected_by_date
    if not hasattr(queue, "_compact_result_original"):
        queue._compact_result_original = queue._compact_result

    queue._expected_by_date = _expected_by_date_without_loteca
    queue._candidate_dates = _candidate_dates_without_loteca
    queue._compact_result = _compact_result_with_dupla


install_daily_policy_fix()


__all__ = ["install_daily_policy_fix"]
