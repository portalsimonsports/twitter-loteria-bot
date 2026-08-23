from __future__ import annotations

from typing import Any, Dict, Sequence, Tuple

from PIL import Image, ImageDraw

import daily_video_v19 as base


THEMES = {
    "Mega-Sena": ((0, 185, 85), (0, 92, 42), (0, 255, 122)),
    "Lotofácil": ((232, 0, 175), (108, 0, 89), (255, 66, 210)),
    "Quina": ((0, 193, 220), (0, 88, 128), (0, 238, 255)),
    "Timemania": ((160, 210, 0), (24, 115, 35), (225, 255, 0)),
    "Dupla Sena": ((220, 24, 46), (104, 0, 20), (255, 74, 74)),
    "Lotomania": ((255, 126, 0), (123, 45, 0), (255, 177, 54)),
    "Dia de Sorte": ((230, 151, 0), (110, 57, 0), (255, 211, 65)),
    "Super Sete": ((116, 177, 36), (42, 83, 7), (172, 255, 61)),
    "+Milionária": ((89, 72, 220), (36, 27, 110), (132, 113, 255)),
    "Loteria Federal": ((0, 133, 218), (0, 51, 102), (68, 189, 255)),
    "Loteca": ((0, 102, 214), (0, 37, 84), (44, 162, 255)),
}


def _norm_name(value: Any) -> str:
    return base._normalize_name(value)


def _theme(name: str):
    return THEMES.get(name, ((0, 160, 220), (0, 64, 110), (0, 224, 255)))


def _glow_rect(draw: ImageDraw.ImageDraw, box, *, fill, outline, width=5, radius=28):
    x1, y1, x2, y2 = box
    for spread, alpha in ((16, 40), (10, 70), (5, 110)):
        draw.rounded_rectangle((x1-spread, y1-spread, x2+spread, y2+spread), radius=radius+spread, outline=(*outline, alpha), width=max(2, width))
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _ball(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, fill, outline, label: str = ""):
    for spread, alpha in ((28, 22), (18, 35), (10, 60)):
        draw.ellipse((cx-r-spread, cy-r-spread, cx+r+spread, cy+r+spread), outline=(*outline, alpha), width=8)
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=fill, outline=outline, width=8)
    draw.ellipse((cx-r+25, cy-r+22, cx+r-25, cy+r-30), outline=(255,255,255,85), width=5)
    if label:
        font = base._fit_font(draw, label, int(r*1.45), int(r*0.38), 24)
        draw.text((cx, cy), label, font=font, fill="white", anchor="mm", stroke_width=4, stroke_fill=(0,0,0))


def _power_intro(results: Sequence[Dict[str, Any]], size: Tuple[int, int]) -> Image.Image:
    width, height = size
    focus = dict(results[0]) if results else {}
    focus_name = _norm_name(focus.get("loteria")) if focus else "Loterias"
    focus_contest = str(focus.get("concurso") or "").strip()
    date = str(focus.get("data") or "").strip()
    primary, dark, accent = _theme(focus_name)

    image = base._gradient(size, top=(1, 12, 35), bottom=(0, 3, 13))
    draw = ImageDraw.Draw(image, "RGBA")

    # Fundo elétrico / esportivo
    for y in range(0, height, max(14, height // 55)):
        a = max(8, 34 - int(y / max(1, height) * 22))
        draw.line((0, y, width, y), fill=(0, 120, 255, a), width=2)
    for x in range(width//2, width, max(28, width // 38)):
        draw.line((x, 0, width, int((x-width//2)*0.55)), fill=(0, 170, 255, 24), width=3)

    # Marca no topo
    draw.rounded_rectangle((42, 34, 660, 142), radius=28, fill=(0, 7, 24, 220), outline=(0, 167, 255, 160), width=3)
    draw.ellipse((67, 52, 147, 132), fill=(0, 120, 220), outline=(150, 235, 255), width=4)
    draw.text((107, 92), "S", font=base._font(42, True), fill="white", anchor="mm")
    draw.text((172, 52), "PORTAL", font=base._font(27, True), fill="white")
    draw.text((172, 83), "SIMONSPORTS", font=base._font(49, True), fill=(255,255,255))

    # Grande esfera da modalidade
    ball_r = int(min(width, height) * 0.235)
    ball_cx = width - ball_r - 70
    ball_cy = int(height * 0.36)
    _ball(draw, ball_cx, ball_cy, ball_r, (*dark, 255), accent, focus_name.lower())

    # Título gigante - linguagem das capas aprovadas
    left_w = int(width * 0.68)
    title = focus_name.upper()
    title_font = base._fit_font(draw, title, left_w - 100, int(height * 0.17), 58)
    draw.text((55, 178), title, font=title_font, fill=accent, stroke_width=7, stroke_fill=(0,0,0))

    contest_text = f"CONCURSO {focus_contest}" if focus_contest else "RESULTADOS DO DIA"
    contest_font = base._fit_font(draw, contest_text, left_w - 80, int(height * 0.145), 54)
    draw.text((58, 350), contest_text, font=contest_font, fill="white", stroke_width=7, stroke_fill=(0,0,0))

    banner_y1, banner_y2 = 540, 735
    _glow_rect(draw, (48, banner_y1, left_w, banner_y2), fill=(*dark, 245), outline=accent, width=5, radius=28)
    result_text = "RESULTADO DE HOJE"
    result_font = base._fit_font(draw, result_text, left_w-110, 88, 48)
    draw.text(((48+left_w)//2, (banner_y1+banner_y2)//2), result_text, font=result_font, fill="white", anchor="mm", stroke_width=4, stroke_fill=(0,0,0))

    # Bolas menores de apoio visual
    _ball(draw, width-440, height-250, 95, (245,245,245,255), accent, "07")
    _ball(draw, width-205, height-245, 90, (248,248,248,255), (255,209,45), "21")

    # Data e outras loterias
    _glow_rect(draw, (48, height-215, 760, height-62), fill=(0,8,28,238), outline=(0,153,255), width=4, radius=25)
    date_font = base._fit_font(draw, date or "HOJE", 620, 58, 34)
    draw.text((115, height-138), "▣", font=base._font(50, True), fill=(0,170,255), anchor="mm")
    draw.text((185, height-138), date or "HOJE", font=date_font, fill="white", anchor="lm", stroke_width=3, stroke_fill=(0,0,0))

    other_names = []
    for item in results[1:]:
        name = _norm_name(item.get("loteria")).upper()
        if name and name not in other_names:
            other_names.append(name)
    support = "+ " + " • ".join(other_names[:4]) if other_names else "+ RESULTADOS COMPLETOS"
    _glow_rect(draw, (800, height-215, width-45, height-62), fill=(0,8,28,238), outline=(0,153,255), width=4, radius=25)
    sup_font = base._fit_font(draw, support, width-900, 40, 24)
    draw.text((835, height-138), support, font=sup_font, fill=(255,224,70), anchor="lm", stroke_width=2, stroke_fill=(0,0,0))

    return image


def install() -> None:
    base._intro_image = _power_intro


install()
