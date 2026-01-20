import os
import json
import requests

YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_API_URL    = "https://www.googleapis.com/youtube/v3/videos"

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
    privacy_status: str = "unlisted"
) -> str:
    """
    Upload simples (multipart). Retorna o videoId.
    - privacy_status: public | unlisted | private
    """
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
        "status": {
            "privacyStatus": privacy_status
        }
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    params = {
        "part": "snippet,status",
        "uploadType": "multipart",
    }

    with open(video_path, "rb") as f:
        files = {
            "metadata": ("metadata.json", json.dumps(metadata, ensure_ascii=False).encode("utf-8"), "application/json; charset=UTF-8"),
            "media": (os.path.basename(video_path), f, "video/mp4"),
        }

        r = requests.post(YOUTUBE_UPLOAD_URL, headers=headers, params=params, files=files, timeout=1800)
        if not r.ok:
            raise _raise_youtube_error(r)

    j = r.json() or {}
    vid = (j.get("id") or "").strip()
    if not vid:
        raise RuntimeError(f"Upload sem videoId. Resposta: {j}")
    return vid

def build_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"