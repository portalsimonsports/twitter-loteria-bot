from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

import daily_video_v19 as base
from lottery_result_v18 import parse_lottery_result


_ORIGINAL_RESULT_FULL_SCENES = base._result_full_scenes
_ORIGINAL_RESULT_SHORT_IMAGE = base._result_short_image
_ORIGINAL_SHORT_SPEECH = base._short_speech
_ORIGINAL_GERAR_PACOTE_DIARIO = base.gerar_pacote_diario


def _is_dupla_sena(data: Dict[str, Any]) -> bool:
    lottery = base._normalize_name(data.get("loteria"))
    parts = parse_lottery_result(lottery, base._raw_result(data))
    return bool(parts.second_draw_numbers)


def _spoken_numbers(numbers: Sequence[str]) -> str:
    return ", ".join(str(int(value)) if str(value).isdigit() else str(value) for value in numbers)


def _dupla_sena_speech(data: Dict[str, Any], draw_number: int | None = None) -> str:
    lottery = base._normalize_name(data.get("loteria"))
    contest = str(data.get("concurso") or "").strip()
    parts = parse_lottery_result(lottery, base._raw_result(data))
    first = _spoken_numbers(parts.main_numbers)
    second = _spoken_numbers(parts.second_draw_numbers)

    if draw_number == 1:
        return base._speech_normalize(
            f"Dupla Sena, concurso {contest}. Primeiro sorteio: {first}."
        )
    if draw_number == 2:
        return base._speech_normalize(
            f"Dupla Sena, concurso {contest}. Segundo sorteio: {second}."
        )
    return base._speech_normalize(
        f"Dupla Sena, concurso {contest}. Primeiro sorteio: {first}. "
        f"Segundo sorteio: {second}."
    )


def _dupla_sena_draw_image(
    data: Dict[str, Any],
    size: Tuple[int, int],
    draw_number: int,
) -> Any:
    lottery = base._normalize_name(data.get("loteria"))
    parts = parse_lottery_result(lottery, base._raw_result(data))
    numbers = parts.main_numbers if draw_number == 1 else parts.second_draw_numbers
    section = f"{draw_number}º SORTEIO"
    image, draw, content_top = base._base_result_image(data, size, section=section)
    width, height = size
    bottom = height - (170 if width > height else 270)
    base._number_grid(draw, numbers, size, top_y=content_top + 15, bottom_y=bottom)
    optional = base._optional_line(data)
    if optional:
        draw.text(
            (width / 2, height - (105 if width > height else 190)),
            optional,
            font=base._fit_font(draw, optional, width - 180, 25, 17),
            fill=(220, 245, 255),
            anchor="mm",
        )
    return image


def _dupla_sena_combined_image(data: Dict[str, Any], size: Tuple[int, int]) -> Any:
    lottery = base._normalize_name(data.get("loteria"))
    parts = parse_lottery_result(lottery, base._raw_result(data))
    image, draw, content_top = base._base_result_image(
        data,
        size,
        section="1º E 2º SORTEIOS",
    )
    width, height = size
    horizontal = width > height

    if horizontal:
        first_label_y = content_top + 20
        first_top = content_top + 60
        first_bottom = height // 2 - 10
        second_label_y = height // 2 + 20
        second_top = height // 2 + 60
        second_bottom = height - 150
    else:
        first_label_y = content_top + 45
        first_top = content_top + 95
        first_bottom = 940
        second_label_y = 1030
        second_top = 1080
        second_bottom = 1600

    label_font = base._font(32 if horizontal else 34, True)
    draw.text(
        (width / 2, first_label_y),
        "1º SORTEIO",
        font=label_font,
        fill=(255, 224, 105),
        anchor="mm",
    )
    base._number_grid(
        draw,
        parts.main_numbers,
        size,
        top_y=first_top,
        bottom_y=first_bottom,
    )
    draw.text(
        (width / 2, second_label_y),
        "2º SORTEIO",
        font=label_font,
        fill=(255, 224, 105),
        anchor="mm",
    )
    base._number_grid(
        draw,
        parts.second_draw_numbers,
        size,
        top_y=second_top,
        bottom_y=second_bottom,
    )

    optional = base._optional_line(data)
    if optional:
        draw.text(
            (width / 2, height - (100 if horizontal else 205)),
            optional,
            font=base._fit_font(draw, optional, width - 160, 25, 17),
            fill=(220, 245, 255),
            anchor="mm",
        )
    return image


def _result_full_scenes_fixed(data: Dict[str, Any]) -> List[Tuple[Any, float, str]]:
    if not _is_dupla_sena(data):
        return _ORIGINAL_RESULT_FULL_SCENES(data)

    size = (1920, 1080)
    output: List[Tuple[Any, float, str]] = []
    for draw_number in (1, 2):
        speech = _dupla_sena_speech(data, draw_number)
        output.append(
            (
                _dupla_sena_draw_image(data, size, draw_number),
                base._estimated_scene_duration(speech, 13.0, 22.0),
                speech,
            )
        )
    return output


def _result_short_image_fixed(data: Dict[str, Any]) -> Any:
    if _is_dupla_sena(data):
        return _dupla_sena_combined_image(data, (1080, 1920))
    return _ORIGINAL_RESULT_SHORT_IMAGE(data)


def _short_speech_fixed(data: Dict[str, Any]) -> str:
    if _is_dupla_sena(data):
        return _dupla_sena_speech(data)
    return _ORIGINAL_SHORT_SPEECH(data)


def _gerar_pacote_diario_sem_loteca(
    resultados: Sequence[Dict[str, Any]],
    *,
    output_dir="output",
    gerar_short: bool = True,
):
    loteca = [
        item for item in resultados
        if "loteca" in base._normalize_name(item.get("loteria")).lower()
    ]
    if loteca:
        raise RuntimeError(
            "A Loteca não pode entrar no vídeo diário consolidado; deve ser publicada separadamente."
        )
    return _ORIGINAL_GERAR_PACOTE_DIARIO(
        resultados,
        output_dir=output_dir,
        gerar_short=gerar_short,
    )


def install_dupla_sena_fix() -> None:
    base._result_full_scenes = _result_full_scenes_fixed
    base._result_short_image = _result_short_image_fixed
    base._short_speech = _short_speech_fixed
    base.gerar_pacote_diario = _gerar_pacote_diario_sem_loteca


install_dupla_sena_fix()


__all__ = ["install_dupla_sena_fix"]
