# -*- coding: utf-8 -*-
"""Publicador dedicado de vídeos espirituais via GitHub Actions.

Fluxo isolado das loterias: baixa áudio/capa do Google Drive compartilhado com
service account, gera MP4 16:9 com FFmpeg, publica no YouTube, aplica thumbnail
e organiza em playlist.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import requests
from oauth2client.service_account import ServiceAccountCredentials

import bot
from post_video import listar_contas_youtube
from youtube_auth import get_access_token
from youtube_upload import build_watch_url, upload_thumbnail, upload_video

DRIVE_API = "https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
YOUTUBE_PLAYLISTS = "https://www.googleapis.com/youtube/v3/playlists"
YOUTUBE_PLAYLIST_ITEMS = "https://www.googleapis.com/youtube/v3/playlistItems"

JOBS = [
    {
        "slug": "ganesha",
        "audio_drive_id": "1nnRBLTnnDznskeClxq-cGYF9rP9Bk85W",
        "cover_drive_id": "1CpUCEOzNCB1rAfV_v_E9mDPjiq1wyPGF",
        "title": "Poderoso Mantra de Ganesha para Prosperidade e Remover Obstáculos",
        "description": (
            "Mantra de Ganesha para um momento de concentração, prosperidade e superação de obstáculos.\n\n"
            "Use este vídeo para meditação, reflexão e prática espiritual.\n\n"
            "Inscreva-se no canal e acompanhe novos conteúdos de espiritualidade, orações e mantras.\n\n"
            "#Ganesha #MantraDeGanesha #Prosperidade #Mantra #Espiritualidade"
        ),
        "tags": [
            "mantra de Ganesha", "Ganesha", "prosperidade", "remover obstáculos",
            "abertura de caminhos", "mantra prosperidade", "espiritualidade", "meditação"
        ],
        "playlist": "Mantras para Prosperidade e Proteção",
        "playlist_description": "Mantras e práticas espirituais voltados à prosperidade, proteção, equilíbrio e abertura de caminhos.",
    },
    {
        "slug": "hooponopono",
        "audio_drive_id": "1h-ouGyylnq-6mje_NlZVfuk187rpumbC",
        "cover_drive_id": "10oDET7VtyKL7eD50IZK6SYv01KIn_K4T",
        "title": "Ho'oponopono Mágico — 108 Repetições | Atraindo Dinheiro e Prosperidade",
        "description": (
            "Ho'oponopono em 108 repetições para um momento de concentração, limpeza emocional, abundância e prosperidade.\n\n"
            "Ouça em um ambiente tranquilo e utilize o conteúdo como prática de meditação e reflexão.\n\n"
            "Inscreva-se no canal e acompanhe novos conteúdos de espiritualidade, orações e meditação.\n\n"
            "#Hooponopono #108Repetições #Prosperidade #Abundância #Meditação"
        ),
        "tags": [
            "ho'oponopono", "hooponopono 108 repetições", "prosperidade", "abundância",
            "atraindo dinheiro", "meditação", "limpeza emocional", "espiritualidade"
        ],
        "playlist": "Ho'oponopono, Cura e Prosperidade",
        "playlist_description": "Práticas de Ho'oponopono, meditação, limpeza emocional, abundância e prosperidade.",
    },
]


def _service_drive_token() -> str:
    raw = (os.getenv("GOOGLE_SERVICE_JSON") or "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_JSON ausente")
    info = json.loads(raw)
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scopes)
    return creds.get_access_token().access_token


def download_drive(file_id: str, out: Path, token: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(
        DRIVE_API.format(file_id=file_id),
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=600,
    ) as response:
        response.raise_for_status()
        with out.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    print(f"[SPIRITUAL] Drive OK: {out.name} ({out.stat().st_size} bytes)", flush=True)


def render_video(image_path: Path, audio_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", "2", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "27",
        "-r", "2", "-g", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    print(f"[SPIRITUAL] Vídeo gerado: {output_path} ({output_path.stat().st_size} bytes)", flush=True)


def render_thumbnail(image_path: Path, thumb_path: Path) -> None:
    command = [
        "ffmpeg", "-y", "-i", str(image_path),
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-q:v", "3", str(thumb_path),
    ]
    subprocess.run(command, check=True)
    if thumb_path.stat().st_size > 2_000_000:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(image_path),
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "-q:v", "6", str(thumb_path),
        ], check=True)


def youtube_account() -> str:
    accounts = listar_contas_youtube(bot._cofre_cache)
    if not accounts:
        raise RuntimeError("Nenhuma conta YOUTUBE com REFRESH_TOKEN no Cofre")
    wanted = (os.getenv("YOUTUBE_SPIRITUAL_ACCOUNT") or "").strip()
    if wanted:
        for account in accounts:
            if account.casefold() == wanted.casefold():
                return account
        raise RuntimeError(f"YOUTUBE_SPIRITUAL_ACCOUNT não encontrada: {wanted}. Contas: {accounts}")
    if len(accounts) > 1:
        preferred = [a for a in accounts if "SIMON" in a.upper() or "PORTAL" in a.upper()]
        if len(preferred) == 1:
            return preferred[0]
        raise RuntimeError(
            "Há mais de uma conta YOUTUBE no Cofre. Defina a variável YOUTUBE_SPIRITUAL_ACCOUNT. "
            f"Contas encontradas: {accounts}"
        )
    return accounts[0]


def ensure_playlist(access_token: str, title: str, description: str) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}
    page_token = ""
    while True:
        params = {"part": "snippet", "mine": "true", "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        response = requests.get(YOUTUBE_PLAYLISTS, headers=headers, params=params, timeout=120)
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("items", []):
            if (item.get("snippet", {}).get("title") or "").strip().casefold() == title.casefold():
                return item["id"]
        page_token = payload.get("nextPageToken") or ""
        if not page_token:
            break

    response = requests.post(
        YOUTUBE_PLAYLISTS,
        headers={**headers, "Content-Type": "application/json"},
        params={"part": "snippet,status"},
        json={
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": "public"},
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["id"]


def add_to_playlist(access_token: str, playlist_id: str, video_id: str) -> None:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    response = requests.post(
        YOUTUBE_PLAYLIST_ITEMS,
        headers=headers,
        params={"part": "snippet"},
        json={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        },
        timeout=120,
    )
    response.raise_for_status()


def already_published(access_token: str, title: str) -> bool:
    # Busca nos uploads recentes do canal para evitar duplicidade em reexecução.
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        headers=headers,
        params={"part": "snippet", "forMine": "true", "type": "video", "maxResults": 50, "q": title[:45]},
        timeout=120,
    )
    response.raise_for_status()
    for item in response.json().get("items", []):
        found = (item.get("snippet", {}).get("title") or "").strip().casefold()
        if found == title.strip().casefold():
            return True
    return False


def main() -> None:
    bot._cofre_load()
    account = youtube_account()
    print(f"[SPIRITUAL] Conta YouTube: {account}", flush=True)

    client_id = bot._cofre_get("YOUTUBE", "CLIENT_ID", conta=account, default="") or ""
    client_secret = bot._cofre_get("YOUTUBE", "CLIENT_SECRET", conta=account, default="") or ""
    refresh_token = bot._cofre_get("YOUTUBE", "REFRESH_TOKEN", conta=account, default="") or ""
    if not (client_id and client_secret and refresh_token):
        raise RuntimeError(f"Credenciais YOUTUBE incompletas para {account}")

    privacy = bot._cofre_get("YOUTUBE", "PRIVACY_STATUS", conta=account, default="public") or "public"
    category_id = bot._cofre_get("YOUTUBE", "CATEGORY_ID", conta=account, default="22") or "22"
    access_token = get_access_token(client_id, client_secret, refresh_token)
    drive_token = _service_drive_token()

    work = Path("spiritual_work")
    work.mkdir(exist_ok=True)

    for job in JOBS:
        title = job["title"]
        if already_published(access_token, title):
            print(f"[SPIRITUAL] Já publicado, pulando: {title}", flush=True)
            continue

        slug = job["slug"]
        audio = work / f"{slug}.mp3"
        cover = work / f"{slug}.png"
        thumb = work / f"{slug}_thumb.jpg"
        video = work / f"{slug}.mp4"

        download_drive(job["audio_drive_id"], audio, drive_token)
        download_drive(job["cover_drive_id"], cover, drive_token)
        render_thumbnail(cover, thumb)
        render_video(cover, audio, video)

        video_id = upload_video(
            access_token=access_token,
            video_path=str(video),
            title=title,
            description=job["description"],
            tags=job["tags"],
            category_id=category_id,
            privacy_status=privacy,
        )
        upload_thumbnail(access_token, video_id, str(thumb))
        playlist_id = ensure_playlist(access_token, job["playlist"], job["playlist_description"])
        add_to_playlist(access_token, playlist_id, video_id)
        print(f"[SPIRITUAL] PUBLICADO: {build_watch_url(video_id)} | playlist={job['playlist']}", flush=True)


if __name__ == "__main__":
    main()
