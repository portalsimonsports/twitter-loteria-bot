from __future__ import annotations

import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Sequence, Tuple
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

import video_visual_v3 as base

WIDTH = base.WIDTH
HEIGHT = base.HEIGHT
prepare_numbers = base.prepare_numbers

PALETTES: Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]] = {
    "mega-sena": ((0, 151, 87), (0, 46, 31), (105, 255, 179)),
    "lotofacil": ((147, 28, 143), (47, 8, 55), (247, 153, 255)),
    "quina": ((46, 45, 154), (14, 15, 64), (151, 171, 255)),
    "lotomania": ((240, 103, 30), (91, 30, 8), (255, 207, 129)),
    "timemania": ((0, 151, 167), (0, 48, 60), (126, 240, 252)),
    "dupla-sena": ((176, 27, 65), (66, 7, 26), (255, 151, 180)),
    "dia-de-sorte": ((207, 150, 25), (70, 44, 5), (255, 229, 132)),
    "super-sete": ((55, 143, 70), (13, 54, 27), (157, 242, 168)),
    "mais-milionaria": ((65, 66, 76), (15, 16, 22), (232, 198, 91)),
    "federal": ((31, 99, 184), (8, 32, 75), (132, 202, 255)),
    "loteca": ((0, 119, 193), (0, 38, 79), (130, 217, 255)),
}


def _mix(a, b, ratio: float):
    ratio = max(0.0, min(1.0, ratio))
    return tuple(round(a[i] * (1.0 - ratio) + b[i] * ratio) for i in range(3))


def _palette(loteria: str, override: Any = None):
    if isinstance(override, (list, tuple)) and len(override) == 3:
        try:
            primary = tuple(max(0, min(255, int(x))) for x in override)
            return primary, _mix(primary, (0, 0, 0), 0.72), _mix(primary, (255, 255, 255), 0.52)
        except Exception:
            pass
    key = base._slug(loteria)
    for name, colors in PALETTES.items():
        if name in key or key in name:
            return colors
    return (25, 105, 164), (7, 31, 72), (144, 220, 255)


def _contrast(color):
    lum = 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]
    return (16, 18, 22) if lum > 165 else (255, 255, 255)


def _base_image(path: str, colors) -> Image.Image:
    primary, dark, light = colors
    top = _mix(primary, (255, 255, 255), 0.08)
    bottom = _mix(dark, primary, 0.18)
    image = base._gradient(top, bottom).convert("RGBA")
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow, "RGBA")
    gd.ellipse((-base._s(260), base._s(210), WIDTH + base._s(260), base._s(1440)), fill=(*light, 34))
    image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(base._s(110))))
    if path and os.path.exists(path):
        try:
            photo = base._cover(Image.open(path)).filter(ImageFilter.GaussianBlur(base._s(2)))
            photo = ImageEnhance.Contrast(photo).enhance(1.12)
            photo = ImageEnhance.Brightness(photo).enhance(0.60)
            tinted = Image.blend(photo, Image.new("RGB", photo.size, primary), 0.38)
            image = Image.blend(image.convert("RGB"), tinted, 0.24).convert("RGBA")
        except Exception:
            pass
    return image


def _decorate(image: Image.Image, primary, light, seed: int) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    center = (WIDTH // 2, round(HEIGHT * 0.53))
    for index in range(20):
        angle = -2.82 + index * 0.30
        length = base._s(520 + (index % 5) * 80)
        x2 = center[0] + int(math.cos(angle) * length)
        y2 = center[1] + int(math.sin(angle) * length)
        draw.line((center[0], center[1], x2, y2), fill=(*light, 24 + (index % 4) * 10), width=max(1, base._s(3)))
    value = (seed * 1103515245 + 12345) & 0x7FFFFFFF
    for _ in range(105):
        value = (value * 1103515245 + 12345) & 0x7FFFFFFF
        x = value % WIDTH
        value = (value * 1103515245 + 12345) & 0x7FFFFFFF
        y = value % HEIGHT
        radius = base._s(1 + value % 4)
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(*light, 34 + value % 118))
    for index in range(4):
        margin = base._s(105 + index * 90)
        y1 = base._s(1180 + index * 34)
        y2 = base._s(1400 - index * 12)
        draw.ellipse((margin, y1, WIDTH-margin, y2), outline=(*primary, 80-index*12), width=max(1, base._s(5-index)))


