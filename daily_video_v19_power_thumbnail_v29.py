from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

import daily_video_v19 as base

# Patch visual do fluxo existente. Não cria um segundo publicador.
# O módulo continua sendo importado pelo workflow atual e substitui somente
# o render visual de abertura/capa e das cenas verticais dos Shorts.
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

LOGO_DIR = Path("assets") / "logos"


def _slug(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("+", "mais-")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    aliases = {
        "loteria-federal": "federal",
        "mais-milionaria": "milionaria",
    }
    return aliases.get(text, text)


def _norm_name(value: Any) -> str:
    return base._normalize_name(value)


def _theme(name: str):
    return THEMES.get(_slug(name), ((0, 115, 190), (0, 37, 78), (65, 190, 255)))


def _gradient(size: Tuple[int, int], top=(4, 18, 45), bottom=(1, 5, 17)) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, width, y), fill=color)
    return image


def _glow_rect(draw: ImageDraw.ImageDraw, box, *, fill, outline, width=5, radius=28):
    x1, y1, x2, y2 = box
    for spread, alpha in ((15, 35), (8, 60)):
        draw.rounded_rectangle((x1-spread, y1-spread, x2+spread, y2+spread), radius=radius+spread, outline=(*outline, alpha), width=max(2, width))
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _brand(draw: ImageDraw.ImageDraw, size: Tuple[int, int]) -> None:
    width, height = size
    portrait = height > width
    scale = width / (1080 if portrait else 1920)
    x1 = int(42 * scale)
    y1 = int(35 * scale)
    x2 = int((690 if not portrait else 875) * scale)
    y2 = int(150 * scale)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=max(18, int(28*scale)), fill=(0, 7, 25, 225), outline=(70, 188, 255, 180), width=max(2, int(3*scale)))
    r = max(28, int(42 * scale))
    cx, cy = x1 + r + int(22*scale), (y1+y2)//2
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(0, 119, 210), outline=(179, 239, 255), width=max(2, int(3*scale)))
    draw.text((cx, cy), "S", font=base._font(max(24, int(42*scale)), True), fill="white", anchor="mm")
    tx = cx + r + int(25*scale)
    draw.text((tx, y1 + int(18*scale)), "PORTAL", font=base._font(max(16, int(25*scale)), True), fill=(176, 232, 255))
    draw.text((tx, y1 + int(47*scale)), "SIMONSPORTS", font=base._font(max(28, int(48*scale)), True), fill="white")


def _load_logo(name: str, max_size: Tuple[int, int]) -> Image.Image | None:
    slug = _slug(name)
    path = LOGO_DIR / f"{slug}.png"
    if not path.exists():
        return None
    try:
        logo = Image.open(path).convert("RGBA")
        logo.thumbnail(max_size, Image.Resampling.LANCZOS)
        return logo
    except Exception:
        return None


