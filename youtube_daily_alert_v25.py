from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

import daily_queue_v19 as queue
from post_video import _cofre_get_safe, _parse_tags, _unique_tags, listar_contas_youtube
from youtube_auth import get_access_token
from youtube_upload import build_watch_url, upload_thumbnail, upload_video

API = "https://www.googleapis.com/youtube/v3"
ALERT_SHEET_DEFAULT = "YOUTUBE_ALERTAS"
ALERT_MARKER = "ALERTA LOTERIAS DO DIA"


def _now(timezone: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(timezone))
    except Exception:
        return datetime.now()


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _signature(targets: Sequence[Tuple[str, str, str]]) -> str:
    raw = "|".join(f"{key}:{contest}" for key, _display, contest in targets)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _metadata(date: str, targets: Sequence[Tuple[str, str, str]]) -> Dict[str, Any]:
    names: List[str] = []
    lines: List[str] = []
    tags: List[str] = [
        "loterias de hoje", "sorteios de hoje", "Loterias Caixa", "resultado loteria hoje",
        "concursos de hoje", "Portal SimonSports", "SimonSports",
    ]
    for _key, display, contest in targets:
        if display not in names:
            names.append(display)
        lines.append(f"• {display} — concurso {contest}")
        tags.extend([display, f"{display} hoje", f"{display} concurso {contest}"])

    joined = ", ".join(names[:4]) + (" e mais" if len(names) > 4 else "")
    title = f"Loterias de Hoje — {joined} | Concursos de {date}"
    if len(title) > 95:
        title = f"Loterias de Hoje — Concursos e Sorteios de {date} | SimonSports"

    description = "\n".join([
        f"Confira as Loterias Caixa programadas para hoje, {date}:",
        "",
        *lines,
        "",
        "Este é o alerta do dia. Assim que todos os resultados oficiais previstos forem confirmados, o SimonSports publica um novo vídeo consolidado com os resultados do dia.",
        "",
        "Acompanhe os resultados: https://www.portalsimonsports.com/search/label/Loterias%20Caixa?m=1",
        "Fonte: CAIXA Loterias. Conteúdo informativo.",
        "",
        "#LoteriasDeHoje #LoteriasCaixa #SimonSports",
        ALERT_MARKER,
    ])
    return {"title": title[:95], "description": description[:4500], "tags": tags}


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, bold: bool = True):
    size = start_size
    while size >= 24:
        font = _font(size, bold=bold)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
        size -= 2
    return _font(24, bold=bold)


def _draw_center(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill: str, width: int) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    x = max(20, (width - (box[2] - box[0])) // 2)
    draw.text((x, y), text, font=font, fill=fill)
    return box[3] - box[1]


def _poster(date: str, targets: Sequence[Tuple[str, str, str]], output_dir: str) -> str:
    width, height = 1920, 1080
    img = Image.new("RGB", (width, height), "#061d33")
    draw = ImageDraw.Draw(img)

    # Faixas simples, legíveis e compatíveis com thumbnail.
    draw.rectangle((0, 0, width, 110), fill="#0a4f83")
    draw.rectangle((0, height - 82, width, height), fill="#03111f")
    draw.text((55, 27), "PORTAL SIMONSPORTS", font=_font(38, True), fill="white")
    draw.text((width - 420, 32), "LOTERIAS CAIXA", font=_font(30, True), fill="#f8c341")

    title = "LOTERIAS DE HOJE"
    title_font = _fit_text(draw, title, width - 160, 88, True)
    _draw_center(draw, title, 150, title_font, "white", width)

    date_font = _font(46, True)
    _draw_center(draw, date, 255, date_font, "#f8c341", width)

    cards = list(targets)[:8]
    cols = 2 if len(cards) > 3 else 1
    rows = (len(cards) + cols - 1) // cols
    card_w = 820 if cols == 2 else 1180
    gap_x = 55
    total_w = cols * card_w + (cols - 1) * gap_x
    start_x = (width - total_w) // 2
    card_h = min(160, max(112, int(520 / max(1, rows))))
    gap_y = 24
    start_y = 360

    for idx, (_key, display, contest) in enumerate(cards):
        col = idx % cols
        row = idx // cols
        x1 = start_x + col * (card_w + gap_x)
        y1 = start_y + row * (card_h + gap_y)
        x2 = x1 + card_w
        y2 = y1 + card_h
        draw.rounded_rectangle((x1, y1, x2, y2), radius=24, fill="#0b385d", outline="#2ea9e8", width=4)
        name_font = _fit_text(draw, display.upper(), card_w - 55, 46, True)
        draw.text((x1 + 28, y1 + 20), display.upper(), font=name_font, fill="white")
        draw.text((x1 + 28, y2 - 58), f"CONCURSO {contest}", font=_font(30, True), fill="#f8c341")

    footer = "RESULTADOS OFICIAIS SERÃO PUBLICADOS ASSIM QUE TODOS FOREM CONFIRMADOS"
    footer_font = _fit_text(draw, footer, width - 120, 30, True)
    _draw_center(draw, footer, height - 66, footer_font, "white", width)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"alerta_loterias_{date.replace('/', '-')}.png")
    img.save(path, quality=95)
    return path


def _video_from_poster(poster_path: str, output_dir: str, date: str) -> str:
    duration = max(8, min(30, int(os.getenv("YOUTUBE_DAILY_ALERT_DURATION", "12") or "12")))
    out = str(Path(output_dir) / f"alerta_loterias_{date.replace('/', '-')}.mp4")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-loop", "1", "-i", poster_path,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(duration),
        "-vf", "scale=1920:1080,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-r", "30",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        out,
    ]
    subprocess.run(cmd, check=True)
    return out


