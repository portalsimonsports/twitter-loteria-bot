# -*- coding: utf-8 -*-
from pathlib import Path

import bot
from post_video import listar_contas_youtube
from spiritual_publish import (
    JOBS,
    _service_drive_token,
    add_to_playlist,
    download_drive,
    ensure_playlist,
    render_thumbnail,
    render_video,
)
from youtube_auth import get_access_token
from youtube_upload import build_watch_url, upload_thumbnail, upload_video


def main():
    bot._cofre_load()
    accounts = listar_contas_youtube(bot._cofre_cache)
    preferred = [a for a in accounts if "SIMON" in a.upper() or "PORTAL" in a.upper()]
    account = preferred[0] if len(preferred) == 1 else accounts[0]
    print(f"[HOOPONOPONO] Conta YouTube: {account}", flush=True)

    client_id = bot._cofre_get("YOUTUBE", "CLIENT_ID", conta=account, default="") or ""
    client_secret = bot._cofre_get("YOUTUBE", "CLIENT_SECRET", conta=account, default="") or ""
    refresh_token = bot._cofre_get("YOUTUBE", "REFRESH_TOKEN", conta=account, default="") or ""
    privacy = bot._cofre_get("YOUTUBE", "PRIVACY_STATUS", conta=account, default="public") or "public"
    category_id = bot._cofre_get("YOUTUBE", "CATEGORY_ID", conta=account, default="22") or "22"

    access_token = get_access_token(client_id, client_secret, refresh_token)
    drive_token = _service_drive_token()
    job = next(j for j in JOBS if j["slug"] == "hooponopono")

    work = Path("spiritual_work")
    work.mkdir(exist_ok=True)
    audio = work / "hooponopono.mp3"
    cover = work / "hooponopono.png"
    thumb = work / "hooponopono_thumb.jpg"
    video = work / "hooponopono.mp4"

    download_drive(job["audio_drive_id"], audio, drive_token)
    download_drive(job["cover_drive_id"], cover, drive_token)
    render_thumbnail(cover, thumb)
    render_video(cover, audio, video)

    video_id = upload_video(
        access_token=access_token,
        video_path=str(video),
        title=job["title"],
        description=job["description"],
        tags=job["tags"],
        category_id=category_id,
        privacy_status=privacy,
    )
    url = build_watch_url(video_id)
    print(f"[HOOPONOPONO] UPLOAD OK: {url}", flush=True)

    upload_thumbnail(access_token, video_id, str(thumb))
    print(f"[HOOPONOPONO] THUMBNAIL OK: {url}", flush=True)

    try:
        playlist_id = ensure_playlist(access_token, job["playlist"], job["playlist_description"])
        add_to_playlist(access_token, playlist_id, video_id)
        print(f"[HOOPONOPONO] PLAYLIST OK: {job['playlist']}", flush=True)
    except Exception as exc:
        print(f"[HOOPONOPONO] PLAYLIST NÃO APLICADA: {type(exc).__name__}: {exc}", flush=True)
        print("[HOOPONOPONO] O vídeo permanece publicado; a credencial atual é suficiente para upload, mas não para gerenciar playlists.", flush=True)

    print(f"[HOOPONOPONO] PUBLICADO: {url}", flush=True)


if __name__ == "__main__":
    main()
