from __future__ import annotations

"""Patch V22 LIVE: aplica a capa padrão aprovada na Live do dia.

A capa é criada com as modalidades, concursos e o maior prêmio estimado do dia.
Também preserva compatibilidade com o método original de publicação/replay.
"""

from typing import Any, Dict, Sequence, Tuple

import youtube_daily_live_v22 as live
from post_video import _cofre_get_safe, listar_contas_youtube
from youtube_auth import get_access_token
from youtube_upload import upload_thumbnail
from youtube_thumbnail_v24 import gerar_capa_live

_ORIGINAL_ENSURE = live.ensure_daily_lives
_ORIGINAL_PUBLISH = live.publish_day_as_live


def _apply_live_thumbnail(date, targets, cofre_get, cofre_cache, timezone, prize_highlight=None):
    thumb = gerar_capa_live(date, targets, prize_highlight=prize_highlight or {})
    updated = 0
    for account in listar_contas_youtube(cofre_cache):
        client_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
        client_secret = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
        refresh_token = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
        privacy = _cofre_get_safe(cofre_get, "YOUTUBE", "PRIVACY_STATUS", conta=account, default="public") or "public"
        if not (client_id and client_secret and refresh_token):
            continue
        try:
            token = get_access_token(client_id, client_secret, refresh_token)
            broadcast = live.ensure_daily_live_for_account(token, date, targets, timezone, privacy)
            video_id = str(broadcast.get("id") or "").strip()
            if not video_id:
                continue
            upload_thumbnail(token, video_id, thumb)
            updated += 1
            live.queue._log(f"[{account}] Capa da Live aplicada: {video_id}")
        except Exception as exc:
            live.queue._log(f"[{account}] Falha ao aplicar capa da Live: {exc}")
    return updated


def ensure_daily_lives(
    date: str,
    targets: Sequence[Tuple[str, str, str]],
    cofre_get,
    cofre_cache: Dict[str, Any],
    *,
    timezone: str,
    prize_highlight: Dict[str, str] | None = None,
):
    urls = _ORIGINAL_ENSURE(date, targets, cofre_get, cofre_cache, timezone=timezone)
    try:
        _apply_live_thumbnail(date, targets, cofre_get, cofre_cache, timezone, prize_highlight)
    except Exception as exc:
        live.queue._log(f"Capa da Live não aplicada nesta execução: {exc}")
    return urls


def publish_day_as_live(
    date,
    targets,
    rows,
    worksheet,
    daily_index,
    cofre_get,
    cofre_cache,
    *,
    dry_run,
    pause,
    timezone,
    prize_highlight=None,
):
    return _ORIGINAL_PUBLISH(
        date,
        targets,
        rows,
        worksheet,
        daily_index,
        cofre_get,
        cofre_cache,
        dry_run=dry_run,
        pause=pause,
        timezone=timezone,
    )


live.ensure_daily_lives = ensure_daily_lives
live.publish_day_as_live = publish_day_as_live
