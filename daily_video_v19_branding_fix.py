from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw

import daily_video_v19 as base


RESULTS_DOMAIN_DISPLAY = "PORTALSIMONSPORTS.COM"
RESULTS_SECTION_DISPLAY = "SEÇÃO LOTERIAS CAIXA"
RESULTS_SPEECH = (
    "Para consultar mais resultados e detalhes de cada concurso, acesse "
    "Portal Simon Sports ponto com, seção Loterias Caixa. "
    "O link direto também está na descrição."
)

DEFAULT_THEME: Dict[str, Tuple[int, int, int]] = {
    "top": (6, 105, 173),
    "bottom": (0, 18, 44),
    "ball": (0, 119, 193),
    "outline": (180, 238, 255),
    "accent": (180, 238, 255),
}

# Paletas inspiradas nas cores predominantes das marcas das modalidades.
LOTTERY_THEMES: Dict[str, Dict[str, Tuple[int, int, int]]] = {
    "mega sena": {
        "top": (0, 151, 104), "bottom": (0, 45, 35),
        "ball": (0, 174, 119), "outline": (181, 255, 224), "accent": (190, 255, 226),
    },
    "lotofacil": {
        "top": (151, 0, 142), "bottom": (50, 0, 65),
        "ball": (178, 0, 161), "outline": (255, 193, 246), "accent": (255, 205, 248),
    },
    "quina": {
        "top": (62, 36, 168), "bottom": (17, 8, 65),
        "ball": (75, 45, 194), "outline": (213, 201, 255), "accent": (221, 212, 255),
    },
    "lotomania": {
        "top": (242, 112, 0), "bottom": (80, 27, 0),
        "ball": (255, 128, 0), "outline": (255, 225, 190), "accent": (255, 230, 198),
    },
    "timemania": {
        "top": (0, 151, 79), "bottom": (0, 54, 34),
        "ball": (0, 180, 94), "outline": (184, 255, 218), "accent": (196, 255, 224),
    },
    "dupla sena": {
        "top": (184, 24, 48), "bottom": (61, 0, 19),
        "ball": (205, 30, 57), "outline": (255, 202, 211), "accent": (255, 211, 218),
    },
    "dia de sorte": {
        "top": (196, 126, 22), "bottom": (76, 39, 0),
        "ball": (225, 147, 31), "outline": (255, 236, 191), "accent": (255, 239, 200),
    },
    "super sete": {
        "top": (105, 159, 38), "bottom": (35, 63, 12),
        "ball": (127, 184, 48), "outline": (230, 255, 190), "accent": (235, 255, 204),
    },
    "mais milionaria": {
        "top": (56, 52, 145), "bottom": (18, 16, 65),
        "ball": (77, 72, 174), "outline": (255, 222, 100), "accent": (255, 224, 105),
    },
    "loteria federal": {
        "top": (0, 92, 164), "bottom": (0, 28, 69),
        "ball": (0, 119, 193), "outline": (190, 237, 255), "accent": (195, 239, 255),
    },
}

_ACTIVE_THEME: Dict[str, Tuple[int, int, int]] = dict(DEFAULT_THEME)


def _key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = ascii_text.replace("+", " mais ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text).split())


def theme_for_lottery(value: Any) -> Dict[str, Tuple[int, int, int]]:
    key = _key(value)
    aliases = {
        "megasena": "mega sena",
        "mega sena": "mega sena",
        "lotofacil": "lotofacil",
        "quina": "quina",
        "lotomania": "lotomania",
        "timemania": "timemania",
        "duplasena": "dupla sena",
        "dupla sena": "dupla sena",
        "diadesorte": "dia de sorte",
        "dia de sorte": "dia de sorte",
        "supersete": "super sete",
        "super sete": "super sete",
        "maismilionaria": "mais milionaria",
        "mais milionaria": "mais milionaria",
        "loteriafederal": "loteria federal",
        "loteria federal": "loteria federal",
    }
    canonical = aliases.get(key.replace(" ", ""), aliases.get(key, key))
    return dict(LOTTERY_THEMES.get(canonical, DEFAULT_THEME))


def _base_result_image_branded(
    data: Dict[str, Any],
    size: Tuple[int, int],
    *,
    section: str = "",
) -> Tuple[Image.Image, ImageDraw.ImageDraw, int]:
    global _ACTIVE_THEME
    _ACTIVE_THEME = theme_for_lottery(data.get("loteria"))

    image = base._gradient(size, top=_ACTIVE_THEME["top"], bottom=_ACTIVE_THEME["bottom"])
    draw = ImageDraw.Draw(image, "RGBA")
    base._brand(draw, size)
    width, height = size
    horizontal = width > height
    lottery = base._normalize_name(data.get("loteria"))
    contest = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or "").strip()
    title_y = 215 if horizontal else 235
    title_font = base._fit_font(draw, lottery.upper(), width - 150, 66 if horizontal else 58, 30)
    draw.text((width / 2, title_y), lottery.upper(), font=title_font, fill="white", anchor="mm")

    subtitle = f"CONCURSO {contest}" if contest else "RESULTADO OFICIAL"
    if date:
        subtitle += f"  •  {date}"
    if section:
        subtitle += f"  •  {section}"
    draw.text(
        (width / 2, title_y + 72),
        subtitle,
        font=base._font(29 if horizontal else 27, True),
        fill=_ACTIVE_THEME["accent"],
        anchor="mm",
    )
    base._footer(draw, size)
    return image, draw, title_y + 125


