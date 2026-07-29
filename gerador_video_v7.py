from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw

from gerador_video_v5 import _write_soundtrack
from video_visual_v6 import (
    HEIGHT,
    WIDTH,
    criar_poster,
    number_positions,
    prepare_numbers,
    render_ball_overlay,
    render_cta,
    render_intro,
    render_reveal_background,
)
import video_visual_v5 as v5

FPS = int(os.getenv("VIDEO_FPS", "30"))
DURATION = 60.0
BACKGROUND_SCALE = 1.035
FOCUS_DIAMETER = 300


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
    key = _slug(loteria)
    if "dupla-sena" in key and count >= 12:
        first = [7.0 + index * 3.25 for index in range(6)]
        second = [28.3 + index * 3.25 for index in range(6)]
        return first + second

    start = 7.0
    end_by_count = 40.0 if count <= 6 else 44.0 if count <= 10 else 46.0 if count <= 15 else 47.0
    if count == 1:
        return [start]
    interval = (end_by_count - start) / (count - 1)
    return [start + index * interval for index in range(count)]


def _event_duration(reveal_times: Sequence[float]) -> float:
    if len(reveal_times) <= 1:
        return 1.65
    smallest_gap = min(b - a for a, b in zip(reveal_times, reveal_times[1:]))
    return max(1.10, min(1.65, smallest_gap * 0.72))


def _scaled_frame(image: Image.Image, scale: float = BACKGROUND_SCALE) -> Image.Image:
    return image.convert("RGB").resize((round(WIDTH * scale), round(HEIGHT * scale)), Image.Resampling.LANCZOS)


def _crop_offsets(image: Image.Image, t: float) -> Tuple[int, int]:
    max_x = max(0, image.width - WIDTH)
    max_y = max(0, image.height - HEIGHT)
    x = round(max_x / 2 + min(max_x / 2, 7 * WIDTH / 1080.0) * math.sin(t * 0.22))
    y = round(max_y / 2 + min(max_y / 2, 6 * WIDTH / 1080.0) * math.cos(t * 0.19))
    return max(0, min(max_x, x)), max(0, min(max_y, y))


def _moving_crop(image: Image.Image, t: float) -> Image.Image:
    x, y = _crop_offsets(image, t)
    return image.crop((x, y, x + WIDTH, y + HEIGHT))


def _ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _ease_out_back(value: float) -> float:
    value = max(0.0, min(1.0, value))
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (value - 1.0) ** 3 + c1 * (value - 1.0) ** 2


def _ball_sprite(data: Dict[str, Any], number: str) -> Image.Image:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    primary, dark, light = v5._palette(loteria, data.get("cor_fundo_rgb"))
    canvas_size = 390
    diameter = 280
    margin = (canvas_size - diameter) // 2
    sprite = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sprite, "RGBA")
    v5._ball(draw, margin, margin, diameter, number, True, True, primary, dark, light)
    return sprite


def _target_geometry(position: Tuple[int, int, int], scaled_background: Image.Image, t: float) -> Tuple[float, float, float]:
    x, y, diameter = position
    crop_x, crop_y = _crop_offsets(scaled_background, t)
    center_x = (x + diameter / 2.0) * BACKGROUND_SCALE - crop_x
    center_y = (y + diameter / 2.0) * BACKGROUND_SCALE - crop_y
    return center_x, center_y, diameter * BACKGROUND_SCALE


