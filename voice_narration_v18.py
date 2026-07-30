from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import voice_narration_v17 as v17
from lottery_result_v18 import parse_lottery_result, special_speech


VOICE_FRANCISCA = v17.VOICE_FRANCISCA
VOICE_THALITA_MULTILINGUAL = v17.VOICE_THALITA_MULTILINGUAL
VOICE_ANTONIO = v17.VOICE_ANTONIO
VOICE_THALITA_NEURAL = v17.VOICE_THALITA_NEURAL
ALL_VOICES = v17.ALL_VOICES
SpeechSegment = v17.SpeechSegment

select_single_voice = v17.select_single_voice
select_presenter_pair = v17.select_presenter_pair
pair_label = v17.pair_label
voice_label = v17.voice_label
reveal_times_full = v17.reveal_times_full
reveal_times_short = v17.reveal_times_short
_BASE_BUILD_SEGMENTS = v17.build_segments
_BASE_DIALOGUE_MIX = v17.synthesize_dialogue_mix
_BASE_SINGLE_MIX = v17.synthesize_single_mix


def extract_numbers(data: Dict[str, Any]) -> List[str]:
    lottery = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    raw = data.get("numeros") or data.get("descricao") or data.get("Descrição") or ""
    return parse_lottery_result(lottery, raw).display_numbers


def _special_start(reveals: Sequence[float], compact: bool) -> float:
    last = reveals[-1] if reveals else (20.0 if compact else 108.0)
    if compact:
        return max(last + 0.75, 22.05)
    return max(last + 2.20, 114.90)


def build_segments(
    data: Dict[str, Any],
    duration: float,
    reveals: Iterable[float],
    *,
    compact: bool,
    primary_voice: str,
    secondary_voice: str | None = None,
) -> List[SpeechSegment]:
    reveal_list = list(reveals)
    lottery = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    raw = data.get("numeros") or data.get("descricao") or data.get("Descrição") or ""
    parts = parse_lottery_result(lottery, raw)

    normalized_data = dict(data)
    normalized_data["numeros"] = parts.display_numbers
    segments = _BASE_BUILD_SEGMENTS(
        normalized_data,
        duration,
        reveal_list,
        compact=compact,
        primary_voice=primary_voice,
        secondary_voice=secondary_voice,
    )

    text = special_speech(parts)
    if not text:
        return segments

    start = _special_start(reveal_list, compact)
    special_segment = SpeechSegment(
        start,
        primary_voice,
        text,
        1.03 if compact else 1.0,
        "+18%" if compact else "+4%",
        "special_result",
    )

    minimum_closing_start = start + (2.05 if compact else 6.20)
    adjusted: List[SpeechSegment] = []
    for segment in segments:
        if segment.role == "closing" and segment.start < minimum_closing_start:
            adjusted.append(replace(segment, start=minimum_closing_start))
        else:
            adjusted.append(segment)
    adjusted.append(special_segment)
    return sorted(adjusted, key=lambda item: item.start)


def _with_builder(callback, data, duration, reveals, music_path, output_path, **kwargs):
    original = v17.build_segments
    v17.build_segments = build_segments
    try:
        return callback(data, duration, list(reveals), music_path, output_path, **kwargs)
    finally:
        v17.build_segments = original


def synthesize_single_mix(
    data: Dict[str, Any],
    duration: float,
    reveals: Iterable[float],
    music_path,
    output_path,
    *,
    compact: bool,
    voice: str | None = None,
):
    return _with_builder(
        _BASE_SINGLE_MIX,
        data,
        duration,
        reveals,
        music_path,
        output_path,
        compact=compact,
        voice=voice,
    )


def synthesize_dialogue_mix(
    data: Dict[str, Any],
    duration: float,
    reveals: Iterable[float],
    music_path,
    output_path,
    *,
    pair: Tuple[str, str] | None = None,
):
    return _with_builder(
        _BASE_DIALOGUE_MIX,
        data,
        duration,
        reveals,
        music_path,
        output_path,
        pair=pair,
    )


def synthesize_custom_segments(
    data: Dict[str, Any],
    duration: float,
    segments: Sequence[SpeechSegment],
    music_path,
    output_path,
    *,
    primary_voice: str,
):
    import voice_narration_v15 as v15

    original_builder = v15.build_segments

    def custom_builder(_data, _duration, _reveals, compact=False, voice=None):
        return list(segments)

    v15.build_segments = custom_builder
    try:
        return v17._BASE_SYNTHESIZE(
            data,
            duration,
            [],
            music_path,
            output_path,
            compact=False,
            voice=primary_voice,
        )
    finally:
        v15.build_segments = original_builder


__all__ = [
    "ALL_VOICES", "SpeechSegment", "VOICE_ANTONIO", "VOICE_FRANCISCA",
    "VOICE_THALITA_MULTILINGUAL", "VOICE_THALITA_NEURAL", "build_segments",
    "extract_numbers", "pair_label", "reveal_times_full", "reveal_times_short",
    "select_presenter_pair", "select_single_voice", "synthesize_custom_segments",
    "synthesize_dialogue_mix", "synthesize_single_mix", "voice_label",
]
