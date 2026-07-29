from __future__ import annotations

import os
import time
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, List, Sequence, Tuple

from post_video import publicar_video_em_multicanais
from video_queue import (
    _empty,
    _ensure_column,
    _find_col,
    _google_client,
    _load_cofre,
    _log,
    _row_to_video_data,
    _truthy_queue,
    _validate_video_data,
    carregar_config,
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = (os.getenv(name, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "sim", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 3650) -> int:
    try:
        value = int((os.getenv(name, str(default)) or str(default)).strip())
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    for fmt in (
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def _candidate_rows(values: List[List[str]], headers: List[str], published_index: int) -> List[Tuple[int, Sequence[str], Dict[str, Any], datetime | None]]:
    auto_enqueue = _env_bool("AUTO_ENQUEUE_VIDEOS", True)
    backlog_days = _env_int("VIDEO_BACKLOG_DAYS", 14, 1, 3650)
    cutoff = datetime.now() - timedelta(days=backlog_days)
    queue_index = _find_col(headers, ["Enfileirado_Videos", "Enfileirado Videos", "Fila_Video"])

    candidates: List[Tuple[int, Sequence[str], Dict[str, Any], datetime | None]] = []
    for sheet_row, row in enumerate(values[1:], start=2):
        published = row[published_index] if published_index < len(row) else ""
        if not _empty(published):
            continue

        queued = False
        if queue_index is not None and queue_index < len(row):
            queued = _truthy_queue(row[queue_index])
        if not queued and not auto_enqueue:
            continue

        try:
            data = _row_to_video_data(row, headers)
            _validate_video_data(data)
        except Exception:
            continue

        result_date = _parse_date(data.get("data"))
        if not queued and result_date is not None and result_date < cutoff:
            continue

        candidates.append((sheet_row, row, data, result_date))

    # Publica os resultados mais antigos primeiro dentro do período recente.
    candidates.sort(key=lambda item: (item[3] or datetime.max, item[0]))
    return candidates


def processar_fila_automatica() -> int:
    config = carregar_config()
    _log(
        "Fila automática iniciada",
        f"aba={config.sheet_tab}",
        f"máximo={config.max_videos}",
        f"dry_run={config.dry_run}",
    )

    client = _google_client()
    cofre_cache, cofre_get = _load_cofre(client, config)
    worksheet = client.open_by_key(config.google_sheet_id).worksheet(config.sheet_tab)
    values = worksheet.get_all_values()
    if not values:
        _log("Aba principal vazia.")
        return 0

    headers = list(values[0])
    published_index = _ensure_column(worksheet, headers, config.publicado_col)
    candidates = _candidate_rows(values, headers, published_index)
    if not candidates:
        _log("Nenhum resultado recente pendente para o YouTube.")
        return 0

    _log(f"Pendentes encontrados: {len(candidates)}; processando até {config.max_videos}.")
    successes = 0

    for sheet_row, _row, data, _result_date in candidates[: config.max_videos]:
        try:
            _log(f"Linha {sheet_row}: {data['loteria']} concurso {data.get('concurso') or '-'}")
            result = publicar_video_em_multicanais(
                data,
                cofre_get,
                cofre_cache,
                dry_run=config.dry_run,
                sleep_between_channels=max(0.5, min(config.pausa, 15.0)),
                tz_name=config.timezone,
            )

            if result.get("ok_any"):
                if config.dry_run:
                    _log(f"Linha {sheet_row}: DRY RUN concluído; planilha não alterada.")
                else:
                    worksheet.update_cell(
                        sheet_row,
                        published_index + 1,
                        str(result.get("mark_value") or "Publicado YOUTUBE"),
                    )
                    successes += 1
                    _log(f"Linha {sheet_row}: publicada e marcada na planilha.")
            else:
                _log(f"Linha {sheet_row}: nenhuma publicação concluída. {result.get('mark_value', '')}")
        except Exception as error:
            _log(f"Linha {sheet_row}: ERRO: {error}")
            traceback.print_exc()

        time.sleep(config.pausa)

    _log(f"Fila automática concluída | publicações confirmadas: {successes}")
    return successes


def main() -> None:
    processar_fila_automatica()


if __name__ == "__main__":
    main()
