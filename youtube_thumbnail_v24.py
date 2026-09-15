from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import daily_queue_v19 as queue
from youtube_auth import get_access_token
from youtube_upload import upload_thumbnail

WIDTH = 1280
HEIGHT = 720
OUT_DIR = Path("output")
LOGO_DIR = Path("assets") / "logos"

# Padrão visual aprovado pelo Portal SimonSports.
# A capa é sempre dinâmica: modalidade, concurso, data e modalidades auxiliares
# vêm dos dados reais da publicação. Não usar mais o layout azul genérico anterior.
THEMES = {
    "mega-sena": ((0, 150, 69), (0, 67, 39), (32, 255, 128)),
    "lotofacil": ((164, 28, 142), (67, 9, 69), (255, 68, 215)),
    "quina": ((0, 91, 171), (0, 35, 83), (0, 213, 255)),
    "timemania": ((90, 157, 39), (23, 71, 31), (216, 255, 44)),
    "dupla-sena": ((190, 30, 58), (76, 8, 31), (255, 79, 101)),
    "lotomania": ((235, 112, 19), (100, 38, 8), (255, 180, 65)),
    "loteca": ((0, 87, 191), (0, 32, 78), (62, 171, 255)),
    "dia-de-sorte": ((205, 140, 0), (92, 51, 0), (255, 213, 64)),
    "super-sete": ((99, 164, 38), (34, 74, 11), (173, 255, 74)),
    "milionaria": ((78, 62, 185), (32, 23, 87), (151, 127, 255)),
    "federal": ((0, 127, 185), (0, 48, 80), (83, 209, 255)),
}

LOGO_SLUGS = {
    "mega-sena": "mega-sena",
    "lotofacil": "lotofacil",
    "quina": "quina",
    "timemania": "timemania",
    "dupla-sena": "dupla-sena",
    "lotomania": "lotomania",
    "loteca": "loteca",
    "dia-de-sorte": "dia-de-sorte",
    "super-sete": "super-sete",
    "milionaria": "milionaria",
    "federal": "federal",
}


def _font(size: int, bold: bool = False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _fit(draw, text, max_width, start, minimum=18, bold=True):
    text = str(text or "")
    for size in range(start, minimum - 1, -2):
        f = _font(size, bold)
        if draw.textbbox((0, 0), text, font=f)[2] <= max_width:
            return f
    return _font(minimum, bold)


def _slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("+", "mais-")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    aliases = {
        "lotofacil": "lotofacil",
        "dupla-sena": "dupla-sena",
        "mega-sena": "mega-sena",
        "loteria-federal": "federal",
        "mais-milionaria": "milionaria",
    }
    return aliases.get(text, text)


def _theme(name: str):
    slug = _slug(name)
    return THEMES.get(slug, ((0, 115, 190), (0, 37, 78), (65, 190, 255)))


def _money_value(value: str) -> float:
    text = re.sub(r"[^0-9,.-]", "", str(value or ""))
    if not text:
        return 0.0
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return 0.0


def _money_text(value: str) -> str:
    amount = _money_value(value)
    if amount <= 0:
        return str(value or "").strip()
    return "R$ " + f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _largest(loterias: Sequence[Dict[str, str]], explicit: Dict[str, str] | None = None) -> Dict[str, str]:
    if explicit and _money_value(explicit.get("premio", "")) > 0:
        return {
            "loteria": str(explicit.get("loteria") or "").strip(),
            "premio": _money_text(explicit.get("premio", "")),
            "concurso": str(explicit.get("concurso") or "").strip(),
        }
    best, best_value = {}, 0.0
    for item in loterias:
        amount = _money_value(item.get("premio", ""))
        if amount > best_value:
            best_value = amount
            best = {
                "loteria": str(item.get("loteria") or "").strip(),
                "premio": _money_text(item.get("premio", "")),
                "concurso": str(item.get("concurso") or "").strip(),
            }
    return best or (dict(loterias[0]) if loterias else {})


def _gradient(top, bottom) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), top)
    px = img.load()
    for y in range(HEIGHT):
        t = y / max(1, HEIGHT - 1)
        for x in range(WIDTH):
            # leve escurecimento para a direita, como nas capas aprovadas
            side = 1.0 - 0.30 * (x / WIDTH)
            px[x, y] = tuple(int((top[i] * (1 - t) + bottom[i] * t) * side) for i in range(3))
    return img


