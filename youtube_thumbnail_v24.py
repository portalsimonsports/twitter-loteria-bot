from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

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


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, min_size: int = 20, bold: bool = True):
    size = start_size
    while size >= min_size:
        font = _font(size, bold=bold)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
        size -= 2
    return _font(min_size, bold=bold)


def _parse_money(value: str) -> float:
    text = re.sub(r"[^0-9,.-]", "", str(value or "")).strip()
    if not text:
        return 0.0
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _format_prize(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "R$" in text.upper():
        return text
    amount = _parse_money(text)
    if amount <= 0:
        return text
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def _largest_from_items(loterias: Sequence[Dict[str, str]], explicit: Dict[str, str] | None = None) -> Dict[str, str]:
    if explicit and str(explicit.get("premio") or "").strip():
        return {
            "loteria": str(explicit.get("loteria") or "").strip(),
            "premio": _format_prize(str(explicit.get("premio") or "").strip()),
        }
    best: Dict[str, str] = {}
    best_value = 0.0
    for item in loterias:
        raw = str(item.get("premio") or "").strip()
        amount = _parse_money(raw)
        if amount > best_value:
            best_value = amount
            best = {
                "loteria": str(item.get("loteria") or "").strip(),
                "premio": _format_prize(raw),
            }
    return best


def _draw_cover(data: str, loterias: List[Dict[str, str]], *, prize_highlight: Dict[str, str] | None = None, mode: str = "alerta") -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), (4, 18, 35))
    draw = ImageDraw.Draw(img)

    # identidade visual aprovada: azul profundo, faixa superior, títulos grandes e cartões limpos
    draw.rectangle((0, 0, WIDTH, 78), fill=(4, 73, 119))
    draw.rectangle((0, 650, WIDTH, HEIGHT), fill=(2, 35, 59))
    draw.text((38, 20), "PORTAL SIMONSPORTS", font=_font(28, True), fill=(255, 255, 255))
    draw.text((1000, 23), "LOTERIAS CAIXA", font=_font(22, True), fill=(255, 204, 0))

    heading = "LOTERIAS DE HOJE" if mode == "alerta" else "RESULTADOS DAS LOTERIAS"
    subheading = data
    heading_font = _fit_text(draw, heading, 820, 62, 36, True)
    draw.text((42, 105), heading, font=heading_font, fill=(255, 255, 255))
    draw.rounded_rectangle((960, 103, 1238, 176), radius=18, fill=(255, 204, 0))
    date_font = _fit_text(draw, subheading, 240, 30, 22, True)
    box = draw.textbbox((0, 0), subheading, font=date_font)
    draw.text((1099 - (box[2] - box[0]) / 2, 125), subheading, font=date_font, fill=(9, 26, 45))

    largest = _largest_from_items(loterias, prize_highlight)
    card_top = 245
    if largest:
        prize_text = f"MAIOR PRÊMIO DO DIA  •  {largest['loteria'].upper()}  •  {largest['premio']}"
        draw.rounded_rectangle((42, 188, 1238, 233), radius=14, fill=(255, 204, 0))
        prize_font = _fit_text(draw, prize_text, 1155, 25, 17, True)
        draw.text((62, 199), prize_text, font=prize_font, fill=(9, 26, 45))

    cols = 3
    card_w = 382
    card_h = 118
    gap_x = 24
    gap_y = 18
    x0 = 42
    for idx, item in enumerate(loterias[:6]):
        col = idx % cols
        row = idx // cols
        x = x0 + col * (card_w + gap_x)
        y = card_top + row * (card_h + gap_y)
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=20, fill=(9, 51, 84), outline=(38, 156, 216), width=3)
        nome = str(item.get("loteria") or "Loteria").strip()
        concurso = str(item.get("concurso") or "").strip()
        name_font = _fit_text(draw, nome.upper(), card_w - 30, 30, 20, True)
        draw.text((x + 16, y + 14), nome.upper(), font=name_font, fill=(255, 255, 255))
        if concurso:
            draw.text((x + 16, y + 67), f"CONCURSO {concurso}", font=_font(23, True), fill=(255, 204, 0))

    if mode == "alerta":
        footer = "ATIVE O SINO • INSCREVA-SE • RESULTADOS ATUALIZADOS EM PRIMEIRA MÃO"
    else:
        footer = "RESULTADOS OFICIAIS • CAIXA LOTERIAS • SIMONSPORTS"
    footer_font = _fit_text(draw, footer, 1180, 26, 18, True)
    draw.text((WIDTH / 2, 674), footer, font=footer_font, fill=(255, 255, 255), anchor="mm")
    return img


def gerar_capa_live(data: str, targets: Sequence[Tuple[str, str, str]], *, prize_highlight: Dict[str, str] | None = None) -> str:
    loterias = [{"loteria": display, "concurso": contest, "premio": ""} for _key, display, contest in targets]
    image = _draw_cover(data, loterias, prize_highlight=prize_highlight, mode="alerta")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"thumbnail_live_{data.replace('/', '-')}.jpg"
    image.save(path, "JPEG", quality=94, optimize=True)
    return str(path)


def gerar_capa_diaria(data: str, loterias: List[Dict[str, str]], *, video_id: str = "", prize_highlight: Dict[str, str] | None = None) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image = _draw_cover(data, loterias, prize_highlight=prize_highlight, mode="resultado")
    name = f"thumbnail_diaria_{data.replace('/', '-')}_{video_id or 'novo'}.jpg"
    path = OUT_DIR / name
    image.save(path, "JPEG", quality=94, optimize=True)
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

    video_id = ""
    for row in reversed(values[1:]):
        marker = row[daily_idx] if daily_idx < len(row) else ""
        vid = _extract_video_id(marker)
        if vid:
            video_id = vid
            break
    if not video_id:
        print("[THUMB V24] Nenhum videoId diário encontrado.", flush=True)
        return 0

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
        premio = str(item.get("premio") or item.get("premiacao") or item.get("prêmio") or "").strip()
        if not nome:
            continue
        key = (nome.casefold(), concurso)
        if key in seen:
            continue
        seen.add(key)
        loterias.append({"loteria": nome, "concurso": concurso, "premio": premio})
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
