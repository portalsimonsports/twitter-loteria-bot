from __future__ import annotations

import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

WIDTH = int(os.getenv("VIDEO_WIDTH", "1080"))
HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1920"))

PALETTES: Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]] = {
    "mega-sena": ((0, 108, 67), (0, 35, 28), (77, 255, 143)),
    "lotofacil": ((126, 31, 137), (41, 10, 56), (231, 144, 255)),
    "quina": ((42, 52, 151), (15, 20, 65), (145, 172, 255)),
    "lotomania": ((239, 100, 34), (91, 31, 12), (255, 202, 126)),
    "timemania": ((0, 134, 164), (0, 44, 60), (115, 229, 247)),
    "dupla-sena": ((157, 31, 55), (65, 10, 25), (255, 157, 174)),
    "dia-de-sorte": ((197, 139, 26), (70, 43, 7), (255, 225, 133)),
    "super-sete": ((58, 124, 57), (16, 52, 28), (153, 232, 151)),
    "mais-milionaria": ((47, 48, 57), (14, 15, 20), (221, 188, 88)),
    "federal": ((28, 92, 171), (9, 32, 72), (126, 195, 255)),
    "loteca": ((0, 115, 191), (0, 38, 78), (126, 213, 255)),
}


def _slug(value: str) -> str:
    text = (value or "").strip().lower()
    text = (
        text.replace("á", "a").replace("à", "a").replace("ã", "a").replace("â", "a")
        .replace("é", "e").replace("ê", "e").replace("í", "i")
        .replace("ó", "o").replace("ô", "o").replace("õ", "o")
        .replace("ú", "u").replace("ç", "c").replace("+", "mais-")
    )
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _palette(loteria: str, override: Any = None):
    if isinstance(override, (list, tuple)) and len(override) == 3:
        try:
            primary = tuple(max(0, min(255, int(x))) for x in override)
            secondary = tuple(max(0, int(x * 0.35)) for x in primary)
            return primary, secondary, (255, 255, 255)
        except Exception:
            pass
    key = _slug(loteria)
    for name, colors in PALETTES.items():
        if name in key or key in name:
            return colors
    return (25, 91, 135), (8, 30, 68), (136, 215, 255)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    real_size = max(10, round(size * WIDTH / 1080.0))
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=real_size)
    return ImageFont.load_default()


def _s(value: int | float) -> int:
    return round(value * WIDTH / 1080.0)


def _gradient(top: Tuple[int, int, int], bottom: Tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        t = y / max(1, HEIGHT - 1)
        t = t * t * (3 - 2 * t)
        color = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, WIDTH, y), fill=color)
    return image