def _draw_brand(draw: ImageDraw.ImageDraw) -> None:
    # Marca SimonSports em bloco superior, preservando leitura em telas pequenas.
    draw.rounded_rectangle((34, 24, 370, 105), radius=22, fill=(0, 7, 25, 225), outline=(70, 188, 255, 180), width=3)
    draw.ellipse((52, 37, 112, 97), fill=(0, 119, 210), outline=(179, 239, 255), width=3)
    draw.text((82, 67), "S", font=_font(32, True), fill="white", anchor="mm")
    draw.text((130, 39), "PORTAL", font=_font(17, True), fill=(176, 232, 255))
    draw.text((130, 59), "SIMONSPORTS", font=_font(31, True), fill="white")


def _load_lottery_logo(name: str, max_size=(270, 170)) -> Image.Image | None:
    slug = LOGO_SLUGS.get(_slug(name), _slug(name))
    path = LOGO_DIR / f"{slug}.png"
    if not path.exists():
        return None
    try:
        logo = Image.open(path).convert("RGBA")
        logo.thumbnail(max_size, Image.Resampling.LANCZOS)
        return logo
    except Exception:
        return None


def _draw_focus_emblem(img: Image.Image, draw: ImageDraw.ImageDraw, name: str, dark, accent) -> None:
    cx, cy, r = 1030, 310, 175
    # brilho sem depender de bibliotecas externas
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow, "RGBA")
    for spread, alpha in ((55, 24), (35, 38), (18, 58)):
        gd.ellipse((cx-r-spread, cy-r-spread, cx+r+spread, cy+r+spread), outline=(*accent, alpha), width=12)
    glow = glow.filter(ImageFilter.GaussianBlur(5))
    img.paste(glow, (0, 0), glow)
    draw = ImageDraw.Draw(img, "RGBA")
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(*dark, 255), outline=(*accent, 255), width=8)
    draw.ellipse((cx-r+22, cy-r+20, cx+r-25, cy+r-38), outline=(255, 255, 255, 55), width=5)
    logo = _load_lottery_logo(name)
    if logo:
        x = int(cx - logo.width / 2)
        y = int(cy - logo.height / 2)
        img.paste(logo, (x, y), logo)
    else:
        f = _fit(draw, name.upper(), 280, 42, 22, True)
        draw.multiline_text((cx, cy), name.upper(), font=f, fill="white", anchor="mm", align="center", stroke_width=3, stroke_fill=(0, 0, 0))


def _draw_approved(data: str, loterias: List[Dict[str, str]], *, prize_highlight=None, mode="alerta") -> Image.Image:
    focus = _largest(loterias, prize_highlight)
    focus_name = str(focus.get("loteria") or "LOTERIAS").strip()
    focus_contest = str(focus.get("concurso") or "").strip()
    focus_prize = str(focus.get("premio") or "").strip()
    primary, dark, accent = _theme(focus_name)

    img = _gradient((4, 18, 45), (1, 5, 17))
    draw = ImageDraw.Draw(img, "RGBA")

    # Luz diagonal e trilhas que reproduzem a linguagem tecnológica das capas aprovadas.
    for y in range(0, HEIGHT, 24):
        draw.line((0, y, WIDTH, y), fill=(*primary, 18), width=2)
    for x in range(650, WIDTH, 62):
        draw.line((x, 0, WIDTH, int((x - 650) * 0.70)), fill=(*accent, 17), width=3)

    _draw_brand(draw)
    _draw_focus_emblem(img, draw, focus_name, dark, accent)
    draw = ImageDraw.Draw(img, "RGBA")

    # Nome da modalidade dominante: principal elemento visual aprovado.
    title = focus_name.upper()
    title_font = _fit(draw, title, 760, 102, 48, True)
    draw.text((42, 138), title, font=title_font, fill=accent, stroke_width=5, stroke_fill=(0, 0, 0))

    contest = f"CONCURSO {focus_contest}" if focus_contest else "LOTERIAS DE HOJE"
    contest_font = _fit(draw, contest, 730, 67, 36, True)
    draw.text((46, 262), contest, font=contest_font, fill="white", stroke_width=4, stroke_fill=(0, 0, 0))

    main_label = "SORTEIO DE HOJE" if mode == "alerta" else "RESULTADO DE HOJE"
    draw.rounded_rectangle((44, 355, 725, 465), radius=23, fill=(*dark, 245), outline=(*accent, 255), width=5)
    label_font = _fit(draw, main_label, 620, 55, 32, True)
    draw.text((385, 410), main_label, font=label_font, fill="white", anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))

    # Data em caixa própria, sempre atualizada pelos dados da publicação.
    draw.rounded_rectangle((44, 510, 385, 575), radius=18, fill=(0, 9, 28, 235), outline=(67, 174, 255, 210), width=3)
    draw.text((69, 542), data or "HOJE", font=_fit(draw, data or "HOJE", 286, 30, 20, True), fill="white", anchor="lm")

    # Prêmio só entra se houver dado real; não desloca o padrão aprovado quando ausente.
    if focus_prize:
        prize = focus_prize if focus_prize.upper().startswith("R$") else _money_text(focus_prize)
        draw.rounded_rectangle((410, 510, 775, 575), radius=18, fill=(0, 9, 28, 235), outline=(*accent, 210), width=3)
        draw.text((430, 542), prize, font=_fit(draw, prize, 325, 28, 18, True), fill=(255, 224, 78), anchor="lm")

    # Faixa inferior como nas referências aprovadas: demais modalidades do mesmo dia.
    others: List[str] = []
    for item in loterias:
        name = str(item.get("loteria") or "").strip().upper()
        if name and name.casefold() != focus_name.upper().casefold() and name not in others:
            others.append(name)
    support = "+ " + " • ".join(others[:5]) if others else "+ RESULTADOS COMPLETOS"
    draw.rounded_rectangle((35, 622, 1245, 694), radius=19, fill=(0, 6, 23, 238), outline=(58, 166, 255, 180), width=3)
    draw.text((640, 658), support, font=_fit(draw, support, 1145, 32, 20, True), fill=(255, 222, 63), anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))

    return img


