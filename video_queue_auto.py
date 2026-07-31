from __future__ import annotations

import os
import re
import time
import traceback
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
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

Candidate = Tuple[int, Sequence[str], Dict[str, Any], datetime | None]


def _env_bool(name: str, default: bool = False) -> bool:
    value = (os.getenv(name, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "sim", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 3650) -> int:
    try:
        value = int((os.getenv(name, str(default)) or str(default)).strip())
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _env_list(name: str) -> set[str]:
    raw = (os.getenv(name, "") or "").replace(";", ",")
    return {_lottery_key(item) for item in raw.split(",") if _lottery_key(item)}


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


def _lottery_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return "-".join(part for part in "".join(ch if ch.isalnum() else " " for ch in ascii_text).split())


def _contest_key(value: Any) -> str:
    text = str(value or "").strip()
    digits = re.sub(r"\D+", "", text)
    return digits or _lottery_key(text)


def _target_filters() -> Tuple[str, str]:
    return (
        _lottery_key(os.getenv("VIDEO_TARGET_MODALITY", "")),
        _contest_key(os.getenv("VIDEO_TARGET_CONTEST", "")),
    )


def _legacy_scheduled_workflow_should_skip() -> bool:
    workflow = (os.getenv("GITHUB_WORKFLOW", "") or "").strip()
    event_name = (os.getenv("GITHUB_EVENT_NAME", "") or "").strip().lower()
    migration_marker = Path("launch_ultimos_concursos_2026_07_30.txt")
    return (
        workflow == "Publicação de Vídeos (YouTube)"
        and event_name == "schedule"
        and migration_marker.is_file()
    )


def _recent_published_counts(
    values: List[List[str]],
    headers: List[str],
    published_index: int,
) -> Dict[str, int]:
    balance_days = _env_int("VIDEO_MODALITY_BALANCE_DAYS", 30, 1, 3650)
    cutoff = datetime.now() - timedelta(days=balance_days)
    counts: Dict[str, int] = {}
    for row in values[1:]:
        published = row[published_index] if published_index < len(row) else ""
        if _empty(published):
            continue
        try:
            data = _row_to_video_data(row, headers)
        except Exception:
            continue
        result_date = _parse_date(data.get("data"))
        if result_date is not None and result_date < cutoff:
            continue
        key = _lottery_key(data.get("loteria"))
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _candidate_rows(values: List[List[str]], headers: List[str], published_index: int) -> List[Candidate]:
    auto_enqueue = _env_bool("AUTO_ENQUEUE_VIDEOS", True)
    backlog_days = _env_int("VIDEO_BACKLOG_DAYS", 7, 1, 3650)
    allow_old_queued = _env_bool("ALLOW_OLD_QUEUED_VIDEOS", False)
    excluded_modalities = _env_list("VIDEO_EXCLUDE_MODALITIES")
    target_modality, target_contest = _target_filters()
    cutoff = datetime.now() - timedelta(days=backlog_days)
    queue_index = _find_col(headers, ["Enfileirado_Videos", "Enfileirado Videos", "Fila_Video"])
    published_counts = _recent_published_counts(values, headers, published_index)

    candidates: List[Candidate] = []
    for sheet_row, row in enumerate(values[1:], start=2):
        published = row[published_index] if published_index < len(row) else ""
        if not _empty(published):
            continue

        queued = queue_index is not None and queue_index < len(row) and _truthy_queue(row[queue_index])
        if not queued and not auto_enqueue:
            continue

        try:
            data = _row_to_video_data(row, headers)
            _validate_video_data(data)
        except Exception:
            continue

        modality_key = _lottery_key(data.get("loteria"))
        contest_key = _contest_key(data.get("concurso"))

        if target_modality and modality_key != target_modality:
            continue
        if target_contest and contest_key != target_contest:
            continue

        if modality_key in excluded_modalities:
            _log(f"Linha {sheet_row} ignorada: modalidade excluída nesta execução ({data.get('loteria')}).")
            continue

        result_date = _parse_date(data.get("data"))
        if result_date is not None and result_date < cutoff and not allow_old_queued:
            _log(
                f"Linha {sheet_row} ignorada: concurso antigo ({data.get('data')}); "
                f"janela automática={backlog_days} dias."
            )
            continue
        candidates.append((sheet_row, row, data, result_date))

    def priority(item: Candidate):
        sheet_row, _row, data, result_date = item
        key = _lottery_key(data.get("loteria"))
        count = published_counts.get(key, 0)
        date_rank = result_date.timestamp() if result_date is not None else float("-inf")
        return count, -date_rank, -sheet_row

    candidates.sort(key=priority)
    return candidates


def _select_diverse(
    candidates: List[Candidate],
    maximum: int,
    *,
    latest_per_modality_only: bool = False,
) -> List[Candidate]:
    selected: List[Candidate] = []
    used_modalities = set()
    for candidate in candidates:
        key = _lottery_key(candidate[2].get("loteria"))
        if key in used_modalities:
            continue
        selected.append(candidate)
        used_modalities.add(key)
        if len(selected) >= maximum:
            return selected

    if latest_per_modality_only:
        return selected

    for candidate in candidates:
        if candidate in selected:
            continue
        selected.append(candidate)
        if len(selected) >= maximum:
            break
    return selected


def processar_fila_automatica() -> int:
    if _legacy_scheduled_workflow_should_skip():
        _log(
            "Agendamento antigo ignorado: a rotina permanente 'Publicar últimos e próximos resultados' "
            "assumiu as publicações automáticas."
        )
        return 0

    config = carregar_config()
    latest_per_modality_only = _env_bool("LATEST_PER_MODALITY_ONLY", False)
    target_modality, target_contest = _target_filters()
    targeted = bool(target_modality or target_contest)
    _log(
        "Fila automática iniciada",
        f"aba={config.sheet_tab}",
        f"máximo={config.max_videos}",
        f"último_por_modalidade={latest_per_modality_only}",
        f"alvo_modalidade={target_modality or '-'}",
        f"alvo_concurso={target_contest or '-'}",
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
        if targeted:
            _log(
                "O resultado informado pelo disparo imediato ainda não foi localizado como pendente na base; "
                "a verificação de segurança tentará novamente."
            )
        else:
            _log("Nenhum resultado pendente elegível para o YouTube.")
        return 0

    if targeted:
        selected = candidates[:1]
    else:
        selected = _select_diverse(
            candidates,
            config.max_videos,
            latest_per_modality_only=latest_per_modality_only,
        )

    _log(
        f"Pendentes elegíveis encontrados: {len(candidates)}; processando {len(selected)} "
        + ("resultado informado pelo evento." if targeted else "com equilíbrio entre modalidades.")
    )
    successes = 0

    for sheet_row, _row, data, _result_date in selected:
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
