from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image, ImageDraw, ImageFont

import daily_queue_v19 as queue
from youtube_auth import get_access_token
from youtube_upload import upload_thumbnail

WIDTH = 1280
HEIGHT = 720
OUT_DIR = Path("output")


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _extract_video_id(text: str) -> str:
    match = re.search(r"youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})", str(text or ""))
    return match.group(1) if match else ""


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, min_size: int = 24, bold: bool = True):
    size = start_size
    while size >= min_size:
        font = _font(size, bold=bold)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
        size -= 2
    return _font(min_size, bold=bold)


def gerar_capa_diaria(data: str, loterias: List[Dict[str, str]], *, video_id: str = "") -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (WIDTH, HEIGHT), (8, 24, 43))
    draw = ImageDraw.Draw(img)

    # faixa superior e rodape para diferenciar claramente a thumbnail do frame do video
    draw.rectangle((0, 0, WIDTH, 92), fill=(0, 118, 190))
    draw.rectangle((0, 640, WIDTH, HEIGHT), fill=(0, 49, 78))

    draw.text((48, 25), "PORTAL SIMONSPORTS", font=_font(34, True), fill=(255, 255, 255))
    draw.text((48, 122), "RESULTADOS DAS LOTERIAS", font=_font(58, True), fill=(255, 255, 255))
    draw.text((48, 190), "DE HOJE", font=_font(66, True), fill=(255, 204, 0))

    # data em selo
    draw.rounded_rectangle((940, 112, 1225, 192), radius=20, fill=(255, 204, 0))
    date_font = _fit_text(draw, data, 245, 32, 24, True)
    bbox = draw.textbbox((0, 0), data, font=date_font)
    tx = 1082 - (bbox[2] - bbox[0]) / 2
    draw.text((tx, 133), data, font=date_font, fill=(10, 24, 40))

    # cards das modalidades/concurso
    y = 292
    card_w = 370
    card_h = 112
    gap = 22
    x0 = 48
    for idx, item in enumerate(loterias[:6]):
        col = idx % 3
        row = idx // 3
        x = x0 + col * (card_w + gap)
        yy = y + row * (card_h + 22)
        draw.rounded_rectangle((x, yy, x + card_w, yy + card_h), radius=18, fill=(13, 61, 96), outline=(56, 165, 220), width=3)
        nome = str(item.get("loteria") or "Loteria").strip()
        concurso = str(item.get("concurso") or "").strip()
        f1 = _fit_text(draw, nome.upper(), card_w - 30, 30, 22, True)
        draw.text((x + 18, yy + 16), nome.upper(), font=f1, fill=(255, 255, 255))
        if concurso:
            draw.text((x + 18, yy + 61), f"CONCURSO {concurso}", font=_font(25, True), fill=(255, 204, 0))

    draw.text((48, 658), "RESULTADOS OFICIAIS • CAIXA LOTERIAS", font=_font(28, True), fill=(255, 255, 255))
    draw.text((885, 658), "SIMONSPORTS", font=_font(30, True), fill=(255, 204, 0))

    name = f"thumbnail_diaria_{data.replace('/', '-')}_{video_id or 'novo'}.jpg"
    path = OUT_DIR / name
    img.save(path, "JPEG", quality=92, optimize=True)
    return str(path)


def reparar_ultima_capa_publicada() -> int:
    cfg = queue.carregar_config()
    client = queue._google_client()
    cofre_cache, cofre_get = queue._load_cofre(client, cfg)
    ws = client.open_by_key(cfg.google_sheet_id).worksheet(cfg.sheet_tab)
    values = ws.get_all_values()
    if not values:
        return 0

    headers = list(values[0])
    daily_idx = queue._find_col(headers, [os.getenv("PUBLICADO_YT_DIARIO_COL", queue.DAILY_COLUMN_DEFAULT)])
    if daily_idx is None:
        print("[THUMB V24] Coluna de publicação diária não encontrada.", flush=True)
        return 0

    # localiza de baixo para cima a publicação diária mais recente
    target_marker = ""
    video_id = ""
    for row in reversed(values[1:]):
        marker = row[daily_idx] if daily_idx < len(row) else ""
        vid = _extract_video_id(marker)
        if vid:
            target_marker = marker
            video_id = vid
            break
    if not video_id:
        print("[THUMB V24] Nenhum videoId diário encontrado.", flush=True)
        return 0

    # coleta todas as linhas que pertencem ao mesmo resumo publicado
    loterias: List[Dict[str, str]] = []
    data = ""
    seen = set()
    for row in values[1:]:
        marker = row[daily_idx] if daily_idx < len(row) else ""
        if _extract_video_id(marker) != video_id:
            continue
        try:
            item = queue._row_data(row, headers)
        except Exception:
            continue
        nome = str(item.get("loteria") or "").strip()
        concurso = str(item.get("concurso") or "").strip()
        if not nome:
            continue
        key = (nome.casefold(), concurso)
        if key in seen:
            continue
        seen.add(key)
        loterias.append({"loteria": nome, "concurso": concurso})
        data = data or str(item.get("data") or "").strip()

    if not loterias:
        print(f"[THUMB V24] Video {video_id} encontrado, mas sem linhas associadas.", flush=True)
        return 0

    thumb = gerar_capa_diaria(data or "", loterias, video_id=video_id)

    accounts = []
    for network, account, key in (cofre_cache.get("creds_rc", {}) or {}).keys():
        if str(network).strip().upper() == "YOUTUBE" and str(key).strip().upper() == "REFRESH_TOKEN" and account:
            accounts.append(str(account).strip())
    accounts = sorted(set(accounts))

    updated = 0
    for account in accounts:
        client_id = cofre_get("YOUTUBE", "CLIENT_ID", conta=account, default="")
        client_secret = cofre_get("YOUTUBE", "CLIENT_SECRET", conta=account, default="")
        refresh_token = cofre_get("YOUTUBE", "REFRESH_TOKEN", conta=account, default="")
        if not (client_id and client_secret and refresh_token):
            continue
        try:
            access_token = get_access_token(client_id, client_secret, refresh_token)
            upload_thumbnail(access_token, video_id, thumb)
            updated += 1
            print(f"[THUMB V24] Capa aplicada em https://www.youtube.com/watch?v={video_id} ({account})", flush=True)
        except Exception as exc:
            print(f"[THUMB V24] Erro ao aplicar capa em {account}: {exc}", flush=True)

    return updated


if __name__ == "__main__":
    reparar_ultima_capa_publicada()
