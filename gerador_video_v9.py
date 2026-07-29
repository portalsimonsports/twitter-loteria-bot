from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Sequence

import gerador_video_v7 as v7
import video_visual_v5 as v5
from audio_identity_v9 import variation_for, write_soundtrack

criar_poster = v7.criar_poster


def _run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Falha no FFmpeg V9: {process.stderr[-5000:]}")


def _reveal_times_v9(loteria: str, count: int):
    if count <= 0:
        return []
    key = v7._slug(loteria)
    if "dupla-sena" in key and count >= 12:
        return [7.60 + index * 3.15 for index in range(6)] + [29.00 + index * 3.15 for index in range(6)]
    start = 7.60
    end = 40.0 if count <= 6 else 44.0 if count <= 10 else 46.0 if count <= 15 else 47.0
    if count == 1:
        return [start]
    interval = (end - start) / (count - 1)
    return [start + index * interval for index in range(count)]


def _signature_filter(loteria: str, data: Dict[str, Any], cta_start: float) -> str:
    primary, _dark, _light = v5._palette(loteria, data.get("cor_fundo_rgb"))
    color = "".join(f"{value:02x}" for value in primary)
    note_offsets = (0.42, 0.69, 0.96, 1.28)
    starts = [0.18 + offset for offset in note_offsets] + [cta_start + 0.10 + offset for offset in note_offsets]
    filters = []
    for start in starts:
        filters.append(
            f"drawbox=x=40:y=32:w=1000:h=136:color=0x{color}@0.34:t=6:"
            f"enable='between(t,{start:.2f},{start + 0.22:.2f})'"
        )
        filters.append(
            f"drawbox=x=0:y=0:w=iw:h=ih:color=0x{color}@0.045:t=fill:"
            f"enable='between(t,{start:.2f},{start + 0.13:.2f})'"
        )
    filters.append("format=yuv420p")
    return ",".join(filters)


def _apply_visual_signature(base_video: Path, output_video: Path, loteria: str, data: Dict[str, Any], cta_start: float) -> None:
    _run([
        "ffmpeg", "-y", "-i", str(base_video),
        "-vf", _signature_filter(loteria, data, cta_start),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "copy", "-t", "60", "-movflags", "+faststart", str(output_video),
    ])


def gerar_video_loteria(data: Dict[str, Any]) -> str:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    cta_start = 54.20
    variation = variation_for(loteria, concurso)

    original_writer = v7._write_soundtrack
    original_reveal_times = v7._reveal_times

    def _writer(path, duration, lottery_name, result_time, cta_time):
        return write_soundtrack(path, duration, lottery_name, concurso, result_time, cta_time)

    v7._write_soundtrack = _writer
    v7._reveal_times = _reveal_times_v9
    try:
        base_path = Path(v7.gerar_video_loteria(data))
    finally:
        v7._write_soundtrack = original_writer
        v7._reveal_times = original_reveal_times

    final_path = base_path.with_name(base_path.stem + "_identidade_v9.mp4")
    _apply_visual_signature(base_path, final_path, loteria, data, cta_start)
    os.replace(final_path, base_path)

    print(
        f"[VÍDEO V9] OK: {base_path} | sem voz | trilha dinâmica={variation + 1}/4 | primeira dezena após 7,6s",
        flush=True,
    )
    return str(base_path)


def executar(data: Dict[str, Any]) -> str:
    return gerar_video_loteria(data)


__all__ = ["criar_poster", "executar", "gerar_video_loteria"]
