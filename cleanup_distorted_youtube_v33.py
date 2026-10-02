from __future__ import annotations

import sys
from datetime import datetime, timezone

import requests

import daily_queue_v19 as queue
from post_video import _cofre_get_safe, listar_contas_youtube
from youtube_auth import get_access_token

API = "https://www.googleapis.com/youtube/v3"
EXACT_BAD_IDS = {"4kDM0g53Uv0"}
BAD_CONTEST_TOKENS = {"2448"}
PUBLISHED_AFTER = "2026-09-28T00:00:00Z"


def _request(method: str, url: str, *, token: str, params=None):
    r = requests.request(
        method,
        url,
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=120,
    )
    if not r.ok:
        raise RuntimeError(f"YouTube HTTP {r.status_code}: {r.text[:1200]}")
    if r.status_code == 204 or not r.text.strip():
        return {}
    return r.json() or {}


def _recent_owned_videos(token: str):
    payload = _request(
        "GET",
        f"{API}/search",
        token=token,
        params={
            "part": "snippet",
            "forMine": "true",
            "type": "video",
            "order": "date",
            "maxResults": 50,
            "publishedAfter": PUBLISHED_AFTER,
        },
    )
    return list(payload.get("items") or [])


def _candidate_ids(token: str):
    ids = set(EXACT_BAD_IDS)
    for item in _recent_owned_videos(token):
        vid = str((item.get("id") or {}).get("videoId") or "").strip()
        snippet = item.get("snippet") or {}
        title = str(snippet.get("title") or "")
        desc = str(snippet.get("description") or "")
        hay = f"{title}\n{desc}"
        if vid and any(token_ in hay for token_ in BAD_CONTEST_TOKENS):
            ids.add(vid)
            print(f"[LIMPEZA] Marcado por concurso distorcido: {vid} | {title}", flush=True)
    return ids


def _video_exists(token: str, video_id: str) -> bool:
    payload = _request(
        "GET",
        f"{API}/videos",
        token=token,
        params={"part": "id,snippet,status", "id": video_id},
    )
    return bool(payload.get("items"))


def _delete_video(token: str, video_id: str):
    r = requests.delete(
        f"{API}/videos",
        headers={"Authorization": f"Bearer {token}"},
        params={"id": video_id},
        timeout=120,
    )
    if r.status_code == 404:
        print(f"[LIMPEZA] Já não existe: {video_id}", flush=True)
        return False
    if not r.ok:
        raise RuntimeError(f"Falha ao excluir {video_id}: HTTP {r.status_code}: {r.text[:1200]}")
    print(f"[LIMPEZA] EXCLUÍDO: {video_id}", flush=True)
    return True


def main() -> int:
    cfg = queue.carregar_config()
    client = queue._google_client()
    cofre_cache, cofre_get = queue._load_cofre(client, cfg)
    accounts = listar_contas_youtube(cofre_cache)
    if not accounts:
        raise RuntimeError("Nenhuma conta YOUTUBE encontrada no Cofre.")

    deleted = 0
    for account in accounts:
        cid = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
        sec = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
        ref = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
        if not (cid and sec and ref):
            print(f"[LIMPEZA] Conta sem credenciais completas: {account}", flush=True)
            continue
        token = get_access_token(cid, sec, ref)
        print(f"[LIMPEZA] Conta: {account}", flush=True)
        for video_id in sorted(_candidate_ids(token)):
            if _video_exists(token, video_id):
                deleted += int(_delete_video(token, video_id))
            else:
                print(f"[LIMPEZA] Não encontrado nesta conta: {video_id}", flush=True)

    print(f"[LIMPEZA] Total excluído: {deleted}", flush=True)
    return deleted


if __name__ == "__main__":
    main()
