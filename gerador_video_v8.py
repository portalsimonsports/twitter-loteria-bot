from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Sequence

import gerador_video_v7 as v7
import video_visual_v5 as v5
from audio_identity_v8 import variation_for, voice_assets, write_soundtrack

criar_poster = v7.criar_poster


def _run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Falha no FFmpeg V8: {process.stderr[-5000:]}")


def _signature_filter(loteria: str, data: Dict[str, Any], cta_start: float) -> str:
    primary, _dark, _light = v5._palette(loteria, data.get("cor_fundo_rgb"))
    color = "".join(f"{value:02x}" for value in primary)
    note_offsets = (0.14, 0.36, 0.58, 0.80)
    starts = list(note_offsets) + [cta_start + 0.05 + offset for offset in note_offsets]
    filters = []
    for start in starts:
        end = start + 0.16
        filters.append(
            f"drawbox=x=40:y=32:w=1000:h=136:color=0x{color}@0.34:t=6:"
            f"enable='between(t,{start:.2f},{end:.2f})'"
        )
        filters.append(
            f"drawbox=x=0:y=0:w=iw:h=ih:color=0x{color}@0.045:t=fill:"
            f"enable='between(t,{start:.2f},{start + 0.11:.2f})'"
        )
    filters.append("format=yuv420p")
    return ",".join(filters)


def _mix_identity(
    base_video: Path,
    output_video: Path,
    intro_voice: Path | None,
    outro_voice: Path | None,
    loteria: str,
    data: Dict[str, Any],
    cta_start: float,
) -> None:
    video_filter = _signature_filter(loteria, data, cta_start)
    common = ["ffmpeg", "-y", "-i", str(base_video)]

    if intro_voice and outro_voice:
        command = common + ["-i", str(intro_voice), "-i", str(outro_voice)]
        filter_complex = (
            f"[0:v]{video_filter}[v];"
            "[0:a]aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            "volume='if(between(t,0.20,5.45)+between(t,54.10,59.80),0.30,0.84)':eval=frame[music];"
            "[1:a]aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            "adelay=620|620,volume=1.18[intro];"
            "[2:a]aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            "adelay=54550|54550,volume=1.16[outro];"
            "[music][intro][outro]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[a]"
        )
        command += [
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-t", "60",
            "-movflags", "+faststart", str(output_video),
        ]
    else:
        command += [
            "-vf", video_filter,
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "copy", "-t", "60",
            "-movflags", "+faststart", str(output_video),
        ]
    _run(command)


def gerar_video_loteria(data: Dict[str, Any]) -> str:
    loteria = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    cta_start = 54.20
    variation = variation_for(loteria, concurso)

    original_writer = v7._write_soundtrack

    def _writer(path, duration, lottery_name, result_time, cta_time):
        return write_soundtrack(path, duration, lottery_name, concurso, result_time, cta_time)

    v7._write_soundtrack = _writer
    try:
        base_path = Path(v7.gerar_video_loteria(data))
    finally:
        v7._write_soundtrack = original_writer

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-identidade-v8-") as temp_dir:
        intro_voice, outro_voice, voice_method = voice_assets(temp_dir, data)
        final_path = base_path.with_name(base_path.stem + "_identidade_v8.mp4")
        _mix_identity(base_path, final_path, intro_voice, outro_voice, loteria, data, cta_start)
        os.replace(final_path, base_path)

    print(
        f"[VÍDEO V8] OK: {base_path} | identidade audiovisual | trilha={variation + 1}/4 | voz={voice_method}",
        flush=True,
    )
    return str(base_path)


def executar(data: Dict[str, Any]) -> str:
    return gerar_video_loteria(data)


__all__ = ["criar_poster", "executar", "gerar_video_loteria"]
