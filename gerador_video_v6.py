from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from gerador_video_v5 import _write_soundtrack
from video_visual_v6 import HEIGHT, WIDTH, criar_poster, number_positions, prepare_numbers, render_ball_overlay, render_cta, render_intro, render_reveal_background

FPS = int(os.getenv("VIDEO_FPS", "30"))
DURATION = 60.0


def _slug(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.translate(str.maketrans("áàãâéêíóôõúç", "aaaaeeiooouc")).replace("+", "mais-")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _ffmpeg_binary() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg não encontrado no ambiente.")
    return executable


def _reveal_times(loteria: str, count: int) -> List[float]:
    if count <= 0:
        return []
    if "dupla-sena" in _slug(loteria) and count >= 12:
        return [6.7 + index * 3.45 for index in range(6)] + [29.0 + index * 3.45 for index in range(6)]
    start = 6.7
    end = 38.0 if count <= 6 else 44.5 if count <= 12 else 46.5 if count <= 15 else 47.5
    if count == 1:
        return [start]
    interval = (end - start) / (count - 1)
    return [start + index * interval for index in range(count)]


def _scaled_frame(image: Image.Image, scale: float = 1.035) -> Image.Image:
    return image.convert("RGB").resize((round(WIDTH * scale), round(HEIGHT * scale)), Image.Resampling.LANCZOS)


def _moving_crop(image: Image.Image, t: float) -> Image.Image:
    max_x = max(0, image.width - WIDTH)
    max_y = max(0, image.height - HEIGHT)
    x = round(max_x / 2 + min(max_x / 2, 7 * WIDTH / 1080.0) * math.sin(t * 0.22))
    y = round(max_y / 2 + min(max_y / 2, 6 * WIDTH / 1080.0) * math.cos(t * 0.19))
    x = max(0, min(max_x, x))
    y = max(0, min(max_y, y))
    return image.crop((x, y, x + WIDTH, y + HEIGHT))


def _ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def gerar_video_loteria(data: Dict[str, Any]) -> str:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    numbers, _ = prepare_numbers(loteria, data.get("numeros") or data.get("descricao") or "")
    output_dir = Path(str(data.get("output_dir") or "output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / f"video_{_slug(loteria) or 'loteria'}_{_slug(concurso) or 'resultado'}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.mp4"

    reveal_start, reveal_fade = 5.50, 0.90
    cta_start, cta_fade = 52.50, 0.90
    result_time, ball_fade = 47.50, 0.65
    reveal_times = _reveal_times(loteria, len(numbers))

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-video-v6-") as temp_dir:
        temp = Path(temp_dir)
        soundtrack = temp / "soundtrack.wav"
        _write_soundtrack(soundtrack, DURATION, loteria, result_time, cta_start)

        intro = _scaled_frame(render_intro(data))
        reveal_zero = render_reveal_background(data, final=False).convert("RGBA")
        cumulative: List[Image.Image] = [_scaled_frame(reveal_zero)]
        working = reveal_zero.copy()
        for number, position in zip(numbers, number_positions(loteria, numbers)):
            working = Image.alpha_composite(working, render_ball_overlay(data, number, position, newest=True))
            cumulative.append(_scaled_frame(working))
        cta = _scaled_frame(render_cta(data))

        log_path = temp / "ffmpeg.log"
        command = [
            _ffmpeg_binary(), "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-", "-i", str(soundtrack),
            "-t", f"{DURATION:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(video_path),
        ]
        with open(log_path, "w", encoding="utf-8") as log_file:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log_file)
            assert process.stdin is not None
            try:
                active_index = 0
                for frame_index in range(round(DURATION * FPS)):
                    t = frame_index / FPS
                    if t < reveal_start:
                        frame = _moving_crop(intro, t)
                    elif t < reveal_start + reveal_fade:
                        frame = Image.blend(_moving_crop(intro, t), _moving_crop(cumulative[0], t), _ease((t - reveal_start) / reveal_fade))
                    elif t >= cta_start:
                        frame = Image.blend(_moving_crop(cumulative[-1], t), _moving_crop(cta, t), _ease((t - cta_start) / cta_fade))
                    else:
                        while active_index < len(reveal_times) and t >= reveal_times[active_index] + ball_fade:
                            active_index += 1
                        if active_index < len(reveal_times) and reveal_times[active_index] <= t < reveal_times[active_index] + ball_fade:
                            frame = Image.blend(
                                _moving_crop(cumulative[active_index], t),
                                _moving_crop(cumulative[active_index + 1], t),
                                _ease((t - reveal_times[active_index]) / ball_fade),
                            )
                        else:
                            shown = sum(1 for start in reveal_times if t >= start + ball_fade)
                            frame = _moving_crop(cumulative[min(shown, len(cumulative) - 1)], t)
                    process.stdin.write(frame.tobytes())
            except Exception:
                process.kill()
                raise
            finally:
                try:
                    process.stdin.close()
                except Exception:
                    pass
            return_code = process.wait()
        if return_code != 0:
            raise RuntimeError("Falha no FFmpeg: " + log_path.read_text(encoding="utf-8", errors="replace")[-5000:])

    print(f"[VÍDEO V6] OK: {video_path} | duração=60s | animação contínua | números={len(numbers)}", flush=True)
    return str(video_path)


def executar(data: Dict[str, Any]) -> str:
    return gerar_video_loteria(data)


__all__ = ["criar_poster", "executar", "gerar_video_loteria"]