def gerar_capa_live(data: str, targets: Sequence[Tuple[str, str, str]], *, prize_highlight: Dict[str, str] | None = None) -> str:
    loterias = [{"loteria": display, "concurso": contest, "premio": ""} for _key, display, contest in targets]
    image = _draw_approved(data, loterias, prize_highlight=prize_highlight, mode="alerta")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"thumbnail_live_{data.replace('/', '-')}.jpg"
    image.save(path, "JPEG", quality=95, optimize=True)
    return str(path)


def gerar_capa_diaria(data: str, loterias: List[Dict[str, str]], *, video_id: str = "", prize_highlight: Dict[str, str] | None = None) -> str:
    image = _draw_approved(data, loterias, prize_highlight=prize_highlight, mode="resultado")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"thumbnail_diaria_{data.replace('/', '-')}_{video_id or 'novo'}.jpg"
    image.save(path, "JPEG", quality=95, optimize=True)
    return str(path)


def _extract_video_id(text: str) -> str:
    m = re.search(r"youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})", str(text or ""))
    return m.group(1) if m else ""


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
        return 0
    video_id = ""
    for row in reversed(values[1:]):
        video_id = _extract_video_id(row[daily_idx] if daily_idx < len(row) else "")
        if video_id:
            break
    if not video_id:
        return 0
    loterias = []
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
        key = (nome.casefold(), concurso)
        if not nome or key in seen:
            continue
        seen.add(key)
        loterias.append({"loteria": nome, "concurso": concurso, "premio": premio})
        data = data or str(item.get("data") or "").strip()
    if not loterias:
        return 0
    thumb = gerar_capa_diaria(data, loterias, video_id=video_id)
    accounts = sorted({str(account).strip() for network, account, key in (cofre_cache.get("creds_rc", {}) or {}).keys() if str(network).strip().upper() == "YOUTUBE" and str(key).strip().upper() == "REFRESH_TOKEN" and account})
    updated = 0
    for account in accounts:
        cid = cofre_get("YOUTUBE", "CLIENT_ID", conta=account, default="")
        sec = cofre_get("YOUTUBE", "CLIENT_SECRET", conta=account, default="")
        ref = cofre_get("YOUTUBE", "REFRESH_TOKEN", conta=account, default="")
        if not (cid and sec and ref):
            continue
        try:
            upload_thumbnail(get_access_token(cid, sec, ref), video_id, thumb)
            updated += 1
        except Exception as exc:
            print(f"[THUMB] {account}: {exc}", flush=True)
    return updated


if __name__ == "__main__":
    reparar_ultima_capa_publicada()
