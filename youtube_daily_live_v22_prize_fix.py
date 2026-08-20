from __future__ import annotations

"""Patch V22 LIVE: aplica a capa aprovada apenas UMA VEZ na criação da Live.

A versão anterior reaplicava a thumbnail a cada execução horária do workflow,
provocando uploadRateLimitExceeded (HTTP 429) no YouTube. Agora verificamos se
a Live já existia antes de criá-la; capa só é enviada para transmissões novas.
"""

from typing import Any, Dict, Sequence, Tuple

import youtube_daily_live_v22 as live
from post_video import _cofre_get_safe, listar_contas_youtube
from youtube_auth import get_access_token
from youtube_upload import upload_thumbnail
from youtube_thumbnail_v24 import gerar_capa_live

_ORIGINAL_ENSURE = live.ensure_daily_lives
_ORIGINAL_PUBLISH = live.publish_day_as_live


def _account_credentials(cofre_get, account: str):
    client_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
    client_secret = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
    refresh_token = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
    privacy = _cofre_get_safe(cofre_get, "YOUTUBE", "PRIVACY_STATUS", conta=account, default="public") or "public"
    return client_id, client_secret, refresh_token, privacy


def ensure_daily_lives(
    date: str,
    targets: Sequence[Tuple[str, str, str]],
    cofre_get,
    cofre_cache: Dict[str, Any],
    *,
    timezone: str,
    prize_highlight: Dict[str, str] | None = None,
):
    # Registra quais contas JÁ tinham Live antes desta execução.
    existing_before = set()
    tokens: Dict[str, str] = {}
    privacy_map: Dict[str, str] = {}

    for account in listar_contas_youtube(cofre_cache):
        client_id, client_secret, refresh_token, privacy = _account_credentials(cofre_get, account)
        if not (client_id and client_secret and refresh_token):
            continue
        try:
            token = get_access_token(client_id, client_secret, refresh_token)
            tokens[account] = token
            privacy_map[account] = privacy
            if live._find_daily_broadcast(token, date):
                existing_before.add(account)
        except Exception as exc:
            live.queue._log(f"[{account}] Não foi possível verificar Live existente: {exc}")

    urls = _ORIGINAL_ENSURE(date, targets, cofre_get, cofre_cache, timezone=timezone)

    # Só envia thumbnail para a Live que nasceu NESTA execução.
    thumb = None
    for account, token in tokens.items():
        if account in existing_before:
            live.queue._log(f"[{account}] Live já existia; thumbnail não será reenviada.")
            continue
        try:
            broadcast = live._find_daily_broadcast(token, date)
            if not broadcast:
                continue
            video_id = str(broadcast.get("id") or "").strip()
            if not video_id:
                continue
            if thumb is None:
                thumb = gerar_capa_live(date, targets, prize_highlight=prize_highlight or {})
            upload_thumbnail(token, video_id, thumb)
            live.queue._log(f"[{account}] Capa aplicada uma única vez na nova Live: {video_id}")
        except Exception as exc:
            live.queue._log(f"[{account}] Capa da nova Live não aplicada: {exc}")

    return urls


def publish_day_as_live(
    date,
    targets,
    rows,
    worksheet,
    daily_index,
    cofre_get,
    cofre_cache: Dict[str, Any],
    *,
    dry_run,
    pause,
    timezone,
    prize_highlight=None,
):
    # O método original já aplica a capa final uma única vez após concluir a Live.
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
