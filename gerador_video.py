from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from video_visual_v3 import WIDTH, HEIGHT, criar_poster, prepare_numbers, scene_image

DEFAULT_DURATION = 30.0
DEFAULT_FPS = 30


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


def _render_segment(image_path: Path, output_path: Path, duration: float, fps: int, direction: int) -> None:
    frames = max(1, round(duration * fps))
    fade_out = max(0.0, duration - 0.42)
    zoom_expression = "min(zoom+0.00030,1.045)" if direction >= 0 else "if(lte(on,1),1.045,max(1.0,zoom-0.00030))"
    x_expression = "iw/2-(iw/zoom/2)+8*sin(on/18)"
    y_expression = "ih/2-(ih/zoom/2)+6*cos(on/20)"
    video_filter = (
        f"scale={round(WIDTH * 1.08)}:{round(HEIGHT * 1.08)},"
        f"zoompan=z='{zoom_expression}':x='{x_expression}':y='{y_expression}':"
        f"d={frames}:s={WIDTH}x{HEIGHT}:fps={fps},"
        f"fade=t=in:st=0:d=0.32,fade=t=out:st={fade_out:.3f}:d=0.40,format=yuv420p"
    )
    _run([
        _ffmpeg_binary(), "-y", "-loop", "1", "-i", str(image_path),
        "-vf", video_filter, "-t", f"{duration:.3f}", "-r", str(fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-movflags", "+faststart", "-an", str(output_path),
    ])


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
    reveal_count = 6 if numbers else 2
    reveal_total = duration * 0.60
    intro_duration = duration * 0.13
    final_duration = duration * 0.17
    cta_duration = duration - intro_duration - reveal_total - final_duration
    reveal_duration = reveal_total / reveal_count

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-video-v3-") as temporary_directory:
        temporary = Path(temporary_directory)
        scene_specs: List[Tuple[str, int, float]] = [("intro", 0, intro_duration)]
        for stage in range(1, reveal_count + 1):
            visible = math.ceil(len(numbers) * stage / reveal_count) if numbers else 0
            scene_specs.append(("reveal", visible, reveal_duration))
        scene_specs.extend([
            ("final", len(numbers), final_duration),
            ("cta", len(numbers), cta_duration),
        ])

        segment_paths: List[Path] = []
        for index, (scene, visible, segment_duration) in enumerate(scene_specs):
            image_path = temporary / f"scene_{index:02d}_{scene}.png"
            segment_path = temporary / f"segment_{index:02d}.mp4"
            scene_image(data, scene, visible_count=visible, seed=100 + index * 17).save(image_path, quality=95)
            _render_segment(image_path, segment_path, segment_duration, fps, 1 if index % 2 == 0 else -1)
            segment_paths.append(segment_path)

        concat_file = temporary / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{path.as_posix()}'" for path in segment_paths),
            encoding="utf-8",
        )
        _run([
            _ffmpeg_binary(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c", "copy", "-movflags", "+faststart", str(video_path),
        ])

    print(f"[VÍDEO V3] OK: {video_path} | duração={duration:.1f}s | fps={fps}", flush=True)
    return str(video_path)


def executar(data: Dict[str, Any]) -> str:
    """Alias estável usado por post_video.py, video_queue.py e workflows."""
    return gerar_video_loteria(data)