def _brand(draw, primary, dark, light, preview: bool) -> None:
    base._panel(draw, (46, 38, 1034, 160), 35, (*dark, 224), (*light, 90), 2)
    draw.ellipse((base._s(76), base._s(67), base._s(146), base._s(137)), fill=(*primary, 255), outline=(*light, 230), width=base._s(3))
    base._center(draw, (base._s(111), base._s(102)), "S", 34, _contrast(primary), True)
    draw.text((base._s(172), base._s(65)), "PORTAL", font=base._font(25, True), fill=(*light, 245))
    draw.text((base._s(172), base._s(95)), "SIMONSPORTS", font=base._font(41, True), fill=(255, 255, 255, 255))
    draw.text((base._s(995), base._s(103)), "RESULTADOS", font=base._font(23, True), fill=(*light, 255), anchor="rm")
    if preview:
        base._panel(draw, (750, 184, 1032, 247), 22, (244, 188, 35, 245))
        base._center(draw, (base._s(891), base._s(215)), "PRÉVIA DE APROVAÇÃO", 19, (24, 22, 14), True)


def _title(draw, loteria: str, concurso: str, data: str, primary, light) -> None:
    size = 86 if len(loteria) <= 13 else 68 if len(loteria) <= 20 else 54
    base._center(draw, (base._s(540), base._s(325)), loteria.upper(), size, (255, 255, 255), True, 2, (0, 0, 0, 165))
    meta = "  •  ".join(x for x in [f"CONCURSO {concurso}" if concurso else "", data] if x) or "RESULTADO OFICIAL"
    base._center(draw, (base._s(540), base._s(417)), meta, 31, light, True)
    draw.rounded_rectangle((base._s(250), base._s(460), base._s(830), base._s(468)), radius=base._s(4), fill=(*primary, 225))


