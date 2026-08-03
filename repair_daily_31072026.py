from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Sequence, Set

import requests

from post_video import _cofre_get_safe, listar_contas_youtube
from video_queue import (
    _ensure_column,
    _google_client,
    _load_cofre,
    _log,
    carregar_config,
)
from youtube_auth import get_access_token


TARGET_DATE = "31/07/2026"
BAD_VIDEO_IDS = {"gdwSXhhENCM", "KB-pSlMwAHY"}
DAILY_COLUMN = "Publicado_Youtube_Diario"


def _video_ids(value: Any) -> Set[str]:
    return set(
        re.findall(
            r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{6,})",
            str(value or ""),
        )
    )


def _delete_video(access_token: str, video_id: str) -> bool:
    response = requests.delete(
        "https://www.googleapis.com/youtube/v3/videos",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"id": video_id},
        timeout=120,
    )
    if response.status_code in {200, 204, 404}:
        _log(f"Vídeo incorreto removido ou já inexistente: {video_id}")
        return True
    try:
        payload = response.json()
    except Exception:
        payload = response.text
    _log(
        f"Não foi possível remover {video_id} nesta conta: "
        f"HTTP {response.status_code} — {json.dumps(payload, ensure_ascii=False)[:500]}"
    )
    return False


def reparar_publicacao_incorreta() -> Dict[str, Any]:
    cfg = carregar_config()
    client = _google_client()
    cofre_cache, cofre_get = _load_cofre(client, cfg)
    spreadsheet = client.open_by_key(cfg.google_sheet_id)
    worksheet = spreadsheet.worksheet(cfg.sheet_tab)
    values = worksheet.get_all_values()
    if not values:
        raise RuntimeError("Planilha principal vazia durante o reparo.")

    headers = list(values[0])
    daily_index = _ensure_column(worksheet, headers, DAILY_COLUMN)
    date_index = next(
        (
            index
            for index, name in enumerate(headers)
            if str(name or "").strip().casefold() == "data"
        ),
        None,
    )
    if date_index is None:
        raise RuntimeError("Coluna Data não encontrada na planilha.")

    rows_to_clear: List[int] = []
    found_bad_ids: Set[str] = set()
    for sheet_row, row in enumerate(values[1:], start=2):
        date = str(row[date_index] if date_index < len(row) else "").strip()
        marker = str(row[daily_index] if daily_index < len(row) else "").strip()
        if date != TARGET_DATE or not marker:
            continue
        ids = _video_ids(marker)
        matched = ids & BAD_VIDEO_IDS
        if matched:
            rows_to_clear.append(sheet_row)
            found_bad_ids.update(matched)

    ids_to_delete = found_bad_ids or set(BAD_VIDEO_IDS)
    accounts = listar_contas_youtube(cofre_cache)
    if not accounts:
        raise RuntimeError("Nenhuma conta YouTube encontrada no Cofre para remover o vídeo incorreto.")

    deletion_attempts = 0
    for account in accounts:
        client_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
        client_secret = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
        refresh_token = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
        if not (client_id and client_secret and refresh_token):
            _log(f"[{account}] Credenciais incompletas no reparo.")
            continue
        access_token = get_access_token(client_id, client_secret, refresh_token)
        for video_id in sorted(ids_to_delete):
            deletion_attempts += 1
            _delete_video(access_token, video_id)

    for row_number in rows_to_clear:
        worksheet.update_cell(row_number, daily_index + 1, "")
    _log(
        f"Reparo de {TARGET_DATE}: marcadores incorretos removidos das linhas {rows_to_clear}."
    )

    return {
        "data": TARGET_DATE,
        "ids": sorted(ids_to_delete),
        "linhas_limpas": rows_to_clear,
        "tentativas_exclusao": deletion_attempts,
    }


def main() -> None:
    result = reparar_publicacao_incorreta()
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