def _number_grid_branded(
    draw: ImageDraw.ImageDraw,
    numbers: Sequence[str],
    size: Tuple[int, int],
    *,
    top_y: int,
    bottom_y: int,
) -> None:
    width, _height = size
    count = max(1, len(numbers))
    horizontal = width > size[1]
    if horizontal:
        columns = 10 if count > 15 else 8 if count > 8 else count
    else:
        columns = 5 if count > 10 else 4 if count > 6 else min(count, 3)
    rows = math.ceil(count / max(1, columns))
    usable_width = width - (180 if horizontal else 120)
    cell_width = usable_width / max(1, columns)
    cell_height = max(88, (bottom_y - top_y) / max(1, rows))
    radius = min(54 if horizontal else 66, int(cell_width * 0.34), int(cell_height * 0.36))
    number_font = base._font(max(24, int(radius * 0.78)), True)

    for index, number in enumerate(numbers):
        row = index // columns
        column = index % columns
        current_row_count = min(columns, count - row * columns)
        row_width = current_row_count * cell_width
        start_x = (width - row_width) / 2
        cx = start_x + (column + 0.5) * cell_width
        cy = top_y + (row + 0.5) * cell_height
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=(*_ACTIVE_THEME["ball"], 248),
            outline=_ACTIVE_THEME["outline"],
            width=4,
        )
        clean = str(number).strip()
        shown = clean.zfill(2) if clean.isdigit() and len(clean) < 2 else clean
        draw.text((cx, cy), shown, font=number_font, fill="white", anchor="mm")


def _closing_image_branded(results: Sequence[Dict[str, Any]], size: Tuple[int, int]) -> Image.Image:
    image = base._gradient(size, top=(8, 95, 165), bottom=(0, 16, 38))
    draw = ImageDraw.Draw(image, "RGBA")
    base._brand(draw, size)
    width, height = size
    horizontal = width > height
    y = height / 2 - (180 if horizontal else 255)

    draw.text(
        (width / 2, y),
        "MAIS RESULTADOS E DETALHES",
        font=base._fit_font(draw, "MAIS RESULTADOS E DETALHES", width - 150, 58 if horizontal else 48, 25),
        fill="white",
        anchor="mm",
    )
    draw.rounded_rectangle(
        (125, y + 105, width - 125, y + (260 if horizontal else 300)),
        radius=38,
        fill=(0, 119, 193, 245),
        outline=(180, 238, 255),
        width=4,
    )
    draw.text(
        (width / 2, y + (165 if horizontal else 180)),
        RESULTS_DOMAIN_DISPLAY,
        font=base._fit_font(draw, RESULTS_DOMAIN_DISPLAY, width - 310, 49 if horizontal else 42, 24),
        fill="white",
        anchor="mm",
    )
    draw.text(
        (width / 2, y + (225 if horizontal else 250)),
        RESULTS_SECTION_DISPLAY,
        font=base._fit_font(draw, RESULTS_SECTION_DISPLAY, width - 330, 34 if horizontal else 32, 20),
        fill=(255, 224, 105),
        anchor="mm",
    )
    draw.text(
        (width / 2, y + (335 if horizontal else 420)),
        "LINK DIRETO NA DESCRIÇÃO DO VÍDEO",
        font=base._fit_font(draw, "LINK DIRETO NA DESCRIÇÃO DO VÍDEO", width - 190, 31 if horizontal else 28, 18),
        fill=(180, 238, 255),
        anchor="mm",
    )
    draw.text(
        (width / 2, y + (420 if horizontal else 520)),
        "INSCREVA-SE • CURTA • COMENTE • COMPARTILHE",
        font=base._fit_font(draw, "INSCREVA-SE • CURTA • COMENTE • COMPARTILHE", width - 220, 33 if horizontal else 27, 17),
        fill="white",
        anchor="mm",
    )
    base._footer(draw, size)
    return image


