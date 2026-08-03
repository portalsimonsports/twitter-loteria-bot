import json
import os
import re
from typing import Iterable, List

import requests

YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_THUMBNAIL_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"

# O YouTube limita o conjunto de tags a 500 caracteres. Tags com espaços
# contam como se estivessem entre aspas, portanto consomem dois caracteres
# adicionais. Mantemos margem de segurança para evitar invalidTags.
YOUTUBE_TAGS_SAFE_LIMIT = 440
YOUTUBE_TAGS_MAX_ITEMS = 25


def _raise_youtube_error(r: requests.Response):
    try:
        j = r.json()
        if isinstance(j, dict) and "error" in j:
            return RuntimeError(f"YouTube API error: {json.dumps(j, ensure_ascii=False)[:1200]}")
    except Exception:
        pass
    return RuntimeError(f"YouTube HTTP {r.status_code}: {r.text[:1200]}")


def _youtube_tag_cost(tag: str, *, has_previous: bool) -> int:
    # A documentação do YouTube considera aspas extras para tags com espaços.
    quoted_extra = 2 if any(ch.isspace() for ch in tag) else 0
    separator = 1 if has_previous else 0
    return len(tag) + quoted_extra + separator


def sanitize_youtube_tags(
    tags: Iterable[object] | None,
    *,
    max_chars: int = YOUTUBE_TAGS_SAFE_LIMIT,
    max_items: int = YOUTUBE_TAGS_MAX_ITEMS,
) -> List[str]:
    """Limpa, deduplica e limita tags conforme as regras do YouTube."""
    output: List[str] = []
    seen = set()
    used_chars = 0

    for raw in tags or []:
        clean = re.sub(r"[\x00-\x1f\x7f]+", " ", str(raw or ""))
        clean = clean.replace('"', "").replace("<", " ").replace(">", " ")
        clean = " ".join(clean.split()).strip(" ,")
        if not clean:
            continue

        # Evita uma única tag excessivamente longa.
        clean = clean[:80].rstrip()
        key = clean.casefold()
        if not clean or key in seen:
            continue

        cost = _youtube_tag_cost(clean, has_previous=bool(output))
        if len(output) >= max_items or used_chars + cost > max_chars:
            continue

        output.append(clean)
        seen.add(key)
        used_chars += cost

    return output


def _is_invalid_tags_response(response: requests.Response) -> bool:
    try:
        payload = response.json() or {}
    except Exception:
        return False

    error = payload.get("error") if isinstance(payload, dict) else None
    errors = error.get("errors", []) if isinstance(error, dict) else []
    for item in errors:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "").strip().lower()
        location = str(item.get("location") or "").strip().lower()
        if reason == "invalidtags" or location == "body.snippet.tags":
            return True
    return False


def _post_video_upload(
    *,
    access_token: str,
    video_path: str,
    metadata: dict,
) -> requests.Response:
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"part": "snippet,status", "uploadType": "multipart"}

    with open(video_path, "rb") as video_file:
        files = {
            "metadata": (
                "metadata.json",
                json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=UTF-8",
            ),
            "media": (os.path.basename(video_path), video_file, "video/mp4"),
        }
        return requests.post(
            YOUTUBE_UPLOAD_URL,
            headers=headers,
            params=params,
            files=files,
            timeout=1800,
        )


def upload_video(
    access_token: str,
    video_path: str,
    title: str,
    description: str,
    tags=None,
    category_id: str = "17",
    privacy_status: str = "unlisted",
) -> str:
    """Envia um vídeo e retorna o videoId."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {video_path}")

    safe_tags = sanitize_youtube_tags(tags)
    privacy_status = (privacy_status or "unlisted").strip().lower()
    if privacy_status not in ("public", "unlisted", "private"):
        privacy_status = "unlisted"

    metadata = {
        "snippet": {
            "title": (title or "")[:95],
            "description": (description or "")[:5000],
            "categoryId": str(category_id or "17"),
        },
        "status": {"privacyStatus": privacy_status},
    }
    if safe_tags:
        metadata["snippet"]["tags"] = safe_tags

    response = _post_video_upload(
        access_token=access_token,
        video_path=video_path,
        metadata=metadata,
    )

    # Proteção adicional: caso o YouTube ainda rejeite tags por alguma regra
    # não documentada, refaz o envio sem tags em vez de perder a publicação.
    if not response.ok and safe_tags and _is_invalid_tags_response(response):
        retry_metadata = {
            "snippet": {
                "title": metadata["snippet"]["title"],
                "description": metadata["snippet"]["description"],
                "categoryId": metadata["snippet"]["categoryId"],
            },
            "status": metadata["status"],
        }
        response = _post_video_upload(
            access_token=access_token,
            video_path=video_path,
            metadata=retry_metadata,
        )

    if not response.ok:
        raise _raise_youtube_error(response)

    payload = response.json() or {}
    video_id = (payload.get("id") or "").strip()
    if not video_id:
        raise RuntimeError(f"Upload sem videoId. Resposta: {payload}")
    return video_id


def upload_thumbnail(access_token: str, video_id: str, image_path: str) -> bool:
    """Aplica uma miniatura personalizada ao vídeo enviado."""
    if not video_id:
        raise ValueError("video_id não informado para a miniatura.")
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Miniatura não encontrada: {image_path}")

    extension = os.path.splitext(image_path)[1].lower()
    mime_type = "image/png" if extension == ".png" else "image/jpeg"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"videoId": video_id, "uploadType": "media"}

    with open(image_path, "rb") as image_file:
        response = requests.post(
            YOUTUBE_THUMBNAIL_UPLOAD_URL,
            headers={**headers, "Content-Type": mime_type},
            params=params,
            data=image_file,
            timeout=300,
        )

    if not response.ok:
        raise _raise_youtube_error(response)
    return True


def build_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


__all__ = [
    "build_watch_url",
    "sanitize_youtube_tags",
    "upload_thumbnail",
    "upload_video",
]
