from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence

import daily_video_v19 as base


def _build_short_fixed(
    results: Sequence[Dict[str, Any]],
    output: Path,
    temp: Path,
    voice: str,
) -> float:
    if not results:
        raise RuntimeError("Nenhum resultado informado para o Short diário.")

    count = len(results)
    if count == 1:
        per_result = 24.0
    else:
        per_result = max(6.0, min(12.0, 48.0 / count))

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

    scenes.append((base._closing_image(results, (1080, 1920)), base.SHORT_CLOSING_DURATION))
    segments.append(
        base.SpeechSegment(
            current + 0.20,
            voice,
            "Resultados completos no canal Simon Sports. Inscreva-se e acompanhe os próximos sorteios.",
            1.0,
            base.SHORT_RATE,
            "closing",
        )
    )

    duration = current + base.SHORT_CLOSING_DURATION
    if duration < 30.0 or duration > 60.0:
        raise RuntimeError(f"Short diário fora da faixa de 30 a 60 segundos: {duration:.1f}s")

    music = temp / "daily_short_music.wav"
    audio = temp / "daily_short_audio.wav"
    contest_seed = base._date_key(results[0].get("data"))
    base.write_soundtrack(music, duration, "Resultados Diários", contest_seed, 0.0, current)
    base.synthesize_custom_segments(
        results[0],
        duration,
        segments,
        music,
        audio,
        primary_voice=voice,
    )
    render_dir = temp / "daily_short_render"
    render_dir.mkdir()
    base._write_concat_video(scenes, audio, output, duration, render_dir)
    return duration


def install_short_duration_fix() -> None:
    base._build_short = _build_short_fixed


install_short_duration_fix()


__all__ = ["install_short_duration_fix"]
