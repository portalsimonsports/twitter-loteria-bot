from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

import video_visual_v5 as v5

WIDTH = v5.WIDTH
HEIGHT = v5.HEIGHT
prepare_numbers = v5.prepare_numbers


def _new_scene(data: Dict[str, Any], seed: int):
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    colors = v5._palette(loteria, data.get("cor_fundo_rgb"))
    image = v5._base_image(str(data.get("imagem_path") or "").strip(), colors)
    image = Image.alpha_composite(image, Image.new("RGBA", image.size, (0, 0, 0, 10)))
    v5._decorate(image, colors[0], colors[2], seed)
    return image, colors


def render_intro(data: Dict[str, Any]) -> Image.Image:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or data.get("data_sorteio") or "").strip()
    image, (primary, dark, light) = _new_scene(data, 101)
    draw = ImageDraw.Draw(image, "RGBA")
    v5._brand(draw, primary, dark, light, bool(data.get("previa", False)))
    v5._center(draw, (v5._s(540), v5._s(455)), loteria.upper(), 112 if len(loteria) <= 13 else 80, (255, 255, 255), True, 3, (0, 0, 0, 175))
    if concurso:
        v5._panel(draw, (255, 610, 825, 704), 30, (*primary, 242), (*light, 215), 2)
        v5._center(draw, (v5._s(540), v5._s(657)), f"CONCURSO {concurso}", 41, v5._contrast(primary), True)
    v5._center(draw, (v5._s(540), v5._s(875)), "RESULTADO OFICIAL", 47, (250, 255, 252), True)
    v5._center(draw, (v5._s(540), v5._s(1005)), "APRESENTAÇÃO DOS NÚMEROS", 45, light, True, 2, (0, 0, 0, 150))
    if date:
        v5._center(draw, (v5._s(540), v5._s(1120)), f"SORTEIO DE {date}", 31, (242, 255, 247), True)
    draw.rounded_rectangle((v5._s(215), v5._s(1350), v5._s(865), v5._s(1362)), radius=v5._s(6), fill=(*primary, 225))
    v5._footer(draw, data, light)
    return image.convert("RGB")


def number_positions(loteria: str, numbers: Sequence[str]) -> List[Tuple[int, int, int]]:
    key = v5._slug(loteria)
    count = len(numbers)
    if "dupla-sena" in key and count >= 12:
        diameter, gap = 118, 28
        start_x = (1080 - (6 * diameter + 5 * gap)) // 2
        return [(start_x + col * (diameter + gap), y, diameter) for y in (715, 1115) for col in range(6)]
    columns, rows, diameter, gap = v5._number_layout(count)
    vertical_gap = 28 if rows <= 2 else 22
    total_height = rows * diameter + (rows - 1) * vertical_gap
    start_y = 600 + max(0, (700 - total_height) // 2)
    positions: List[Tuple[int, int, int]] = []
    for index in range(count):
        row, col = divmod(index, columns)
        row_count = min(columns, count - row * columns)
        row_width = row_count * diameter + (row_count - 1) * gap
        start_x = (1080 - row_width) // 2
        positions.append((start_x + col * (diameter + gap), start_y + row * (diameter + vertical_gap), diameter))
    return positions


def render_reveal_background(data: Dict[str, Any], final: bool = False) -> Image.Image:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or data.get("data_sorteio") or "").strip()
    numbers, _ = prepare_numbers(loteria, data.get("numeros") or data.get("descricao") or "")
    image, (primary, dark, light) = _new_scene(data, 227 if final else 211)
    draw = ImageDraw.Draw(image, "RGBA")
    v5._brand(draw, primary, dark, light, bool(data.get("previa", False)))
    v5._title(draw, loteria, concurso, date, primary, light)
    v5._center(draw, (v5._s(540), v5._s(520)), "RESULTADO COMPLETO" if final else "NÚMEROS SORTEADOS", 36 if final else 31, (245, 255, 249), True)
    if "dupla-sena" in v5._slug(loteria) and len(numbers) >= 12:
        for label, y in (("1º SORTEIO", 610), ("2º SORTEIO", 1010)):
            v5._panel(draw, (340, y, 740, y + 66), 25, (*primary, 235), (*light, 220), 2)
            v5._center(draw, (v5._s(540), v5._s(y + 33)), label, 29, v5._contrast(primary), True)
    v5._footer(draw, data, light)
    return image.convert("RGB")


def render_cta(data: Dict[str, Any]) -> Image.Image:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    url = str(data.get("url") or "https://www.portalsimonsports.com/").strip()
    image, (primary, dark, light) = _new_scene(data, 333)
    draw = ImageDraw.Draw(image, "RGBA")
    v5._brand(draw, primary, dark, light, bool(data.get("previa", False)))
    v5._center(draw, (v5._s(540), v5._s(365)), loteria.upper(), 75 if len(loteria) <= 16 else 58, light, True, 2, (0, 0, 0, 160))
    v5._center(draw, (v5._s(540), v5._s(520)), "RESULTADO COMPLETO", 68, (255, 255, 255), True, 2, (0, 0, 0, 160))
    v5._panel(draw, (155, 720, 925, 855), 42, (*primary, 235), (*light, 205), 2)
    v5._center(draw, (v5._s(540), v5._s(787)), "LINK NA DESCRIÇÃO", 43, v5._contrast(primary), True)
    domain = re.sub(r"^https?://", "", url).split("/")[0] or "www.portalsimonsports.com"
    v5._center(draw, (v5._s(540), v5._s(945)), domain, 32, (245, 255, 249), True)
    labels = (("RESULTADOS", "ATUALIZADOS"), ("FONTE", "OFICIAL"), ("TODAS AS", "LOTERIAS"))
    for index, (line1, line2) in enumerate(labels):
        cx = 220 + index * 320
        draw.ellipse((v5._s(cx-56), v5._s(1080), v5._s(cx+56), v5._s(1192)), fill=(*dark, 225), outline=(*light, 205), width=v5._s(3))
        v5._center(draw, (v5._s(cx), v5._s(1136)), "✓", 45, light, True)
        v5._center(draw, (v5._s(cx), v5._s(1250)), line1, 20, (255, 255, 255), True)
        v5._center(draw, (v5._s(cx), v5._s(1284)), line2, 20, light, True)
    v5._panel(draw, (150, 1430, 930, 1585), 42, (*primary, 225), (*light, 195), 2)
    v5._center(draw, (v5._s(540), v5._s(1478)), "INSCREVA-SE NO CANAL", 36, v5._contrast(primary), True)
    v5._center(draw, (v5._s(540), v5._s(1534)), "E ATIVE AS NOTIFICAÇÕES", 25, v5._contrast(primary), True)
    v5._footer(draw, data, light)
    return image.convert("RGB")


def render_ball_overlay(data: Dict[str, Any], number: str, position: Tuple[int, int, int], newest: bool = True) -> Image.Image:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    primary, dark, light = v5._palette(loteria, data.get("cor_fundo_rgb"))
    x, y, diameter = position
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    v5._ball(draw, x, y, diameter, number, True, newest, primary, dark, light)
    return image


def criar_poster(data: Dict[str, Any], output_path: str | Path) -> str:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    numbers, _ = prepare_numbers(loteria, data.get("numeros") or data.get("descricao") or "")
    image = render_reveal_background(data, final=True).convert("RGBA")
    for number, position in zip(numbers, number_positions(loteria, numbers)):
        image = Image.alpha_composite(image, render_ball_overlay(data, number, position, newest=False))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output, quality=95)
    return str(output)
