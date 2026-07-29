from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
import wave
from array import array
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from video_visual_v3 import WIDTH, HEIGHT, criar_poster, prepare_numbers, scene_image

DEFAULT_DURATION = 30.0
DEFAULT_FPS = 30
AUDIO_SAMPLE_RATE = 44100


def _slug(value: str) -> str:
    text = (value or "").strip().lower()
    text = (
        text.replace("á", "a").replace("à", "a").replace("ã", "a").replace("â", "a")
        .replace("é", "e").replace("ê", "e").replace("í", "i").replace("ó", "o")
        .replace("ô", "o").replace("õ", "o").replace("ú", "u").replace("ç", "c")
        .replace("+", "mais-")
    )
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _ffmpeg_binary() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg não encontrado no ambiente.")
    return executable


def _run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Falha no FFmpeg: {process.stderr[-3000:]}")


def _render_segment(image_path: Path, output_path: Path, duration: float, fps: int, direction: int, intensity: float = 1.0) -> None:
    frames = max(1, round(duration * fps))
    fade_out = max(0.0, duration - 0.32)
    speed = 0.00026 + 0.00009 * max(0.0, min(1.5, intensity))
    max_zoom = 1.038 + 0.012 * max(0.0, min(1.5, intensity))
    zoom_expression = f"min(zoom+{speed:.6f},{max_zoom:.4f})" if direction >= 0 else f"if(lte(on,1),{max_zoom:.4f},max(1.0,zoom-{speed:.6f}))"
    x_expression = "iw/2-(iw/zoom/2)+10*sin(on/16)"
    y_expression = "ih/2-(ih/zoom/2)+8*cos(on/19)"
    video_filter = (
        f"scale={round(WIDTH * 1.10)}:{round(HEIGHT * 1.10)},"
        f"zoompan=z='{zoom_expression}':x='{x_expression}':y='{y_expression}':"
        f"d={frames}:s={WIDTH}x{HEIGHT}:fps={fps},"
        f"fade=t=in:st=0:d=0.22,fade=t=out:st={fade_out:.3f}:d=0.30,format=yuv420p"
    )
    _run([
        _ffmpeg_binary(), "-y", "-loop", "1", "-i", str(image_path),
        "-vf", video_filter, "-t", f"{duration:.3f}", "-r", str(fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-movflags", "+faststart", "-an", str(output_path),
    ])


def _weighted_durations(total: float, count: int) -> List[float]:
    base_weights = [0.82, 0.92, 1.02, 1.12, 1.23, 1.34, 1.16, 1.05]
    weights = base_weights[:count]
    if count > len(weights):
        weights.extend([1.0] * (count - len(weights)))
    scale = total / max(0.001, sum(weights))
    return [weight * scale for weight in weights]


def _timeline(duration: float, number_count: int) -> Tuple[List[Tuple[str, int, float, float]], List[float], float, float]:
    intro_duration = min(2.35, max(1.8, duration * 0.075))
    final_duration = min(6.0, max(5.2, duration * 0.18))
    cta_duration = min(4.8, max(4.0, duration * 0.145))
    reveal_total = max(6.0, duration - intro_duration - final_duration - cta_duration)

    if number_count <= 0:
        reveal_count = 3
    elif number_count <= 6:
        reveal_count = number_count
    elif number_count <= 15:
        reveal_count = 6
    else:
        reveal_count = 7

    reveal_durations = _weighted_durations(reveal_total, max(1, reveal_count))
    scene_specs: List[Tuple[str, int, float, float]] = [("intro", 0, intro_duration, 1.25)]
    cue_times: List[float] = []
    elapsed = intro_duration

    for stage, segment_duration in enumerate(reveal_durations, start=1):
        cue_times.append(elapsed + 0.08)
        visible = math.ceil(number_count * stage / reveal_count) if number_count else 0
        intensity = 0.85 + 0.08 * stage
        scene_specs.append(("reveal", visible, segment_duration, intensity))
        elapsed += segment_duration

    final_time = elapsed
    scene_specs.append(("final", number_count, final_duration, 1.15))
    elapsed += final_duration
    cta_time = elapsed
    scene_specs.append(("cta", number_count, cta_duration, 1.05))
    return scene_specs, cue_times, final_time, cta_time


def _tone(time_value: float, event_time: float, frequency: float, length: float, amplitude: float) -> float:
    dt = time_value - event_time
    if dt < 0.0 or dt >= length:
        return 0.0
    envelope = math.exp(-dt * 10.0) * min(1.0, dt * 35.0)
    return amplitude * envelope * (
        math.sin(2.0 * math.pi * frequency * dt)
        + 0.42 * math.sin(2.0 * math.pi * frequency * 1.5 * dt)
    )


def _write_soundtrack(path: Path, duration: float, cue_times: Sequence[float], final_time: float, cta_time: float) -> None:
    total_samples = max(1, int(duration * AUDIO_SAMPLE_RATE))
    pcm = array("h")
    events = [(0.18, 92.0, 0.55, 0.25)]
    events.extend((cue, 650.0 + (index % 3) * 110.0, 0.24, 0.20) for index, cue in enumerate(cue_times))
    events.append((final_time + 0.05, 520.0, 0.52, 0.26))
    events.append((cta_time + 0.08, 780.0, 0.48, 0.22))

    for sample_index in range(total_samples):
        t = sample_index / AUDIO_SAMPLE_RATE
        fade_in = min(1.0, t / 0.8)
        fade_out = min(1.0, max(0.0, duration - t) / 1.0)
        fade = fade_in * fade_out

        ambient = (
            0.022 * math.sin(2.0 * math.pi * 110.0 * t)
            + 0.015 * math.sin(2.0 * math.pi * 165.0 * t)
            + 0.010 * math.sin(2.0 * math.pi * 220.0 * t)
        )
        beat_phase = t % 1.0
        beat = 0.0
        if beat_phase < 0.11:
            beat = 0.032 * math.exp(-beat_phase * 26.0) * math.sin(2.0 * math.pi * 72.0 * beat_phase)

        value = (ambient + beat) * fade
        for event_time, frequency, length, amplitude in events:
            value += _tone(t, event_time, frequency, length, amplitude)

        value = max(-0.92, min(0.92, value))
        left = int(value * 32767)
        right = int(value * 0.96 * 32767)
        pcm.append(left)
        pcm.append(right)

    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(AUDIO_SAMPLE_RATE)
        audio.writeframes(pcm.tobytes())


def gerar_video_loteria(data: Dict[str, Any]) -> str:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    duration = max(20.0, min(60.0, float(data.get("duracao") or DEFAULT_DURATION)))
    fps = max(15, min(60, int(data.get("fps") or DEFAULT_FPS)))
    output_dir = Path(str(data.get("output_dir") or "output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_lottery = _slug(loteria) or "loteria"
    safe_contest = _slug(concurso) or "resultado"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    video_path = output_dir / f"video_{safe_lottery}_{safe_contest}_{timestamp}.mp4"

    numbers, _ = prepare_numbers(loteria, data.get("numeros") or data.get("descricao") or "")
    scene_specs, cue_times, final_time, cta_time = _timeline(duration, len(numbers))

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-video-v4-") as temporary_directory:
        temporary = Path(temporary_directory)
        segment_paths: List[Path] = []
        for index, (scene, visible, segment_duration, intensity) in enumerate(scene_specs):
            image_path = temporary / f"scene_{index:02d}_{scene}.png"
            segment_path = temporary / f"segment_{index:02d}.mp4"
            scene_image(data, scene, visible_count=visible, seed=100 + index * 17).save(image_path, quality=95)
            _render_segment(
                image_path,
                segment_path,
                segment_duration,
                fps,
                1 if index % 2 == 0 else -1,
                intensity,
            )
            segment_paths.append(segment_path)

        concat_file = temporary / "concat.txt"
        concat_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in segment_paths), encoding="utf-8")
        silent_video = temporary / "silent_video.mp4"
        _run([
            _ffmpeg_binary(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c", "copy", "-movflags", "+faststart", str(silent_video),
        ])

        soundtrack = temporary / "soundtrack.wav"
        _write_soundtrack(soundtrack, duration, cue_times, final_time, cta_time)
        _run([
            _ffmpeg_binary(), "-y", "-i", str(silent_video), "-i", str(soundtrack),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
            "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(video_path),
        ])

    print(f"[VÍDEO V4] OK: {video_path} | duração={duration:.1f}s | fps={fps} | áudio=sim", flush=True)
    return str(video_path)


def executar(data: Dict[str, Any]) -> str:
    """Alias estável usado por post_video.py, video_queue.py e workflows."""
    return gerar_video_loteria(data)
