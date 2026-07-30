from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

from loteca_preview_v18 import SAMPLE
from post_video import publicar_video_em_multicanais
from video_queue import (
    _empty,
    _ensure_column,
    _google_client,
    _load_cofre,
    _norm,
    _row_to_video_data,
    carregar_config,
)
from youtube_auth import get_access_token


TARGET_LOTTERY = "Loteca"
TARGET_CONTEST = "1263"
THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"


def _find_target_row(worksheet: Any) -> Tuple[Optional[int], Optional[int], str]:
    values = worksheet.get_all_values()
    if not values:
        raise RuntimeError("A aba principal está vazia.")

    headers = list(values[0])
    published_index = _ensure_column(worksheet, headers, "Publicado_Youtube")

    for sheet_row, row in enumerate(values[1:], start=2):
        try:
            data = _row_to_video_data(row, headers)
        except Exception:
            continue
        if _norm(data.get("loteria")) != _norm(TARGET_LOTTERY):
            continue
        if str(data.get("concurso") or "").strip() != TARGET_CONTEST:
            continue
        current = row[published_index] if published_index < len(row) else ""
        return sheet_row, published_index, str(current or "").strip()

    return None, published_index, ""


def _upload_thumbnail(access_token: str, video_id: str, image_path: str) -> None:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Miniatura não encontrada: {path}")

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"videoId": video_id}
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    with path.open("rb") as handle:
        response = requests.post(
            THUMBNAIL_URL,
            headers=headers,
            params=params,
            files={"media": (path.name, handle, mime)},
            timeout=300,
        )
    if not response.ok:
        raise RuntimeError(
            f"YouTube recusou a miniatura do vídeo {video_id}: "
            f"HTTP {response.status_code} — {response.text[:800]}"
        )


def _apply_thumbnails(
    results: list[Dict[str, Any]],
    poster_path: str,
    cofre_get,
) -> None:
    if not poster_path or not Path(poster_path).is_file():
        print("[LOTECA 1263] Pôster não encontrado; publicação mantida sem miniatura personalizada.", flush=True)
        return

    for item in results:
        if item.get("status") != "OK":
            continue
        account = str(item.get("conta") or "").strip()
        client_id = (cofre_get("YOUTUBE", "CLIENT_ID", conta=account, default="") or "").strip()
        client_secret = (cofre_get("YOUTUBE", "CLIENT_SECRET", conta=account, default="") or "").strip()
        refresh_token = (cofre_get("YOUTUBE", "REFRESH_TOKEN", conta=account, default="") or "").strip()
        if not (client_id and client_secret and refresh_token):
            print(f"[LOTECA 1263] Miniatura ignorada em {account}: credenciais incompletas.", flush=True)
            continue

        try:
            access_token = get_access_token(client_id, client_secret, refresh_token)
            for kind in ("full_id", "short_id"):
                video_id = str(item.get(kind) or "").strip()
                if not video_id:
                    continue
                try:
                    _upload_thumbnail(access_token, video_id, poster_path)
                    print(f"[LOTECA 1263] Miniatura aplicada: {account} / {kind} / {video_id}", flush=True)
                except Exception as error:
                    # A miniatura não pode transformar um upload válido em falha de publicação.
                    print(f"[LOTECA 1263] Aviso ao aplicar miniatura em {video_id}: {error}", flush=True)
        except Exception as error:
            print(f"[LOTECA 1263] Aviso ao autenticar miniatura em {account}: {error}", flush=True)


def main() -> None:
    config = carregar_config()
    if config.dry_run:
        raise RuntimeError("DRY_RUN_VIDEOS está ativo. A publicação real foi interrompida.")

    client = _google_client()
    cofre_cache, cofre_get = _load_cofre(client, config)
    worksheet = client.open_by_key(config.google_sheet_id).worksheet(config.sheet_tab)

    sheet_row, published_index, current_status = _find_target_row(worksheet)
    if sheet_row is None or published_index is None:
        raise RuntimeError("A Loteca 1263 não foi localizada na aba principal.")
    if not _empty(current_status):
        print(
            f"[LOTECA 1263] Publicação já registrada na linha {sheet_row}: {current_status}. "
            "Nenhum novo upload foi realizado.",
            flush=True,
        )
        return

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    data: Dict[str, Any] = dict(SAMPLE)
    data["previa"] = False
    data["output_dir"] = str(output_dir)
    data["title_completo"] = "Resultado Loteca 1263 — 14 Jogos, Placares e Colunas | SimonSports"
    data["title_short"] = "Loteca 1263 — 14 Jogos, Placares e Colunas #Shorts"

    print("[LOTECA 1263] Iniciando geração e publicação real do vídeo completo e do Short.", flush=True)
    result = publicar_video_em_multicanais(
        data,
        cofre_get,
        cofre_cache,
        dry_run=False,
        sleep_between_channels=max(0.5, min(config.pausa, 15.0)),
        tz_name=config.timezone,
    )

    if not result.get("ok_any"):
        raise RuntimeError(str(result.get("mark_value") or "Nenhum upload foi concluído."))

    package = result.get("video_paths") or {}
    _apply_thumbnails(result.get("results") or [], str(package.get("poster") or ""), cofre_get)

    mark_value = str(result.get("mark_value") or "Publicado YOUTUBE — Loteca 1263")
    worksheet.update_cell(sheet_row, published_index + 1, mark_value)

    print(f"[LOTECA 1263] Publicação confirmada e registrada na linha {sheet_row}.", flush=True)
    for item in result.get("results") or []:
        if item.get("status") == "OK":
            print(
                f"[LOTECA 1263] Canal={item.get('conta')} | "
                f"Completo={item.get('full_url')} | Short={item.get('short_url')}",
                flush=True,
            )


if __name__ == "__main__":
    main()
