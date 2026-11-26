from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence

import daily_video_v19 as base
import daily_video_v19_branding_fix as branding


def _build_short_duration_safe(
    results: Sequence[Dict[str, Any]],
    output: Path,
    temp: Path,
    voice: str,
) -> float:
    if not results:
        raise RuntimeError("Nenhum resultado informado para o Short diário.")

    # Federal: medir a locução real de todos os cinco bilhetes antes de renderizar.
    if len(results) == 1 and base._normalize_name(results[0].get("loteria")) == "Loteria Federal":
        import subprocess
        import sys
        data = results[0]
        speech = base._full_speech(data)
        closing = "Mais resultados em Portal Simon Sports ponto com. Inscreva-se no canal e ative as notificações."
        approved = {"pt-BR-FranciscaNeural", "pt-BR-AntonioNeural", "pt-BR-ThalitaNeural"}
        if voice not in approved:
            voice = "pt-BR-FranciscaNeural"
        durations = []
        tracks = []
        for index, phrase in enumerate((speech, closing)):
            mp3 = temp / f"federal_voice_{index}.mp3"
            wav = temp / f"federal_voice_{index}.wav"
            subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voice,
                "--text", phrase, "--write-media", str(mp3)], check=True, timeout=180)
            seconds = float(subprocess.check_output(["ffprobe", "-v", "error",
                "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                str(mp3)], text=True))
            if seconds <= 0:
                raise RuntimeError("Federal: locução vazia")
            duration = seconds + 1.5
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3),
                "-af", "adelay=200:all=1,apad", "-t", str(duration),
                "-ar", "44100", "-ac", "2", str(wav)], check=True)
            durations.append(duration)
            tracks.append(wav)
        audio = temp / "federal_short_audio.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tracks[0]),
            "-i", str(tracks[1]), "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[a]",
            "-map", "[a]", str(audio)], check=True)
        render_dir = temp / "federal_short_render"
        render_dir.mkdir(exist_ok=True)
        scenes = [(base._result_short_image(data), durations[0]),
            (branding._closing_image_branded(results, (1080, 1920)), durations[1])]
        base._write_concat_video(scenes, audio, output, sum(durations), render_dir)
        return sum(durations)

    count = len(results)
    per_result = 24.0 if count == 1 else max(4.5, min(10.0, 50.0 / count))

    # A versão anterior usava fechamento fixo de 8s. Com 2 resultados,
    # 10 + 10 + 8 = 28s e o próprio código abortava o workflow.
    # O fechamento passa a completar automaticamente o mínimo de 30s.
    result_duration = per_result * count
    closing_duration = max(8.0, 30.0 - result_duration)

    # Margem de segurança para evitar arredondamento/concatenação abaixo de 30s.
    if result_duration + closing_duration < 30.2:
        closing_duration += 0.25

    # Nunca permitir Short acima de 60s. Se necessário, reduz por resultado.
    if result_duration + closing_duration > 59.5:
        available = max(1.0, 59.5 - closing_duration)
        per_result = available / count
        result_duration = per_result * count

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

    scenes.append((branding._closing_image_branded(results, (1080, 1920)), closing_duration))
    segments.append(
        base.SpeechSegment(
            current + 0.20,
            voice,
            "Mais resultados em Portal Simon Sports ponto com, seção Loterias Caixa. Link na descrição. Inscreva-se no canal e ative as notificações.",
            1.0,
            base.SHORT_RATE,
            "closing",
        )
    )

    duration = current + closing_duration
    if duration < 30.0 or duration > 60.0:
        raise RuntimeError(f"Short diário fora da faixa de 30 a 60 segundos após ajuste: {duration:.1f}s")

    music = temp / "daily_short_music.wav"
    audio = temp / "daily_short_audio.wav"
    contest_seed = base._date_key(results[0].get("data"))
    base.write_soundtrack(music, duration, "Resultados Diários", contest_seed, 0.0, current)
    base.synthesize_custom_segments(
        results[0], duration, segments, music, audio, primary_voice=voice
    )
    render_dir = temp / "daily_short_render"
    render_dir.mkdir(exist_ok=True)
    base._write_concat_video(scenes, audio, output, duration, render_dir)
    return duration


base._build_short = _build_short_duration_safe
branding._build_short_branded = _build_short_duration_safe

__all__ = ["_build_short_duration_safe"]
