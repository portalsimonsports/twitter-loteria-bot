from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw

from lottery_result_v18 import ParsedLotteryResult, parse_lottery_result


def prepare_numbers(lottery: str, value: Any) -> Tuple[List[str], str]:
    parts = parse_lottery_result(lottery, value)
    return parts.display_numbers, parts.extra_display


def _draw_special_panel(draw, parts: ParsedLotteryResult, v5, primary, dark, light) -> None:
    base = v5.base
    if parts.trevos:
        base._panel(draw, (205, 1360, 875, 1588), 42, (*dark, 230), (*light, 210), 3)
        base._center(draw, (base._s(540), base._s(1410)), "TREVOS DA SORTE", 31, light, True)
        values = list(parts.trevos[:2])
        positions = (435, 645) if len(values) == 2 else (540,)
        for x, value in zip(positions, values):
            draw.ellipse(
                (base._s(x - 68), base._s(1450), base._s(x + 68), base._s(1586)),
                fill=(*primary, 245),
                outline=(*light, 255),
                width=base._s(5),
            )
            base._center(draw, (base._s(x), base._s(1518)), value, 52, v5._contrast(primary), True)
        return

    if parts.team or parts.lucky_month:
        label = "TIME DO CORAÇÃO" if parts.team else "MÊS DA SORTE"
        value = parts.team or parts.lucky_month
        base._panel(draw, (120, 1380, 960, 1585), 42, (*dark, 232), (*light, 205), 3)
        base._center(draw, (base._s(540), base._s(1432)), label, 29, light, True)
        size = 45 if len(value) <= 22 else 36 if len(value) <= 32 else 29
        base._center(draw, (base._s(540), base._s(1515)), value.upper(), size, (255, 255, 255), True)


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
    v5._title(draw, loteria, concurso, date, primary, light)

    heading = "RESULTADO COMPLETO" if final else "NÚMEROS SORTEADOS"
    v5.base._center(
        draw,
        (v5.base._s(540), v5.base._s(520)),
        heading,
        36 if final else 31,
        (245, 255, 249),
        True,
    )

    if "dupla-sena" in v5.base._slug(loteria) and len(numbers) >= 12:
        for label, y in (("1º SORTEIO", 610), ("2º SORTEIO", 1010)):
            v5.base._panel(draw, (340, y, 740, y + 66), 25, (*primary, 235), (*light, 220), 2)
            v5.base._center(draw, (v5.base._s(540), v5.base._s(y + 33)), label, 29, v5._contrast(primary), True)

    if final and parts.has_special:
        _draw_special_panel(draw, parts, v5, primary, dark, light)

    v5._footer(draw, data, light)
    return image.convert("RGB")


def criar_poster(data: Dict[str, Any], output_path: str | Path) -> str:
    import video_visual_v6 as v6

    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    raw = data.get("numeros") or data.get("descricao") or data.get("Descrição") or ""
    numbers = parse_lottery_result(loteria, raw).display_numbers
    image = render_reveal_background(data, final=True).convert("RGBA")
    for number, position in zip(numbers, v6.number_positions(loteria, numbers)):
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

    v6.render_reveal_background = render_reveal_background
    v7.render_reveal_background = render_reveal_background

    v6.criar_poster = criar_poster
    v7.criar_poster = criar_poster
    v9.criar_poster = criar_poster


__all__ = ["criar_poster", "install_visual_support", "prepare_numbers", "render_reveal_background"]