def _ensure_log_sheet(api_spreadsheet):
    name = os.getenv("YOUTUBE_DAILY_ALERT_SHEET", ALERT_SHEET_DEFAULT).strip() or ALERT_SHEET_DEFAULT
    try:
        ws = api_spreadsheet.worksheet(name)
    except Exception:
        ws = api_spreadsheet.add_worksheet(title=name, rows=1000, cols=8)
        ws.append_row(["Data", "Conta", "Assinatura", "URL", "PublicadoEm", "Status"])
    values = ws.get_all_values()
    if not values:
        ws.append_row(["Data", "Conta", "Assinatura", "URL", "PublicadoEm", "Status"])
    return ws


def _already_logged(ws, date: str, account: str, signature: str) -> str:
    values = ws.get_all_values()
    if not values:
        return ""
    headers = [str(x or "").strip().casefold() for x in values[0]]
    def idx(name: str) -> int:
        try:
            return headers.index(name.casefold())
        except ValueError:
            return -1
    i_date, i_account, i_sig, i_url = idx("Data"), idx("Conta"), idx("Assinatura"), idx("URL")
    for row in values[1:]:
        def cell(i: int) -> str:
            return str(row[i] if i >= 0 and i < len(row) else "").strip()
        if cell(i_date) == date and cell(i_account) == account and cell(i_sig) == signature:
            return cell(i_url)
    return ""


def _recent_upload_match(token: str, date: str) -> str:
    try:
        r = requests.get(
            f"{API}/channels",
            headers={"Authorization": f"Bearer {token}"},
            params={"part": "contentDetails", "mine": "true", "maxResults": 1},
            timeout=30,
        )
        if not r.ok:
            return ""
        items = r.json().get("items") or []
        if not items:
            return ""
        uploads = (((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") or "").strip()
        if not uploads:
            return ""
        r = requests.get(
            f"{API}/playlistItems",
            headers={"Authorization": f"Bearer {token}"},
            params={"part": "snippet,contentDetails", "playlistId": uploads, "maxResults": 20},
            timeout=30,
        )
        if not r.ok:
            return ""
        for item in r.json().get("items") or []:
            snippet = item.get("snippet") or {}
            title = str(snippet.get("title") or "")
            if date in title and "Loterias de Hoje" in title:
                video_id = str((item.get("contentDetails") or {}).get("videoId") or "").strip()
                return build_watch_url(video_id) if video_id else "ENCONTRADO"
    except Exception:
        return ""
    return ""


def ensure_daily_alerts(
    date: str,
    targets: Sequence[Tuple[str, str, str]],
    cofre_get,
    cofre_cache: Dict[str, Any],
    api_spreadsheet,
    *,
    dry_run: bool,
    timezone: str,
) -> List[str]:
    if not targets:
        return []

    start_hour = max(0, min(23, int(os.getenv("YOUTUBE_DAILY_ALERT_START_HOUR", "6") or "6")))
    if _now(timezone).hour < start_hour:
        queue._log(f"Alerta diário aguardando {start_hour:02d}:00 no fuso {timezone}.")
        return []

    signature = _signature(targets)
    meta = _metadata(date, targets)
    accounts = listar_contas_youtube(cofre_cache)
    if not accounts:
        queue._log("Nenhuma conta YOUTUBE disponível para o alerta diário.")
        return []

    log_ws = _ensure_log_sheet(api_spreadsheet)
    package_ready = False
    poster_path = ""
    video_path = ""
    urls: List[str] = []

    for account in accounts:
        previous = _already_logged(log_ws, date, account, signature)
        if previous:
            queue._log(f"[{account}] Alerta diário já registrado: {previous}")
            urls.append(previous)
            continue

        client_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
        client_secret = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
        refresh_token = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
        privacy = _cofre_get_safe(cofre_get, "YOUTUBE", "PRIVACY_STATUS", conta=account, default="public") or "public"
        category_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CATEGORY_ID", conta=account, default="24") or "24"
        custom_tags = _parse_tags(_cofre_get_safe(cofre_get, "YOUTUBE", "TAGS", conta=account, default=""))
        if not (client_id and client_secret and refresh_token):
            queue._log(f"[{account}] Credenciais incompletas; alerta ignorado.")
            continue

        if dry_run:
            queue._log(f"[{account}] PREVISÃO: alerta '{meta['title']}'")
            continue

        token = get_access_token(client_id, client_secret, refresh_token)
        youtube_existing = _recent_upload_match(token, date)
        if youtube_existing:
            log_ws.append_row([date, account, signature, youtube_existing, _now(timezone).strftime("%d/%m/%Y %H:%M"), "RECONCILIADO"])
            urls.append(youtube_existing)
            queue._log(f"[{account}] Alerta já existe no YouTube; registro reconciliado.")
            continue

        if not package_ready:
            poster_path = _poster(date, targets, "output")
            video_path = _video_from_poster(poster_path, "output", date)
            package_ready = True

        tags = _unique_tags(custom_tags, meta["tags"])
        video_id = upload_video(
            access_token=token,
            video_path=video_path,
            title=meta["title"],
            description=meta["description"],
            tags=tags,
            category_id=category_id,
            privacy_status=privacy if privacy in {"public", "unlisted", "private"} else "public",
        )
        upload_thumbnail(token, video_id, poster_path)
        url = build_watch_url(video_id)
        log_ws.append_row([date, account, signature, url, _now(timezone).strftime("%d/%m/%Y %H:%M"), "PUBLICADO"])
        urls.append(url)
        queue._log(f"[{account}] Alerta diário publicado: {url}")

    return urls
