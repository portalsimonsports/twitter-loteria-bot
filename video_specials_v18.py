from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw

from lottery_result_v18 import ParsedLotteryResult, parse_lottery_result


def prepare_numbers(lottery: str, value: Any) -> Tuple[List[str], str]:
    parts = parse_lottery_result(lottery, value)
    return parts.display_numbers, parts.extra_display


def _safe_number_positions(loteria: str, numbers: Sequence[str]) -> List[Tuple[int, int, int]]:
    """Layout vertical 9:16 otimizado para Shorts, sem invadir UI lateral/inferior."""
    count = len(numbers)
    key = loteria.lower()

    if "dupla" in key and count >= 12:
        diameter = 108
        gap = 18
        start_x = (900 - (6 * diameter + 5 * gap)) // 2 + 30
        return [
            (start_x + col * (diameter + gap), y, diameter)
            for y in (700, 1015)
            for col in range(6)
        ]

    if count <= 4:
        columns = count
    elif count <= 8:
        columns = 4
    elif count <= 12:
        columns = 4
    else:
        columns = 5

    diameter = 158 if count <= 8 else 126 if count <= 12 else 105
    gap = 34 if count <= 8 else 26 if count <= 12 else 20
    vertical_gap = 55 if count <= 8 else 38

    rows = (count + columns - 1) // columns
    total_height = rows * diameter + (rows - 1) * vertical_gap
    start_y = 655 + max(0, (500 - total_height) // 2)

    positions: List[Tuple[int, int, int]] = []
    safe_width = 900
    left_margin = 30
    for index in range(count):
        row, col = divmod(index, columns)
        row_count = min(columns, count - row * columns)
        row_width = row_count * diameter + (row_count - 1) * gap
        start_x = left_margin + max(0, (safe_width - row_width) // 2)
        positions.append(
            (
                start_x + col * (diameter + gap),
                start_y + row * (diameter + vertical_gap),
                diameter,
            )
        )
    return positions


def _draw_title_safe(draw, loteria: str, concurso: str, date: str, v5, primary, light) -> None:
    base = v5.base
    title = loteria.upper()
    title_size = 74 if len(title) <= 14 else 62 if len(title) <= 20 else 50

    # Área segura: abaixo da barra superior do Shorts e antes das dezenas.
    base._center(
        draw,
        (base._s(470), base._s(390)),
        title,
        title_size,
        (255, 255, 255),
        True,
        3,
        (0, 0, 0, 170),
    )

    subtitle_parts = []
    if concurso:
        subtitle_parts.append(f"CONCURSO {concurso}")
    if date:
        subtitle_parts.append(date)
    subtitle = "  •  ".join(subtitle_parts)
    if subtitle:
        base._panel(draw, (110, 485, 830, 575), 28, (*primary, 238), (*light, 210), 2)
        base._center(draw, (base._s(470), base._s(530)), subtitle, 31, v5._contrast(primary), True)


def _draw_special_panel(draw, parts: ParsedLotteryResult, v5, primary, dark, light) -> None:
    base = v5.base

    # O painel especial fica dentro da área segura do Shorts, antes do bloco
    # inferior de título/canal/comentários do aplicativo.
    if parts.trevos:
        base._panel(draw, (90, 1195, 850, 1370), 40, (*primary, 242), (*light, 225), 3)
        base._center(draw, (base._s(470), base._s(1235)), "TREVOS DA SORTE", 29, v5._contrast(primary), True)
        values = list(parts.trevos[:2])
        positions = (385, 555) if len(values) == 2 else (470,)
        for x, value in zip(positions, values):
            draw.ellipse(
                (base._s(x - 56), base._s(1268), base._s(x + 56), base._s(1380)),
                fill=(*dark, 245),
                outline=(*light, 255),
                width=base._s(4),
            )
            base._center(draw, (base._s(x), base._s(1324)), value, 43, (255, 255, 255), True)
        return

    if parts.team or parts.lucky_month:
        label = "TIME DO CORAÇÃO" if parts.team else "MÊS DA SORTE"
        value = (parts.team or parts.lucky_month or "").upper()
        full_text = f"{label}: {value}"
        size = 41 if len(full_text) <= 28 else 34 if len(full_text) <= 38 else 28
        base._panel(draw, (65, 1205, 875, 1360), 38, (*primary, 244), (*light, 230), 3)
        base._center(draw, (base._s(470), base._s(1282)), full_text, size, v5._contrast(primary), True)


def render_reveal_background(data: Dict[str, Any], final: bool = False) -> Image.Image:
    import video_visual_v5 as v5
    import video_visual_v6 as v6

    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or data.get("data_sorteio") or "").strip()
    raw = data.get("numeros") or data.get("descricao") or data.get("Descrição") or ""
    parts = parse_lottery_result(loteria, raw)
    numbers = parts.display_numbers

    image, (primary, dark, light) = v6._new_scene(data, 227 if final else 211)
    draw = ImageDraw.Draw(image, "RGBA")
    v5._brand(draw, primary, dark, light, bool(data.get("previa", False)))
    _draw_title_safe(draw, loteria, concurso, date, v5, primary, light)

    # Removido o antigo texto "RESULTADO COMPLETO / NÚMEROS SORTEADOS" que
    # concorria visualmente com título, concurso e controles do Shorts.
    if "dupla-sena" in v5.base._slug(loteria) and len(numbers) >= 12:
        for label, y in (("1º SORTEIO", 640), ("2º SORTEIO", 955)):
            v5.base._panel(draw, (310, y, 630, y + 58), 22, (*primary, 235), (*light, 220), 2)
            v5.base._center(draw, (v5.base._s(470), v5.base._s(y + 29)), label, 25, v5._contrast(primary), True)

    if final and parts.has_special:
        _draw_special_panel(draw, parts, v5, primary, dark, light)

    # Rodapé acima da faixa inferior mais agressiva da UI do Shorts.
    v5.base._center(
        draw,
        (v5.base._s(470), v5.base._s(1445)),
        "FONTE: CAIXA LOTERIAS • CONTEÚDO INFORMATIVO",
        20,
        (240, 240, 240),
        True,
        1,
        (0, 0, 0, 150),
    )
    return image.convert("RGB")


def criar_poster(data: Dict[str, Any], output_path: str | Path) -> str:
    import video_visual_v6 as v6

    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    raw = data.get("numeros") or data.get("descricao") or data.get("Descrição") or ""
    numbers = parse_lottery_result(loteria, raw).display_numbers
    image = render_reveal_background(data, final=True).convert("RGBA")
    for number, position in zip(numbers, _safe_number_positions(loteria, numbers)):
        image = Image.alpha_composite(image, v6.render_ball_overlay(data, number, position, newest=False))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output, quality=95)
    return str(output)


def install_visual_support() -> None:
    import gerador_video_v7 as v7
    import gerador_video_v9 as v9
    import video_visual_v3 as v3
    import video_visual_v5 as v5
    import video_visual_v6 as v6

    v3.prepare_numbers = prepare_numbers
    v5.prepare_numbers = prepare_numbers
    v6.prepare_numbers = prepare_numbers
    v7.prepare_numbers = prepare_numbers

    # O layout aprovado passa a controlar também a posição das bolas.
    v6.number_positions = _safe_number_positions
    v6.render_reveal_background = render_reveal_background
    v7.render_reveal_background = render_reveal_background

    v6.criar_poster = criar_poster
    v7.criar_poster = criar_poster
    v9.criar_poster = criar_poster


__all__ = ["criar_poster", "install_visual_support", "prepare_numbers", "render_reveal_background"]
