import json
import os

import requests

YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_THUMBNAIL_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"


def _raise_youtube_error(r: requests.Response):
    try:
        j = r.json()
        if isinstance(j, dict) and "error" in j:
            return RuntimeError(f"YouTube API error: {json.dumps(j, ensure_ascii=False)[:1200]}")
    except Exception:
        pass
    return RuntimeError(f"YouTube HTTP {r.status_code}: {r.text[:1200]}")


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

    tags = tags or []
    privacy_status = (privacy_status or "unlisted").strip().lower()
    if privacy_status not in ("public", "unlisted", "private"):
        privacy_status = "unlisted"

    metadata = {
        "snippet": {
            "title": (title or "")[:95],
            "description": description or "",
            "tags": tags[:30],
            "categoryId": str(category_id or "17"),
        },
        "status": {"privacyStatus": privacy_status},
    }

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"part": "snippet,status", "uploadType": "multipart"}

    with open(video_path, "rb") as f:
        files = {
            "metadata": (
                "metadata.json",
                json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=UTF-8",
            ),
            "media": (os.path.basename(video_path), f, "video/mp4"),
        }
        response = requests.post(
            YOUTUBE_UPLOAD_URL,
            headers=headers,
            params=params,
            files=files,
            timeout=1800,
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


__all__ = ["build_watch_url", "upload_thumbnail", "upload_video"]