def _cover(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    scale = max(WIDTH / image.width, HEIGHT / image.height)
    width, height = int(image.width * scale), int(image.height * scale)
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    left = max(0, (width - WIDTH) // 2)
    top = max(0, (height - HEIGHT) // 2)
    return image.crop((left, top, left + WIDTH, top + HEIGHT))


def _base_image(path: str, colors) -> Image.Image:
    primary, secondary, _ = colors
    base = _gradient(primary, secondary)
    if path and os.path.exists(path):
        try:
            photo = _cover(Image.open(path)).filter(ImageFilter.GaussianBlur(_s(3)))
            photo = ImageEnhance.Contrast(photo).enhance(1.18)
            photo = ImageEnhance.Brightness(photo).enhance(0.46)
            base = Image.blend(base, photo, 0.42)
        except Exception:
            pass
    return base.convert("RGBA")


def _split_raw(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = re.sub(r"^n[uú]meros?\s*:\s*", "", str(value or "").strip(), flags=re.I)
    parts = [part.strip() for part in re.split(r"[,;|\n]+", text) if part.strip()]
    if len(parts) <= 1:
        numeric_tokens = re.findall(r"(?<!\d)\d{1,6}(?!\d)", text)
        if len(numeric_tokens) > 1:
            return numeric_tokens
    return parts


def prepare_numbers(loteria: str, value: Any) -> Tuple[List[str], str]:
    raw = _split_raw(value)
    key = _slug(loteria)
    if "loteca" in key:
        return [], "14 JOGOS COM PLACARES NO PORTAL"

    numeric: List[str] = []
    extras: List[str] = []
    for token in raw:
        cleaned = token.strip().replace("+", "")
        if re.fullmatch(r"\d{1,6}", cleaned):
            numeric.append(cleaned.zfill(2) if len(cleaned) <= 2 else cleaned)
        elif token not in {"-", "+", "x", "X"}:
            extras.append(token)

    if numeric:
        limits = {
            "timemania": 7,
            "dia-de-sorte": 7,
            "super-sete": 7,
            "mais-milionaria": 8,
            "dupla-sena": 12,
            "lotomania": 20,
        }
        limit = 20
        for name, amount in limits.items():
            if name in key:
                limit = amount
                break
        return numeric[:limit], " • ".join(extras[:2])

    return raw[:20], ""


def _center(draw: ImageDraw.ImageDraw, xy, text: str, size: int, fill, bold=True, stroke=0, stroke_fill=(0, 0, 0, 150)):
    draw.text(xy, text, font=_font(size, bold), fill=fill, anchor="mm", stroke_width=_s(stroke), stroke_fill=stroke_fill)


def _panel(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(tuple(_s(value) for value in box), radius=_s(radius), fill=fill, outline=outline, width=max(1, _s(width)))


def _decorate(image: Image.Image, accent: Tuple[int, int, int], seed: int) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    center = (WIDTH // 2, round(HEIGHT * 0.52))
    for index in range(18):
        angle = -2.75 + index * 0.31
        length = _s(520 + (index % 5) * 70)
        x2 = center[0] + int(math.cos(angle) * length)
        y2 = center[1] + int(math.sin(angle) * length)
        draw.line((center[0], center[1], x2, y2), fill=(*accent, 28 + (index % 3) * 12), width=max(1, _s(3)))

    value = (seed * 1103515245 + 12345) & 0x7FFFFFFF
    for _ in range(110):
        value = (value * 1103515245 + 12345) & 0x7FFFFFFF
        x = value % WIDTH
        value = (value * 1103515245 + 12345) & 0x7FFFFFFF
        y = value % HEIGHT
        radius = _s(1 + value % 5)
        alpha = 35 + value % 145
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(*accent, alpha))

    for index in range(4):
        margin_x = _s(120 + index * 85)
        y1 = _s(1180 + index * 35)
        y2 = _s(1390 - index * 15)
        draw.ellipse((margin_x, y1, WIDTH-margin_x, y2), outline=(*accent, 90-index*14), width=max(1, _s(5-index)))


def _brand(draw: ImageDraw.ImageDraw, accent, secondary, preview: bool) -> None:
    _panel(draw, (46, 38, 1034, 160), 35, (3, 10, 18, 220), (255, 255, 255, 42), 2)
    draw.ellipse((_s(76), _s(67), _s(146), _s(137)), fill=(*accent, 255))
    _center(draw, (_s(111), _s(102)), "S", 34, secondary, True)
    draw.text((_s(172), _s(65)), "PORTAL", font=_font(25, True), fill=(220, 255, 232, 240))
    draw.text((_s(172), _s(95)), "SIMONSPORTS", font=_font(41, True), fill=(255, 255, 255, 255))
    draw.text((_s(995), _s(103)), "RESULTADOS", font=_font(23, True), fill=(*accent, 255), anchor="rm")
    if preview:
        _panel(draw, (750, 184, 1032, 247), 22, (244, 188, 35, 245))
        _center(draw, (_s(891), _s(215)), "PRÉVIA DE APROVAÇÃO", 19, (24, 22, 14), True)


def _draw_title(draw: ImageDraw.ImageDraw, loteria: str, concurso: str, data: str, accent, y: int = 325) -> None:
    title_size = 86 if len(loteria) <= 13 else 68 if len(loteria) <= 20 else 54
    _center(draw, (_s(540), _s(y)), loteria.upper(), title_size, (255, 255, 255), True, 2, (0, 0, 0, 170))
    meta = "  •  ".join(part for part in [f"CONCURSO {concurso}" if concurso else "", data] if part) or "RESULTADO OFICIAL"
    _center(draw, (_s(540), _s(y + 92)), meta, 31, accent, True)


def _number_layout(count: int) -> Tuple[int, int, int, int]:
    if count <= 6:
        return count, 1, 132, 34
    if count <= 10:
        return math.ceil(count / 2), 2, 116, 30
    if count <= 15:
        return 5, 3, 103, 25
    return 5, math.ceil(count / 5), 90, 22


def _draw_ball(draw: ImageDraw.ImageDraw, x: int, y: int, diameter: int, number: str, shown: bool, is_new: bool, accent, secondary) -> None:
    box = tuple(_s(value) for value in (x, y, x + diameter, y + diameter))
    if shown:
        glow = _s(17 if is_new else 8)
        draw.ellipse((box[0]-glow, box[1]-glow, box[2]+glow, box[3]+glow), fill=(*accent, 58 if is_new else 24))
        draw.ellipse(box, fill=(250, 253, 255, 255), outline=(*accent, 255), width=max(3, _s(7 if is_new else 4)))
        highlight = _s(max(8, diameter * 0.12))
        draw.ellipse((box[0]+highlight, box[1]+highlight, box[0]+highlight*3, box[1]+highlight*2), fill=(255, 255, 255, 150))
        font_size = 54 if diameter >= 116 else 43 if diameter >= 100 else 34
        if len(number) > 3:
            font_size = max(20, round(font_size * 0.62))
        _center(draw, ((box[0]+box[2])//2, (box[1]+box[3])//2 + _s(2)), number, font_size, secondary, True)
    else:
        draw.ellipse(box, fill=(4, 12, 20, 90), outline=(*accent, 82), width=max(2, _s(3)))
        _center(draw, ((box[0]+box[2])//2, (box[1]+box[3])//2), "?", 39, (*accent, 95), True)


def _draw_numbers(draw: ImageDraw.ImageDraw, numbers: Sequence[str], visible_count: int, accent, secondary, top_y: int = 590) -> None:
    count = max(1, len(numbers))
    columns, rows, diameter, gap = _number_layout(count)
    vertical_gap = 28 if rows <= 2 else 22
    total_height = rows * diameter + (rows - 1) * vertical_gap
    start_y = top_y + max(0, (690 - total_height) // 2)
    new_group = max(1, math.ceil(count / 6))

    for index in range(count):
        row = index // columns
        column = index % columns
        row_count = min(columns, count - row * columns)
        row_width = row_count * diameter + (row_count - 1) * gap
        start_x = (1080 - row_width) // 2
        x = start_x + column * (diameter + gap)
        y = start_y + row * (diameter + vertical_gap)
        shown = index < visible_count
        is_new = shown and index >= max(0, visible_count - new_group)
        _draw_ball(draw, x, y, diameter, numbers[index], shown, is_new, accent, secondary)


def _draw_dupla_sena(draw: ImageDraw.ImageDraw, numbers: Sequence[str], visible_count: int, accent, secondary) -> None:
    groups = [("1º SORTEIO", list(numbers[:6]), 600), ("2º SORTEIO", list(numbers[6:12]), 985)]
    for group_index, (label, group_numbers, label_y) in enumerate(groups):
        _panel(draw, (345, label_y, 735, label_y + 64), 24, (3, 16, 24, 215), (*accent, 170), 2)
        _center(draw, (_s(540), _s(label_y + 32)), label, 28, accent, True)
        start_y = label_y + 98
        diameter = 118
        gap = 28
        row_width = len(group_numbers) * diameter + max(0, len(group_numbers) - 1) * gap
        start_x = (1080 - row_width) // 2
        group_visible = max(0, min(6, visible_count - group_index * 6))
        for index, number in enumerate(group_numbers):
            shown = index < group_visible
            is_new = shown and index == group_visible - 1
            _draw_ball(draw, start_x + index * (diameter + gap), start_y, diameter, number, shown, is_new, accent, secondary)


def _official_footer(draw: ImageDraw.ImageDraw, data: Dict[str, Any], accent) -> None:
    updated = str(data.get("atualizado_em") or "").strip()
    if not updated:
        try:
            updated = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y às %H:%M")
        except Exception:
            updated = datetime.now().strftime("%d/%m/%Y às %H:%M")
    _center(draw, (_s(540), _s(1805)), f"FONTE: CAIXA LOTERIAS  •  ATUALIZADO EM {updated}", 18, (*accent, 225), True)
    _center(draw, (_s(540), _s(1850)), "CONTEÚDO INFORMATIVO • RESULTADO OFICIAL", 20, (255, 255, 255, 178), False)


def scene_image(data: Dict[str, Any], scene: str, visible_count: int = 0, seed: int = 1) -> Image.Image:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or data.get("data_sorteio") or "").strip()
    prize = str(data.get("premio") or data.get("estimativa") or "").strip()
    url = str(data.get("url") or "https://www.portalsimonsports.com/").strip()
    image_path = str(data.get("imagem_path") or "").strip()
    preview = bool(data.get("previa", False))
    numbers, extra = prepare_numbers(loteria, data.get("numeros") or data.get("descricao") or "")
    key = _slug(loteria)
    primary, secondary, accent = _palette(loteria, data.get("cor_fundo_rgb"))

    image = _base_image(image_path, (primary, secondary, accent))
    image = Image.alpha_composite(image, Image.new("RGBA", image.size, (0, 0, 0, 38)))
    _decorate(image, accent, seed)
    draw = ImageDraw.Draw(image, "RGBA")
    _brand(draw, accent, secondary, preview)

    if scene == "intro":
        _center(draw, (_s(540), _s(420)), loteria.upper(), 110 if len(loteria) <= 13 else 78, (255, 255, 255), True, 3, (0, 0, 0, 180))
        if concurso:
            _panel(draw, (255, 565, 825, 653), 30, (*accent, 238), (255, 255, 255, 90), 2)
            _center(draw, (_s(540), _s(609)), f"CONCURSO {concurso}", 39, secondary, True)
        _center(draw, (_s(540), _s(785)), "RESULTADO OFICIAL", 42, (245, 255, 248), True)
        _center(draw, (_s(540), _s(895)), "CONFIRA AGORA", 62, accent, True, 2, (0, 0, 0, 165))
        if date:
            _center(draw, (_s(540), _s(1000)), f"SORTEIO DE {date}", 29, (235, 255, 242), True)
        _panel(draw, (150, 1440, 930, 1570), 42, (3, 15, 22, 210), (*accent, 155), 2)
        _center(draw, (_s(540), _s(1505)), "NÚMEROS EM SEGUIDA", 39, (255, 255, 255), True)

    elif scene == "reveal":
        _draw_title(draw, loteria, concurso, date, accent)
        _center(draw, (_s(540), _s(510)), "RESULTADO OFICIAL • NÚMEROS SORTEADOS", 29, (235, 255, 242), True)
        if numbers:
            if "dupla-sena" in key and len(numbers) >= 12:
                _draw_dupla_sena(draw, numbers, visible_count, accent, secondary)
            else:
                _draw_numbers(draw, numbers, visible_count, accent, secondary)
            _panel(draw, (148, 1485, 932, 1598), 38, (3, 18, 24, 215), (*accent, 145), 2)
            _center(draw, (_s(540), _s(1540)), f"{visible_count} DE {len(numbers)} REVELADOS", 31, accent, True)
        else:
            _center(draw, (_s(540), _s(760)), "14 JOGOS", 105, accent, True, 3, (0, 0, 0, 170))
            _center(draw, (_s(540), _s(900)), "PLACARES E RESULTADOS", 47, (255, 255, 255), True)
            _center(draw, (_s(540), _s(980)), extra or "CONFIRA NO PORTAL", 31, accent, True)

    elif scene == "final":
        _draw_title(draw, loteria, concurso, date, accent)
        _center(draw, (_s(540), _s(505)), "RESULTADO COMPLETO", 38, (255, 255, 255), True)
        if numbers:
            if "dupla-sena" in key and len(numbers) >= 12:
                _draw_dupla_sena(draw, numbers, len(numbers), accent, secondary)
            else:
                _draw_numbers(draw, numbers, len(numbers), accent, secondary)
        else:
            _center(draw, (_s(540), _s(820)), "14 JOGOS", 102, accent, True)
            _center(draw, (_s(540), _s(940)), "RESULTADO COMPLETO NO PORTAL", 38, (255, 255, 255), True)
        if extra:
            _center(draw, (_s(540), _s(1395)), extra.upper(), 25, (236, 255, 242), True)
        if prize:
            _panel(draw, (110, 1460, 970, 1628), 42, (*accent, 225), (255, 255, 255, 95), 2)
            _center(draw, (_s(540), _s(1505)), "PRÓXIMO PRÊMIO ESTIMADO", 24, secondary, True)
            _center(draw, (_s(540), _s(1572)), prize, 51, secondary, True)

    else:
        _center(draw, (_s(540), _s(350)), "RESULTADO COMPLETO", 68, (255, 255, 255), True, 2, (0, 0, 0, 160))
        _center(draw, (_s(540), _s(500)), "PORTAL", 78, accent, True, 3, (0, 0, 0, 180))
        _center(draw, (_s(540), _s(605)), "SIMONSPORTS", 74, (255, 255, 255), True, 2, (0, 0, 0, 160))
        _panel(draw, (160, 730, 920, 855), 42, (*accent, 225), (255, 255, 255, 85), 2)
        _center(draw, (_s(540), _s(792)), "LINK NA DESCRIÇÃO", 42, secondary, True)
        domain = re.sub(r"^https?://", "", url).split("/")[0] or "www.portalsimonsports.com"
        _center(draw, (_s(540), _s(925)), domain, 31, (235, 255, 242), True)
        labels = [("RESULTADOS", "ATUALIZADOS"), ("FONTE", "OFICIAL"), ("TODAS AS", "LOTERIAS")]
        for index, (line1, line2) in enumerate(labels):
            center_x = 220 + index * 320
            draw.ellipse((_s(center_x-54), _s(1080), _s(center_x+54), _s(1188)), fill=(3, 20, 25, 220), outline=(*accent, 175), width=_s(3))
            _center(draw, (_s(center_x), _s(1134)), "✓", 44, accent, True)
            _center(draw, (_s(center_x), _s(1245)), line1, 20, (255, 255, 255), True)
            _center(draw, (_s(center_x), _s(1278)), line2, 20, accent, True)
        _panel(draw, (150, 1430, 930, 1580), 42, (3, 16, 24, 225), (*accent, 175), 2)
        _center(draw, (_s(540), _s(1475)), "INSCREVA-SE NO CANAL", 36, (255, 255, 255), True)
        _center(draw, (_s(540), _s(1530)), "E ATIVE AS NOTIFICAÇÕES", 25, accent, True)

    _official_footer(draw, data, accent)
    return image.convert("RGB")


def criar_poster(data: Dict[str, Any], output_path: str | os.PathLike[str]) -> str:
    numbers, _ = prepare_numbers(str(data.get("loteria") or ""), data.get("numeros") or data.get("descricao") or "")
    image = scene_image(data, "final", visible_count=len(numbers), seed=777)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, quality=95)
    return str(output)
