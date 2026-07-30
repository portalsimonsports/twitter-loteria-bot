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


def _visual_settle_offset(reveals: List[float], compact: bool) -> float:
    """Calcula o atraso necessário para a fala coincidir com a dezena já visível.

    O vídeo-base inicia cada animação no instante de ``reveal``, mas a bola só se
    acomoda no quadro alguns instantes depois. A locução passa a começar nesse
    momento de acomodação, evitando que o áudio fique uma dezena à frente da tela.
    """
    if len(reveals) >= 2:
        smallest_gap = min(b - a for a, b in zip(reveals, reveals[1:]) if b > a)
    else:
        smallest_gap = 1.0 if compact else 3.2

    if compact:
        return min(0.58, max(0.34, smallest_gap * 0.58))
    return min(2.25, max(1.05, smallest_gap * 0.58))


def build_segments(
    data: Dict[str, Any],
    duration: float,
    reveals: Iterable[float],
    compact: bool = False,
    voice: str | None = None,
):
    reveal_list = list(reveals)
    segments = v15.build_segments(
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
    """Usa o encaixe seguro da V15 com a linha do tempo visual corrigida."""
    original_builder = v15.build_segments
    v15.build_segments = build_segments
    try:
        return v15.synthesize_narration_mix(
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
