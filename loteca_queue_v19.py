from __future__ import annotations

import re
import time
import traceback
from typing import Any, Dict, List, Sequence, Tuple

from post_video import publicar_video_em_multicanais
from video_queue import (
    _empty,
    _ensure_column,
    _find_col,
    _google_client,
    _load_cofre,
    _log,
    _norm,
    _row_to_video_data,
    _truthy_queue,
    _validate_video_data,
    carregar_config,
)


def _is_loteca(value: Any) -> bool:
    return "loteca" in _norm(value)


def _candidate_key(data: Dict[str, Any]) -> Tuple[str, str, str]:
    contest = re.sub(r"\D+", "", str(data.get("concurso") or ""))
    date = str(data.get("data") or "").strip()
    result = re.sub(r"\s+", " ", str(data.get("numeros") or "").strip()).casefold()
    return contest, date, result


def processar_loteca_individual() -> int:
    cfg = carregar_config()
    client = _google_client()
    cofre_cache, cofre_get = _load_cofre(client, cfg)
    worksheet = client.open_by_key(cfg.google_sheet_id).worksheet(cfg.sheet_tab)
    values = worksheet.get_all_values()
    if not values:
        _log("Aba principal vazia para a fila exclusiva da Loteca.")
        return 0

    headers = list(values[0])
    queue_index = _ensure_column(worksheet, headers, cfg.enfileirado_col)
    published_index = _ensure_column(worksheet, headers, cfg.publicado_col)

    grouped: Dict[Tuple[str, str, str], List[Tuple[int, Sequence[str], Dict[str, Any]]]] = {}
    for sheet_row, row in enumerate(values[1:], start=2):
        queue_value = row[queue_index] if queue_index < len(row) else ""
        published_value = row[published_index] if published_index < len(row) else ""
        if not _truthy_queue(queue_value) or not _empty(published_value):
            continue

        try:
            data = _row_to_video_data(row, headers)
            _validate_video_data(data)
        except Exception:
            continue
        if not _is_loteca(data.get("loteria")):
            continue

        grouped.setdefault(_candidate_key(data), []).append((sheet_row, row, data))

    if not grouped:
        _log("Nenhuma Loteca pendente para publicação individual.")
        return 0

    ordered = sorted(
        grouped.values(),
        key=lambda group: min(item[0] for item in group),
    )
    successes = 0

    for duplicate_group in ordered[: max(1, cfg.max_videos)]:
        row_numbers = [item[0] for item in duplicate_group]
        data = duplicate_group[-1][2]
        try:
            _log(
                f"Loteca individual selecionada: concurso {data.get('concurso') or '-'} | "
                f"linhas duplicadas={row_numbers}"
            )
            result = publicar_video_em_multicanais(
                data,
                cofre_get,
                cofre_cache,
                dry_run=cfg.dry_run,
                sleep_between_channels=max(0.5, min(cfg.pausa, 15.0)),
                tz_name=cfg.timezone,
            )
            if result.get("ok_any") and not cfg.dry_run:
                marker = str(result.get("mark_value") or "Publicado YOUTUBE LOTeca")
                for row_number in row_numbers:
                    worksheet.update_cell(row_number, published_index + 1, marker)
                successes += 1
                _log(
                    f"Loteca concurso {data.get('concurso') or '-'} publicada separadamente "
                    f"e marcada nas linhas {row_numbers}."
                )
            elif cfg.dry_run:
                _log("Prévia da Loteca concluída; planilha não alterada.")
            else:
                _log(f"Nenhuma publicação da Loteca confirmada: {result.get('mark_value', '')}")
        except Exception as error:
            _log(f"Erro na publicação individual da Loteca: {error}")
            traceback.print_exc()

        time.sleep(max(0.5, min(cfg.pausa, 15.0)))

    if not cfg.dry_run and successes <= 0:
        raise RuntimeError("Havia Loteca pendente, mas nenhuma publicação individual foi confirmada.")
    return successes


def main() -> None:
    processar_loteca_individual()


if __name__ == "__main__":
    main()