def _ball(draw, x, y, diameter, number, shown, is_new, primary, dark, light) -> None:
    box = tuple(base._s(v) for v in (x, y, x + diameter, y + diameter))
    if shown:
        glow = base._s(20 if is_new else 10)
        draw.ellipse((box[0]-glow, box[1]-glow, box[2]+glow, box[3]+glow), fill=(*light, 76 if is_new else 32))
        fill = _mix(primary, (255, 255, 255), 0.12 if is_new else 0.03)
        draw.ellipse(box, fill=(*fill, 255), outline=(*light, 255), width=max(3, base._s(8 if is_new else 5)))
        h = base._s(max(8, diameter * 0.12))
        draw.ellipse((box[0]+h, box[1]+h, box[0]+h*3, box[1]+h*2), fill=(255, 255, 255, 105))
        fs = 54 if diameter >= 116 else 43 if diameter >= 100 else 34
        if len(number) > 3:
            fs = max(20, round(fs * 0.62))
        base._center(draw, ((box[0]+box[2])//2, (box[1]+box[3])//2 + base._s(2)), number, fs, _contrast(fill), True, 1, (*dark, 150))
    else:
        draw.ellipse(box, fill=(*dark, 175), outline=(*primary, 165), width=max(2, base._s(4)))
        base._center(draw, ((box[0]+box[2])//2, (box[1]+box[3])//2), "?", 39, (*light, 150), True)


def _numbers(draw, numbers: Sequence[str], visible: int, primary, dark, light) -> None:
    count = max(1, len(numbers))
    columns, rows, diameter, gap = base._number_layout(count)
    vertical_gap = 28 if rows <= 2 else 22
    total_height = rows * diameter + (rows - 1) * vertical_gap
    start_y = 575 + max(0, (760 - total_height) // 2)
    new_group = max(1, math.ceil(count / 6))
    for index in range(count):
        row, column = divmod(index, columns)
        row_count = min(columns, count - row * columns)
        row_width = row_count * diameter + (row_count - 1) * gap
        start_x = (1080 - row_width) // 2
        shown = index < visible
        _ball(draw, start_x + column * (diameter + gap), start_y + row * (diameter + vertical_gap), diameter, numbers[index], shown, shown and index >= max(0, visible-new_group), primary, dark, light)


def _dupla(draw, numbers: Sequence[str], visible: int, primary, dark, light) -> None:
    for group_index, (label, values, label_y) in enumerate((("1º SORTEIO", numbers[:6], 610), ("2º SORTEIO", numbers[6:12], 1010))):
        base._panel(draw, (340, label_y, 740, label_y + 66), 25, (*primary, 235), (*light, 220), 2)
        base._center(draw, (base._s(540), base._s(label_y + 33)), label, 29, _contrast(primary), True)
        diameter, gap = 118, 28
        start_x = (1080 - (len(values) * diameter + max(0, len(values)-1) * gap)) // 2
        group_visible = max(0, min(6, visible - group_index * 6))
        for index, number in enumerate(values):
            shown = index < group_visible
            _ball(draw, start_x + index * (diameter + gap), label_y + 102, diameter, number, shown, shown and index == group_visible - 1, primary, dark, light)


def _footer(draw, data: Dict[str, Any], light) -> None:
    updated = str(data.get("atualizado_em") or "").strip()
    if not updated:
        try:
            updated = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y às %H:%M")
        except Exception:
            updated = datetime.now().strftime("%d/%m/%Y às %H:%M")
    base._center(draw, (base._s(540), base._s(1805)), f"FONTE: CAIXA LOTERIAS  •  ATUALIZADO EM {updated}", 18, (*light, 235), True)
    base._center(draw, (base._s(540), base._s(1850)), "CONTEÚDO INFORMATIVO • RESULTADO OFICIAL", 20, (255, 255, 255, 188), False)


def scene_image(data: Dict[str, Any], scene: str, visible_count: int = 0, seed: int = 1) -> Image.Image:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or data.get("data_sorteio") or "").strip()
    prize = str(data.get("premio") or data.get("estimativa") or "").strip()
    url = str(data.get("url") or "https://www.portalsimonsports.com/").strip()
    image_path = str(data.get("imagem_path") or "").strip()
    preview = bool(data.get("previa", False))
    numbers, extra = prepare_numbers(loteria, data.get("numeros") or data.get("descricao") or "")
    key = base._slug(loteria)
    primary, dark, light = _palette(loteria, data.get("cor_fundo_rgb"))

    image = _base_image(image_path, (primary, dark, light))
    image = Image.alpha_composite(image, Image.new("RGBA", image.size, (0, 0, 0, 12)))
    _decorate(image, primary, light, seed)
    draw = ImageDraw.Draw(image, "RGBA")
    _brand(draw, primary, dark, light, preview)

    if scene == "intro":
        base._center(draw, (base._s(540), base._s(430)), loteria.upper(), 110 if len(loteria) <= 13 else 78, (255, 255, 255), True, 3, (0, 0, 0, 175))
        if concurso:
            base._panel(draw, (255, 575, 825, 665), 30, (*primary, 240), (*light, 210), 2)
            base._center(draw, (base._s(540), base._s(620)), f"CONCURSO {concurso}", 40, _contrast(primary), True)
        base._center(draw, (base._s(540), base._s(820)), "RESULTADO OFICIAL", 43, (250, 255, 252), True)
        base._center(draw, (base._s(540), base._s(930)), "CONFIRA AGORA", 64, light, True, 2, (0, 0, 0, 160))
        if date:
            base._center(draw, (base._s(540), base._s(1040)), f"SORTEIO DE {date}", 30, (242, 255, 247), True)
        for index, diameter in enumerate((150, 120, 90)):
            cx = 390 + index * 150
            box = (base._s(cx-diameter//2), base._s(1395-diameter//2), base._s(cx+diameter//2), base._s(1395+diameter//2))
            draw.ellipse(box, fill=(*primary, 185-index*25), outline=(*light, 230), width=base._s(4))

    elif scene == "reveal":
        _title(draw, loteria, concurso, date, primary, light)
        base._center(draw, (base._s(540), base._s(520)), "NÚMEROS SORTEADOS", 31, (245, 255, 249), True)
        if numbers:
            _dupla(draw, numbers, visible_count, primary, dark, light) if "dupla-sena" in key and len(numbers) >= 12 else _numbers(draw, numbers, visible_count, primary, dark, light)
        else:
            base._center(draw, (base._s(540), base._s(780)), "14 JOGOS", 105, light, True, 3, (0, 0, 0, 170))
            base._center(draw, (base._s(540), base._s(930)), "PLACARES E RESULTADOS", 47, (255, 255, 255), True)
            base._center(draw, (base._s(540), base._s(1020)), extra or "CONFIRA NO PORTAL", 31, light, True)

    elif scene == "final":
        _title(draw, loteria, concurso, date, primary, light)
        base._center(draw, (base._s(540), base._s(520)), "RESULTADO COMPLETO", 39, (255, 255, 255), True)
        if numbers:
            _dupla(draw, numbers, len(numbers), primary, dark, light) if "dupla-sena" in key and len(numbers) >= 12 else _numbers(draw, numbers, len(numbers), primary, dark, light)
        if extra:
            base._center(draw, (base._s(540), base._s(1450)), extra.upper(), 25, (242, 255, 247), True)
        if prize:
            base._panel(draw, (110, 1485, 970, 1645), 42, (*primary, 230), (*light, 190), 2)
            base._center(draw, (base._s(540), base._s(1530)), "PRÓXIMO PRÊMIO ESTIMADO", 24, _contrast(primary), True)
            base._center(draw, (base._s(540), base._s(1590)), prize, 50, _contrast(primary), True)

    else:
        base._center(draw, (base._s(540), base._s(350)), "RESULTADO COMPLETO", 68, (255, 255, 255), True, 2, (0, 0, 0, 160))
        base._center(draw, (base._s(540), base._s(500)), "PORTAL", 78, light, True, 3, (0, 0, 0, 180))
        base._center(draw, (base._s(540), base._s(605)), "SIMONSPORTS", 74, (255, 255, 255), True, 2, (0, 0, 0, 160))
        base._panel(draw, (160, 730, 920, 855), 42, (*primary, 235), (*light, 200), 2)
        base._center(draw, (base._s(540), base._s(792)), "LINK NA DESCRIÇÃO", 42, _contrast(primary), True)
        domain = re.sub(r"^https?://", "", url).split("/")[0] or "www.portalsimonsports.com"
        base._center(draw, (base._s(540), base._s(925)), domain, 31, (242, 255, 247), True)
        labels = [("RESULTADOS", "ATUALIZADOS"), ("FONTE", "OFICIAL"), ("TODAS AS", "LOTERIAS")]
        for index, (line1, line2) in enumerate(labels):
            cx = 220 + index * 320
            draw.ellipse((base._s(cx-54), base._s(1080), base._s(cx+54), base._s(1188)), fill=(*dark, 220), outline=(*light, 190), width=base._s(3))
            base._center(draw, (base._s(cx), base._s(1134)), "✓", 44, light, True)
            base._center(draw, (base._s(cx), base._s(1245)), line1, 20, (255, 255, 255), True)
            base._center(draw, (base._s(cx), base._s(1278)), line2, 20, light, True)
        base._panel(draw, (150, 1430, 930, 1580), 42, (*primary, 220), (*light, 190), 2)
        base._center(draw, (base._s(540), base._s(1475)), "INSCREVA-SE NO CANAL", 36, _contrast(primary), True)
        base._center(draw, (base._s(540), base._s(1530)), "E ATIVE AS NOTIFICAÇÕES", 25, _contrast(primary), True)

    _footer(draw, data, light)
    return image.convert("RGB")


def criar_poster(data: Dict[str, Any], output_path: str | os.PathLike[str]) -> str:
    numbers, _ = prepare_numbers(str(data.get("loteria") or ""), data.get("numeros") or data.get("descricao") or "")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    scene_image(data, "final", visible_count=len(numbers), seed=777).save(output, quality=95)
    return str(output)
