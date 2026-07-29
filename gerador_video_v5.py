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

from video_visual_v5 import WIDTH, HEIGHT, criar_poster, prepare_numbers, scene_image

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
    fade_out = max(0.0, duration - 0.26)
    speed = 0.00028 + 0.00010 * max(0.0, min(1.5, intensity))
    max_zoom = 1.040 + 0.014 * max(0.0, min(1.5, intensity))
    zoom_expression = f"min(zoom+{speed:.6f},{max_zoom:.4f})" if direction >= 0 else f"if(lte(on,1),{max_zoom:.4f},max(1.0,zoom-{speed:.6f}))"
    x_expression = "iw/2-(iw/zoom/2)+12*sin(on/15)"
    y_expression = "ih/2-(ih/zoom/2)+9*cos(on/18)"
    video_filter = (
        f"scale={round(WIDTH * 1.11)}:{round(HEIGHT * 1.11)},"
        f"zoompan=z='{zoom_expression}':x='{x_expression}':y='{y_expression}':"
        f"d={frames}:s={WIDTH}x{HEIGHT}:fps={fps},"
        f"fade=t=in:st=0:d=0.18,fade=t=out:st={fade_out:.3f}:d=0.25,format=yuv420p"
    )
    _run([
        _ffmpeg_binary(), "-y", "-loop", "1", "-i", str(image_path),
        "-vf", video_filter, "-t", f"{duration:.3f}", "-r", str(fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-movflags", "+faststart", "-an", str(output_path),
    ])


def _weighted_durations(total: float, count: int) -> List[float]:
    weights = [0.82, 0.90, 0.98, 1.08, 1.18, 1.30, 1.20, 1.08][:count]
    if count > len(weights):
        weights.extend([1.0] * (count - len(weights)))
    scale = total / max(0.001, sum(weights))
    return [weight * scale for weight in weights]


def _timeline(duration: float, number_count: int) -> Tuple[List[Tuple[str, int, float, float]], float, float]:
    intro_duration = min(2.0, max(1.55, duration * 0.060))
    final_duration = min(6.0, max(5.4, duration * 0.19))
    cta_duration = min(4.5, max(4.0, duration * 0.14))
    reveal_total = max(6.0, duration - intro_duration - final_duration - cta_duration)
    if number_count <= 0:
        reveal_count = 3
    elif number_count <= 6:
        reveal_count = number_count
    elif number_count <= 15:
        reveal_count = 6
    else:
        reveal_count = 8
    scenes: List[Tuple[str, int, float, float]] = [("intro", 0, intro_duration, 1.20)]
    elapsed = intro_duration
    for stage, segment_duration in enumerate(_weighted_durations(reveal_total, max(1, reveal_count)), start=1):
        visible = math.ceil(number_count * stage / reveal_count) if number_count else 0
        scenes.append(("reveal", visible, segment_duration, 0.90 + 0.07 * stage))
        elapsed += segment_duration
    final_time = elapsed
    scenes.append(("final", number_count, final_duration, 1.18))
    elapsed += final_duration
    cta_time = elapsed
    scenes.append(("cta", number_count, cta_duration, 1.08))
    return scenes, final_time, cta_time


def _midi(note: float) -> float:
    return 440.0 * (2.0 ** ((note - 69.0) / 12.0))


def _pulse(phase: float, decay: float = 7.0) -> float:
    phase %= 1.0
    return math.exp(-phase * decay) * min(1.0, phase * 35.0)


def _lottery_key(loteria: str) -> int:
    keys = {
        "mega-sena": 45,
        "lotofacil": 48,
        "quina": 50,
        "lotomania": 52,
        "timemania": 47,
        "dupla-sena": 43,
        "dia-de-sorte": 50,
        "super-sete": 45,
        "mais-milionaria": 41,
        "federal": 48,
        "loteca": 43,
    }
    slug = _slug(loteria)
    for name, note in keys.items():
        if name in slug or slug in name:
            return note
    return 45


def _write_soundtrack(path: Path, duration: float, loteria: str, final_time: float, cta_time: float) -> None:
    """Trilha eletrônica contínua, original e gerada localmente."""
    total_samples = max(1, int(duration * AUDIO_SAMPLE_RATE))
    pcm = array("h")
    bpm = 124.0
    beat_seconds = 60.0 / bpm
    bar_seconds = beat_seconds * 4.0
    base_note = _lottery_key(loteria)
    progression = [(0, (0, 3, 7)), (-4, (0, 4, 7)), (3, (0, 4, 7)), (-2, (0, 4, 7))]

    for sample_index in range(total_samples):
        t = sample_index / AUDIO_SAMPLE_RATE
        fade = min(1.0, t / 0.65) * min(1.0, max(0.0, duration - t) / 1.15)
        beat_index = int(t / beat_seconds)
        beat_phase = (t / beat_seconds) % 1.0
        half_phase = (t / (beat_seconds / 2.0)) % 1.0
        bar_index = int(t / bar_seconds)
        shift, intervals = progression[bar_index % len(progression)]
        root_note = base_note + shift
        chord_notes = [root_note + interval for interval in intervals]
        progress = min(1.0, t / max(1.0, final_time))
        energy = 0.82 + 0.20 * progress + (0.13 if t >= final_time else 0.0) + (0.08 if t >= cta_time else 0.0)

        slow_lfo = 0.84 + 0.16 * math.sin(2.0 * math.pi * 0.10 * t)
        pad_left = pad_right = 0.0
        for idx, note in enumerate(chord_notes):
            freq = _midi(note + 12)
            phase_offset = idx * 0.43
            tone = math.sin(2.0 * math.pi * freq * t + phase_offset)
            tone += 0.34 * math.sin(2.0 * math.pi * freq * 2.0 * t + phase_offset * 1.7)
            pan = -0.45 + idx * 0.45
            pad_left += tone * (1.0 - pan * 0.35)
            pad_right += tone * (1.0 + pan * 0.35)
        pad_left *= 0.018 * slow_lfo
        pad_right *= 0.018 * slow_lfo

        bass_env = _pulse(beat_phase, 5.0)
        bass_freq = _midi(root_note - 12)
        bass = (math.sin(2.0 * math.pi * bass_freq * t) + 0.28 * math.sin(2.0 * math.pi * bass_freq * 2.0 * t)) * 0.085 * bass_env

        kick_env = math.exp(-beat_phase * 18.0)
        kick_freq = 54.0 - 20.0 * min(1.0, beat_phase * 4.0)
        kick = math.sin(2.0 * math.pi * kick_freq * (beat_phase * beat_seconds)) * 0.18 * kick_env

        arp_step = int(t / (beat_seconds / 2.0))
        arp_note = chord_notes[arp_step % len(chord_notes)] + (12 if arp_step % 4 == 3 else 0)
        arp_freq = _midi(arp_note + 12)
        arp_env = _pulse(half_phase, 8.5)
        arp = (math.sin(2.0 * math.pi * arp_freq * t) + 0.20 * math.sin(2.0 * math.pi * arp_freq * 2.0 * t)) * 0.055 * arp_env
        arp_pan = -0.42 if arp_step % 2 == 0 else 0.42

        hat_noise = math.sin(2.0 * math.pi * 6120.0 * t) + 0.55 * math.sin(2.0 * math.pi * 8230.0 * t + 0.7) + 0.35 * math.sin(2.0 * math.pi * 10130.0 * t + 1.4)
        hat = hat_noise * 0.012 * _pulse(half_phase, 24.0)

        snare = 0.0
        if beat_index % 4 in (1, 3):
            snare_noise = math.sin(2.0 * math.pi * 1780.0 * t) + 0.72 * math.sin(2.0 * math.pi * 2430.0 * t + 0.8) + 0.45 * math.sin(2.0 * math.pi * 3370.0 * t + 1.5)
            snare = snare_noise * 0.030 * math.exp(-beat_phase * 17.0)

        swell = 0.0
        for target in (final_time, cta_time):
            distance = target - t
            if 0.0 < distance < 1.20:
                amount = 1.0 - distance / 1.20
                swell += math.sin(2.0 * math.pi * (240.0 + 760.0 * amount * amount) * t) * 0.018 * amount

        left = (pad_left + bass + kick + arp * (1.0 - arp_pan * 0.55) + hat + snare + swell) * energy * fade
        right = (pad_right + bass + kick + arp * (1.0 + arp_pan * 0.55) + hat + snare + swell) * energy * fade
        left = math.tanh(left * 1.65) * 0.78
        right = math.tanh(right * 1.65) * 0.78
        pcm.append(int(max(-1.0, min(1.0, left)) * 32767))
        pcm.append(int(max(-1.0, min(1.0, right)) * 32767))

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
    video_path = output_dir / f"video_{_slug(loteria) or 'loteria'}_{_slug(concurso) or 'resultado'}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.mp4"
    numbers, _ = prepare_numbers(loteria, data.get("numeros") or data.get("descricao") or "")
    scenes, final_time, cta_time = _timeline(duration, len(numbers))

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-video-v5-") as temp_dir:
        temp = Path(temp_dir)
        segments: List[Path] = []
        for index, (scene, visible, segment_duration, intensity) in enumerate(scenes):
            image_path = temp / f"scene_{index:02d}_{scene}.png"
            segment_path = temp / f"segment_{index:02d}.mp4"
            scene_image(data, scene, visible_count=visible, seed=100 + index * 17).save(image_path, quality=95)
            _render_segment(image_path, segment_path, segment_duration, fps, 1 if index % 2 == 0 else -1, intensity)
            segments.append(segment_path)

        concat_file = temp / "concat.txt"
        concat_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in segments), encoding="utf-8")
        silent_video = temp / "silent_video.mp4"
        _run([_ffmpeg_binary(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", "-movflags", "+faststart", str(silent_video)])
        soundtrack = temp / "soundtrack.wav"
        _write_soundtrack(soundtrack, duration, loteria, final_time, cta_time)
        _run([
            _ffmpeg_binary(), "-y", "-i", str(silent_video), "-i", str(soundtrack),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
            "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(video_path),
        ])

    print(f"[VÍDEO V5] OK: {video_path} | duração={duration:.1f}s | fps={fps} | trilha=contínua", flush=True)
    return str(video_path)


def executar(data: Dict[str, Any]) -> str:
    return gerar_video_loteria(data)
