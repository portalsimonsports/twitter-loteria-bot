from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict

import gerador_pacote_v13 as v13
from voice_narration_v14 import (
    extract_numbers,
    reveal_times_full,
    reveal_times_short,
    select_voice,
    synthesize_narration_mix,
    voice_label,
)


VERSION = "V14"
FULL_DURATION = 165.0
FULL_INTRO_DURATION = 45.0
FULL_RESULT_DURATION = 78.0
FULL_CLOSING_DURATION = 42.0


def _create_short(base_video: Path, data: Dict[str, Any], output_dir: Path, voice: str) -> Path:
    lottery_text = str(data.get("loteria") or "Loteria").strip()
    contest_text = str(data.get("concurso") or "").strip()
    lottery = v13.visual._slug(lottery_text) or "loteria"
    contest = v13.visual._slug(contest_text or "resultado") or "resultado"
    output = output_dir / f"short_{lottery}_{contest}_30s_voz_v14.mp4"
    numbers = extract_numbers(data)
    reveals = reveal_times_short(
        lottery_text,
        len(numbers),
        intro_duration=5.4,
        result_duration=18.1,
    )

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-short-v14-") as temp_dir:
        temp = Path(temp_dir)
        cta = temp / "cta_short.png"
        music = temp / "trilha_short.wav"
        narrated = temp / "audio_short_narrado.wav"

        v13._short_cta(data, cta, voice_label(voice))
        v13.write_soundtrack(music, 30.0, lottery_text, contest_text, 23.4, 24.0)
        synthesize_narration_mix(
            data,
            30.0,
            reveals,
            music,
            narrated,
            compact=True,
            voice=voice,
        )

        intro_duration = 5.4
        result_duration = 18.6
        filter_complex = (
            f"[0:v]trim=start=0:end=0.9,setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={intro_duration - 0.9:.3f},"
            "fps=30,settb=AVTB,format=yuv420p[intro];"
            f"[0:v]trim=start=7.0:end=54.0,setpts={(result_duration / 47.0):.9f}*PTS,"
            "fps=30,settb=AVTB,format=yuv420p[result];"
            "[intro][result]concat=n=2:v=1:a=0,trim=duration=24,"
            "setpts=PTS-STARTPTS,fade=t=out:st=23.55:d=0.45[v0];"
            "[1:v]scale=1080:1920,trim=duration=6,setpts=PTS-STARTPTS,"
            "fps=30,settb=AVTB,format=yuv420p,fade=t=in:st=0:d=0.45[v1];"
            "[v0][v1]concat=n=2:v=1:a=0,trim=duration=30,setpts=PTS-STARTPTS[v]"
        )

        v13.visual._run([
            "ffmpeg", "-y",
            "-i", str(base_video),
            "-loop", "1", "-t", "6", "-i", str(cta),
            "-i", str(narrated),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "2:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-t", "30",
            "-movflags", "+faststart", str(output),
        ])
    return output


def _create_full(base_video: Path, data: Dict[str, Any], output_dir: Path, voice: str) -> Path:
    numbers = extract_numbers(data)
    lottery_text = str(data.get("loteria") or "Loteria").strip()
    contest_text = str(data.get("concurso") or "").strip()
    lottery = v13.visual._slug(lottery_text) or "loteria"
    contest = v13.visual._slug(contest_text or "resultado") or "resultado"
    output = output_dir / f"video_completo_{lottery}_{contest}_{round(FULL_DURATION)}s_voz_v14.mp4"
    reveals = reveal_times_full(
        lottery_text,
        len(numbers),
        intro_duration=FULL_INTRO_DURATION,
        result_duration=FULL_RESULT_DURATION,
    )

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-completo-v14-") as temp_dir:
        temp = Path(temp_dir)
        overlay = temp / "moldura_horizontal.png"
        music = temp / "trilha_completa.wav"
        narrated = temp / "audio_completo_narrado.wav"

        v13._horizontal_overlay(data, overlay, voice_label(voice))
        v13.write_soundtrack(
            music,
            FULL_DURATION,
            lottery_text,
            contest_text,
            FULL_INTRO_DURATION + FULL_RESULT_DURATION - 5.0,
            FULL_INTRO_DURATION + FULL_RESULT_DURATION,
        )
        synthesize_narration_mix(
            data,
            FULL_DURATION,
            reveals,
            music,
            narrated,
            compact=False,
            voice=voice,
        )

        filter_complex = (
            f"[0:v]trim=start=0:end=0.9,setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={FULL_INTRO_DURATION - 0.9:.3f}[intro];"
            f"[0:v]trim=start=7.0:end=54.0,setpts={(FULL_RESULT_DURATION / 47.0):.9f}*PTS[result];"
            f"[0:v]trim=start=53.1:end=54.0,setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={FULL_CLOSING_DURATION - 0.9:.3f}[closing];"
            f"[intro][result][closing]concat=n=3:v=1:a=0,trim=duration={FULL_DURATION:.0f},"
            "setpts=PTS-STARTPTS,split=2[bg][fg];"
            "[bg]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
            "boxblur=28:2,eq=brightness=-0.24:saturation=1.18[bg2];"
            "[fg]scale=-2:1080[fg2];"
            "[bg2][fg2]overlay=(W-w)/2:0[main];"
            "[main][1:v]overlay=0:0,format=yuv420p[v]"
        )

        v13.visual._run([
            "ffmpeg", "-y",
            "-i", str(base_video),
            "-loop", "1", "-t", f"{FULL_DURATION:.3f}", "-i", str(overlay),
            "-i", str(narrated),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "2:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{FULL_DURATION:.3f}",
            "-movflags", "+faststart", str(output),
        ])
    return output


def gerar_pacote(data: Dict[str, Any]) -> Dict[str, str]:
    output_dir = Path(str(data.get("output_dir") or "output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_voice = select_voice(data)
    presenter = voice_label(selected_voice)
    base_video = Path(v13.visual.gerar_base_vertical(data))
    short_path = _create_short(base_video, data, output_dir, selected_voice)
    full_path = _create_full(base_video, data, output_dir, selected_voice)

    print(
        f"[VÍDEO {VERSION}] Voz única: {presenter} | locução sem sobreposição | "
        f"Short={short_path.name} | completo={full_path.name}",
        flush=True,
    )
    return {
        "short": str(short_path),
        "completo": str(full_path),
        "base": str(base_video),
        "voz": presenter,
    }


def executar(data: Dict[str, Any]) -> str:
    return gerar_pacote(data)["short"]


__all__ = ["executar", "gerar_pacote"]