def _draw_focus_ball(
    frame: Image.Image,
    sprite: Image.Image,
    progress: float,
    target: Tuple[float, float, float],
    data: Dict[str, Any],
) -> Image.Image:
    progress = max(0.0, min(1.0, progress))
    focus_center = (WIDTH * 0.50, HEIGHT * 0.50)
    target_x, target_y, target_diameter = target

    if progress < 0.34:
        phase = progress / 0.34
        scale_progress = _ease_out_back(phase)
        center_x, center_y = focus_center
        diameter = 58.0 + (FOCUS_DIAMETER - 58.0) * scale_progress
        opacity = min(1.0, phase * 4.5)
    elif progress < 0.52:
        center_x, center_y = focus_center
        diameter = FOCUS_DIAMETER * (1.0 + 0.018 * math.sin((progress - 0.34) / 0.18 * math.pi))
        opacity = 1.0
    else:
        phase = _ease((progress - 0.52) / 0.48)
        center_x = focus_center[0] + (target_x - focus_center[0]) * phase
        center_y = focus_center[1] + (target_y - focus_center[1]) * phase
        diameter = FOCUS_DIAMETER + (target_diameter - FOCUS_DIAMETER) * phase
        opacity = 1.0

    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    primary, _dark, light = v5._palette(loteria, data.get("cor_fundo_rgb"))
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    if progress < 0.58:
        ring_phase = progress / 0.58
        radius = diameter * (0.56 + 0.42 * ring_phase)
        alpha = round(150 * (1.0 - ring_phase))
        for extra, width, factor in ((0, 6, 1.0), (30, 3, 0.55)):
            r = radius + extra
            draw.ellipse(
                (center_x - r, center_y - r, center_x + r, center_y + r),
                outline=(*light, round(alpha * factor)),
                width=max(1, round(width * WIDTH / 1080.0)),
            )
        glow_r = diameter * 0.72
        draw.ellipse(
            (center_x - glow_r, center_y - glow_r, center_x + glow_r, center_y + glow_r),
            fill=(*primary, round(34 * (1.0 - ring_phase))),
        )

    sprite_size = max(24, round(sprite.width * diameter / 280.0))
    rendered = sprite.resize((sprite_size, sprite_size), Image.Resampling.LANCZOS)
    if opacity < 0.999:
        alpha_channel = rendered.getchannel("A").point(lambda value: round(value * opacity))
        rendered.putalpha(alpha_channel)
    left = round(center_x - sprite_size / 2)
    top = round(center_y - sprite_size / 2)
    overlay.alpha_composite(rendered, (left, top))
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def gerar_video_loteria(data: Dict[str, Any]) -> str:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    numbers, _ = prepare_numbers(loteria, data.get("numeros") or data.get("descricao") or "")
    positions = number_positions(loteria, numbers)
    reveal_times = _reveal_times(loteria, len(numbers))
    animation_duration = _event_duration(reveal_times)

    output_dir = Path(str(data.get("output_dir") or "output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / f"video_{_slug(loteria) or 'loteria'}_{_slug(concurso) or 'resultado'}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.mp4"

    reveal_start, reveal_fade = 5.60, 0.85
    result_start, result_fade = 49.00, 0.85
    cta_start, cta_fade = 54.20, 0.90

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-video-v7-") as temp_dir:
        temp = Path(temp_dir)
        soundtrack = temp / "soundtrack.wav"
        _write_soundtrack(soundtrack, DURATION, loteria, result_start, cta_start)

        intro = _scaled_frame(render_intro(data))
        reveal_zero = render_reveal_background(data, final=False).convert("RGBA")
        cumulative: List[Image.Image] = [_scaled_frame(reveal_zero)]
        working = reveal_zero.copy()
        sprites: List[Image.Image] = []
        for number, position in zip(numbers, positions):
            sprites.append(_ball_sprite(data, number))
            working = Image.alpha_composite(working, render_ball_overlay(data, number, position, newest=False))
            cumulative.append(_scaled_frame(working))

        final_working = render_reveal_background(data, final=True).convert("RGBA")
        for number, position in zip(numbers, positions):
            final_working = Image.alpha_composite(final_working, render_ball_overlay(data, number, position, newest=False))
        final_frame = _scaled_frame(final_working)
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
                for frame_index in range(round(DURATION * FPS)):
                    t = frame_index / FPS
                    if t < reveal_start:
                        frame = _moving_crop(intro, t)
                    elif t < reveal_start + reveal_fade:
                        frame = Image.blend(
                            _moving_crop(intro, t),
                            _moving_crop(cumulative[0], t),
                            _ease((t - reveal_start) / reveal_fade),
                        )
                    elif t >= cta_start:
                        frame = Image.blend(
                            _moving_crop(final_frame, t),
                            _moving_crop(cta, t),
                            _ease((t - cta_start) / cta_fade),
                        )
                    elif t >= result_start:
                        frame = Image.blend(
                            _moving_crop(cumulative[-1], t),
                            _moving_crop(final_frame, t),
                            _ease((t - result_start) / result_fade),
                        )
                    else:
                        active = next(
                            (index for index, start in enumerate(reveal_times) if start <= t < start + animation_duration),
                            None,
                        )
                        if active is not None:
                            base_frame = _moving_crop(cumulative[active], t)
                            target = _target_geometry(positions[active], cumulative[active], t)
                            frame = _draw_focus_ball(
                                base_frame,
                                sprites[active],
                                (t - reveal_times[active]) / animation_duration,
                                target,
                                data,
                            )
                        else:
                            shown = sum(1 for start in reveal_times if t >= start + animation_duration)
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

    print(
        f"[VÍDEO V7] OK: {video_path} | duração=60s | destaque central e encaixe suave | números={len(numbers)}",
        flush=True,
    )
    return str(video_path)


def executar(data: Dict[str, Any]) -> str:
    return gerar_video_loteria(data)


__all__ = ["criar_poster", "executar", "gerar_video_loteria"]