def _build_full_branded(
    results: Sequence[Dict[str, Any]],
    output: Path,
    temp: Path,
    pair: Tuple[str, str],
) -> float:
    primary, secondary = pair
    scenes: List[base.Scene] = [(base._intro_image(results, (1920, 1080)), base.FULL_INTRO_DURATION)]
    segments: List[base.SpeechSegment] = [
        base.SpeechSegment(
            0.25,
            primary,
            "Portal Simon Sports, simplesmente o melhor. Confira os resultados das loterias de hoje.",
            1.0,
            base.FULL_RATE,
            "opening",
        )
    ]
    current = base.FULL_INTRO_DURATION
    total_result_scenes = sum(len(base._result_full_scenes(item)) for item in results)
    engagement_after = max(1, total_result_scenes // 2)
    scene_counter = 0

    for result_index, data in enumerate(results):
        voice = primary if result_index % 2 == 0 else secondary
        for image, scene_duration, speech in base._result_full_scenes(data):
            scenes.append((image, scene_duration))
            segments.append(
                base.SpeechSegment(current + 0.35, voice, speech, 1.0, base.FULL_RATE, "daily_result")
            )
            current += scene_duration
            scene_counter += 1
            if total_result_scenes >= 4 and scene_counter == engagement_after:
                scenes.append((base._engagement_image((1920, 1080)), base.FULL_ENGAGEMENT_DURATION))
                other = secondary if voice == primary else primary
                segments.append(
                    base.SpeechSegment(
                        current + 0.35,
                        other,
                        "Já conferiu os seus jogos? Deixe o seu like, conte nos comentários e compartilhe este boletim.",
                        1.0,
                        base.FULL_RATE,
                        "engagement",
                    )
                )
                current += base.FULL_ENGAGEMENT_DURATION

    closing_duration = 19.0
    scenes.append((_closing_image_branded(results, (1920, 1080)), closing_duration))
    segments.extend(
        [
            base.SpeechSegment(
                current + 0.35,
                secondary,
                RESULTS_SPEECH,
                1.0,
                base.FULL_RATE,
                "closing",
            ),
            base.SpeechSegment(
                current + 11.0,
                primary,
                "Curta, comente, compartilhe e inscreva-se no canal. Portal Simon Sports, simplesmente o melhor.",
                1.0,
                base.FULL_RATE,
                "closing",
            ),
        ]
    )
    duration = current + closing_duration
    music = temp / "daily_full_music.wav"
    audio = temp / "daily_full_audio.wav"
    contest_seed = base._date_key(results[0].get("data") if results else "")
    base.write_soundtrack(music, duration, "Resultados Diários", contest_seed, base.FULL_INTRO_DURATION, current)
    base.synthesize_custom_segments(
        results[0] if results else {},
        duration,
        segments,
        music,
        audio,
        primary_voice=primary,
    )
    render_dir = temp / "daily_full_render"
    render_dir.mkdir()
    base._write_concat_video(scenes, audio, output, duration, render_dir)
    return duration


def _build_short_branded(
    results: Sequence[Dict[str, Any]],
    output: Path,
    temp: Path,
    voice: str,
) -> float:
    if not results:
        raise RuntimeError("Nenhum resultado informado para o Short diário.")

    count = len(results)
    per_result = 24.0 if count == 1 else max(4.5, min(10.0, 50.0 / count))
    closing_duration = 8.0
    scenes: List[base.Scene] = []
    segments: List[base.SpeechSegment] = []
    current = 0.0

    for data in results:
        scenes.append((base._result_short_image(data), per_result))
        segments.append(
            base.SpeechSegment(
                current + 0.20,
                voice,
                base._short_speech(data),
                1.0,
                base.SHORT_RATE,
                "daily_short_result",
            )
        )
        current += per_result

    scenes.append((_closing_image_branded(results, (1080, 1920)), closing_duration))
    segments.append(
        base.SpeechSegment(
            current + 0.20,
            voice,
            "Mais resultados em Portal Simon Sports ponto com, seção Loterias Caixa. Link na descrição.",
            1.0,
            base.SHORT_RATE,
            "closing",
        )
    )
    duration = current + closing_duration
    if duration < 30.0 or duration > 60.0:
        raise RuntimeError(f"Short diário fora da faixa de 30 a 60 segundos: {duration:.1f}s")

    music = temp / "daily_short_music.wav"
    audio = temp / "daily_short_audio.wav"
    contest_seed = base._date_key(results[0].get("data"))
    base.write_soundtrack(music, duration, "Resultados Diários", contest_seed, 0.0, current)
    base.synthesize_custom_segments(
        results[0], duration, segments, music, audio, primary_voice=voice
    )
    render_dir = temp / "daily_short_render"
    render_dir.mkdir()
    base._write_concat_video(scenes, audio, output, duration, render_dir)
    return duration


def install_branding_fix() -> None:
    base._base_result_image = _base_result_image_branded
    base._number_grid = _number_grid_branded
    base._closing_image = _closing_image_branded
    base._build_full = _build_full_branded
    base._build_short = _build_short_branded


install_branding_fix()


__all__ = [
    "LOTTERY_THEMES",
    "RESULTS_DOMAIN_DISPLAY",
    "RESULTS_SECTION_DISPLAY",
    "RESULTS_SPEECH",
    "install_branding_fix",
    "theme_for_lottery",
]