def _emblem(image: Image.Image, draw: ImageDraw.ImageDraw, name: str, center: Tuple[int, int], radius: int, dark, accent) -> None:
    cx, cy = center
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow, "RGBA")
    for spread, alpha in ((52, 22), (30, 38), (15, 62)):
        gd.ellipse((cx-radius-spread, cy-radius-spread, cx+radius+spread, cy+radius+spread), outline=(*accent, alpha), width=max(6, radius//16))
    glow = glow.filter(ImageFilter.GaussianBlur(max(3, radius//35)))
    image.paste(glow, (0, 0), glow)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=(*dark, 255), outline=(*accent, 255), width=max(6, radius//18))
    draw.ellipse((cx-radius+20, cy-radius+18, cx+radius-25, cy+radius-35), outline=(255,255,255,55), width=max(3, radius//45))
    logo = _load_logo(name, (int(radius*1.45), int(radius*0.86)))
    if logo:
        image.paste(logo, (int(cx-logo.width/2), int(cy-logo.height/2)), logo)
    else:
        f = base._fit_font(draw, name.upper(), int(radius*1.55), max(26, int(radius*0.31)), 20)
        draw.multiline_text((cx, cy), name.upper(), font=f, fill="white", anchor="mm", align="center", stroke_width=3, stroke_fill=(0,0,0))


def _support_names(results: Sequence[Dict[str, Any]], focus_name: str) -> str:
    names: List[str] = []
    for item in results:
        n = _norm_name(item.get("loteria")).upper()
        if n and n.casefold() != focus_name.casefold() and n not in names:
            names.append(n)
    return "+ " + " • ".join(names[:4]) if names else "+ RESULTADOS COMPLETOS"


def _power_intro(results: Sequence[Dict[str, Any]], size: Tuple[int, int]) -> Image.Image:
    width, height = size
    portrait = height > width
    focus = dict(results[0]) if results else {}
    focus_name = _norm_name(focus.get("loteria")) if focus else "Loterias"
    contest = str(focus.get("concurso") or "").strip()
    date = str(focus.get("data") or "").strip()
    primary, dark, accent = _theme(focus_name)

    image = _gradient(size)
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(0, height, max(18, height // 55)):
        draw.line((0, y, width, y), fill=(*primary, 18), width=2)
    _brand(draw, size)

    if portrait:
        title_y = 245
        title_font = base._fit_font(draw, focus_name.upper(), width-90, 100, 46)
        draw.text((width//2, title_y), focus_name.upper(), font=title_font, fill=accent, anchor="mm", stroke_width=5, stroke_fill=(0,0,0))
        contest_text = f"CONCURSO {contest}" if contest else "RESULTADOS DO DIA"
        cf = base._fit_font(draw, contest_text, width-120, 64, 34)
        draw.text((width//2, 365), contest_text, font=cf, fill="white", anchor="mm", stroke_width=4, stroke_fill=(0,0,0))
        _emblem(image, draw, focus_name, (width//2, 760), 250, dark, accent)
        draw = ImageDraw.Draw(image, "RGBA")
        _glow_rect(draw, (90, 1090, width-90, 1270), fill=(*dark,245), outline=accent, width=5, radius=30)
        rf = base._fit_font(draw, "RESULTADO DE HOJE", width-250, 66, 36)
        draw.text((width//2, 1180), "RESULTADO DE HOJE", font=rf, fill="white", anchor="mm", stroke_width=3, stroke_fill=(0,0,0))
        _glow_rect(draw, (90, 1350, width-90, 1450), fill=(0,8,28,238), outline=(0,153,255), width=4, radius=24)
        draw.text((width//2, 1400), date or "HOJE", font=base._fit_font(draw, date or "HOJE", width-230, 42, 25), fill="white", anchor="mm")
        support = _support_names(results, focus_name.upper())
        draw.rounded_rectangle((55, height-215, width-55, height-90), radius=26, fill=(0,6,23,238), outline=(58,166,255,180), width=3)
        draw.text((width//2, height-152), support, font=base._fit_font(draw, support, width-150, 31, 19), fill=(255,222,63), anchor="mm", stroke_width=2, stroke_fill=(0,0,0))
    else:
        left = int(width*0.62)
        title_font = base._fit_font(draw, focus_name.upper(), left-90, 112, 56)
        draw.text((55, 180), focus_name.upper(), font=title_font, fill=accent, stroke_width=6, stroke_fill=(0,0,0))
        contest_text = f"CONCURSO {contest}" if contest else "RESULTADOS DO DIA"
        cf = base._fit_font(draw, contest_text, left-90, 72, 40)
        draw.text((58, 350), contest_text, font=cf, fill="white", stroke_width=5, stroke_fill=(0,0,0))
        _glow_rect(draw, (55, 510, left, 675), fill=(*dark,245), outline=accent, width=5, radius=30)
        rf = base._fit_font(draw, "RESULTADO DE HOJE", left-130, 70, 38)
        draw.text(((55+left)//2, 593), "RESULTADO DE HOJE", font=rf, fill="white", anchor="mm", stroke_width=3, stroke_fill=(0,0,0))
        _emblem(image, draw, focus_name, (width-350, 380), 265, dark, accent)
        draw = ImageDraw.Draw(image, "RGBA")
        _glow_rect(draw, (55, height-220, 650, height-75), fill=(0,8,28,238), outline=(0,153,255), width=4, radius=24)
        draw.text((95, height-147), date or "HOJE", font=base._fit_font(draw, date or "HOJE", 500, 46, 28), fill="white", anchor="lm")
        support = _support_names(results, focus_name.upper())
        _glow_rect(draw, (700, height-220, width-55, height-75), fill=(0,8,28,238), outline=(0,153,255), width=4, radius=24)
        draw.text(((700+width-55)//2, height-147), support, font=base._fit_font(draw, support, width-820, 37, 22), fill=(255,222,63), anchor="mm", stroke_width=2, stroke_fill=(0,0,0))
    return image


def _short_result_approved(data: Dict[str, Any]) -> Image.Image:
    size = (1080, 1920)
    width, height = size
    name = _norm_name(data.get("loteria"))
    contest = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or "").strip()
    primary, dark, accent = _theme(name)
    image = _gradient(size)
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(0, height, 35):
        draw.line((0, y, width, y), fill=(*primary, 17), width=2)
    _brand(draw, size)

    title = name.upper()
    draw.text((width//2, 255), title, font=base._fit_font(draw, title, width-90, 94, 44), fill=accent, anchor="mm", stroke_width=5, stroke_fill=(0,0,0))
    subtitle = f"CONCURSO {contest}" if contest else "RESULTADO OFICIAL"
    draw.text((width//2, 375), subtitle, font=base._fit_font(draw, subtitle, width-120, 60, 32), fill="white", anchor="mm", stroke_width=4, stroke_fill=(0,0,0))

    _emblem(image, draw, name, (width//2, 690), 205, dark, accent)
    draw = ImageDraw.Draw(image, "RGBA")
    _glow_rect(draw, (85, 945, width-85, 1095), fill=(*dark,245), outline=accent, width=5, radius=28)
    draw.text((width//2, 1020), "RESULTADO DE HOJE", font=base._fit_font(draw, "RESULTADO DE HOJE", width-220, 57, 32), fill="white", anchor="mm", stroke_width=3, stroke_fill=(0,0,0))

    # Mantém a informação do resultado no Short, mas dentro do novo padrão visual.
    try:
        parts = base.parse_lottery_result(name, base._raw_result(data))
        values = list(parts.display_numbers)
    except Exception:
        values = []

    if values:
        # Até 20 dezenas, distribuídas em linhas compactas. Para Loteca/Federal,
        # o fluxo base continua exibindo o conteúdo especial em outras cenas do vídeo.
        values = [str(v).zfill(2) if str(v).isdigit() and len(str(v)) < 2 else str(v) for v in values[:20]]
        cols = 5 if len(values) > 10 else 4 if len(values) > 6 else min(3, max(1, len(values)))
        rows = (len(values) + cols - 1) // cols
        area_top, area_bottom = 1160, 1620
        cell_w = (width - 150) / cols
        cell_h = (area_bottom - area_top) / max(1, rows)
        r = int(min(58, cell_w*0.28, cell_h*0.32))
        f = base._font(max(24, int(r*0.72)), True)
        for i, value in enumerate(values):
            row, col = divmod(i, cols)
            row_count = min(cols, len(values)-row*cols)
            row_w = row_count * cell_w
            start_x = (width-row_w)/2
            cx = start_x + (col+0.5)*cell_w
            cy = area_top + (row+0.5)*cell_h
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(248,248,248,255), outline=(*accent,255), width=5)
            draw.text((cx, cy), value, font=f, fill=(18,22,30), anchor="mm")

    draw.rounded_rectangle((70, height-230, width-70, height-105), radius=25, fill=(0,6,23,238), outline=(58,166,255,180), width=3)
    footer = date or "HOJE"
    draw.text((width//2, height-167), footer, font=base._fit_font(draw, footer, width-180, 38, 23), fill=(255,222,63), anchor="mm")
    return image


def install() -> None:
    base._intro_image = _power_intro
    base._result_short_image = _short_result_approved


install()
