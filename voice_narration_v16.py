from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Iterable, List

import voice_narration_v15 as v15


VOICE_ANTONIO = v15.VOICE_ANTONIO
VOICE_FRANCISCA = v15.VOICE_FRANCISCA
VOICE_THALITA = v15.VOICE_THALITA
extract_numbers = v15.extract_numbers
reveal_times_full = v15.reveal_times_full
reveal_times_short = v15.reveal_times_short
select_voice = v15.select_voice
voice_label = v15.voice_label

# Referências imutáveis às implementações originais da V15. Elas impedem que o
# encaixe temporário abaixo faça build_segments chamar a si própria em recursão.
_BASE_BUILD_SEGMENTS = v15.build_segments
_BASE_SYNTHESIZE_NARRATION_MIX = v15.synthesize_narration_mix


def _visual_settle_offset(reveals: List[float], compact: bool) -> float:
    """Atrasa a fala até a dezena já ter aparecido visualmente.

    O instante ``reveal`` marca o começo da animação da bola. A voz não deve
    anunciar o número antes disso; ela começa quando a bola já está claramente
    visível, eliminando o efeito em que a fala ocorre e a dezena só aparece depois.
    """
    positive_gaps = [b - a for a, b in zip(reveals, reveals[1:]) if b > a]
    if positive_gaps:
        smallest_gap = min(positive_gaps)
    else:
        smallest_gap = 1.0 if compact else 3.2

    if compact:
        return min(0.62, max(0.38, smallest_gap * 0.62))
    return min(2.35, max(1.15, smallest_gap * 0.62))


def build_segments(
    data: Dict[str, Any],
    duration: float,
    reveals: Iterable[float],
    compact: bool = False,
    voice: str | None = None,
):
    reveal_list = list(reveals)
    segments = _BASE_BUILD_SEGMENTS(
        data,
        duration,
        reveal_list,
        compact=compact,
        voice=voice,
    )
    offset = _visual_settle_offset(reveal_list, compact)

    adjusted = []
    for segment in segments:
        if segment.role == "number":
            adjusted.append(replace(segment, start=segment.start + offset))
        else:
            adjusted.append(segment)
    return sorted(adjusted, key=lambda item: item.start)


def synthesize_narration_mix(
    data: Dict[str, Any],
    duration: float,
    reveals: Iterable[float],
    music_path,
    output_path,
    *,
    compact: bool = False,
    voice: str | None = None,
):
    """Mantém o encaixe seguro da V15 com a fala depois da entrada visual."""
    original_builder = v15.build_segments
    v15.build_segments = build_segments
    try:
        return _BASE_SYNTHESIZE_NARRATION_MIX(
            data,
            duration,
            list(reveals),
            music_path,
            output_path,
            compact=compact,
            voice=voice,
        )
    finally:
        v15.build_segments = original_builder


__all__ = [
    "VOICE_ANTONIO",
    "VOICE_FRANCISCA",
    "VOICE_THALITA",
    "build_segments",
    "extract_numbers",
    "reveal_times_full",
    "reveal_times_short",
    "select_voice",
    "synthesize_narration_mix",
    "voice_label",
]
