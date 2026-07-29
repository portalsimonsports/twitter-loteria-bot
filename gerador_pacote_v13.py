from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict

from PIL import Image, ImageDraw

import gerador_pacote_v11 as visual
from audio_identity_v9 import write_soundtrack
from voice_narration_v13 import (
    extract_numbers,
    reveal_times_full,
    reveal_times_short,
    select_voice,
    synthesize_narration_mix,
    voice_label,
)


VERSION = "V13"
FULL_DURATION = 150.0
FULL_INTRO_DURATION = 38.0
FULL_RESULT_DURATION = 76.0
FULL_CLOSING_DURATION = 36.0


def _short_cta(data: Dict[str, Any], output: Path, presenter: str) -> None:
    lottery = str(data.get("loteria") or "Loteria").strip()
    primary, dark, light = visual._palette(lottery, data.get("cor_fundo_rgb"))
    image = Image.new("RGB", (1080, 1920), dark)
    draw = ImageDraw.Draw(image, "RGBA")

    for y in range(1920):
        ratio = y / 1919.0
        color = tuple(round(dark[i] * (1 - ratio * 0.38) + primary[i] * ratio * 0.38) for i in range(3))
        draw.line((0, y, 1080, y), fill=(*color, 255))

    for radius, alpha in ((440, 24), (330, 42), (225, 72)):
        draw.ellipse(
            (540 - radius, 730 - radius, 540 + radius, 730 + radius),
            outline=(*light, alpha),
            width=5,
        )

    draw.rounded_rectangle((55, 55, 1025, 205), radius=42, fill=(*dark, 225), outline=(*light, 115), width=3)
    draw.ellipse((90, 88, 170, 168), fill=(*primary, 255), outline=(*light, 230), width=3)
    visual._center(draw, (130, 128), "S", 42, (255, 255, 255, 255), True)
    draw.text((205, 83), "PORTAL", font=visual._font(29, True), fill=(*light, 245))
    draw.text((205, 120), "SIMONSPORTS", font=visual._font(50, True), fill=(255, 255, 255, 255))

    visual._center(draw, (540, 375), lottery.upper(), 68 if len(lottery) <= 16 else 54, (*light, 255), True)
    visual._center(draw, (540, 515), "RESULTADO CONFERIDO", 67, (255, 255, 255, 255), True)
    visual._center(draw, (540, 625), f"APRESENTAÇÃO: {presenter.upper()}", 35, (*light, 255), True)

    boxes = (
        (840, "DEIXE SEU LIKE"),
        (1060, "INSCREVA-SE NO CANAL"),
        (1280, "COMENTE E COMPARTILHE"),
    )
    for center_y, text in boxes:
        draw.rounded_rectangle(
            (115, center_y - 75, 965, center_y + 75),
            radius=50,
            fill=(*primary, 238),
            outline=(*light, 220),
            width=4,
        )
        visual._center(draw, (540, center_y), text, 40 if len(text) < 18 else 34, (255, 255, 255, 255), True)

    visual._center(draw, (540, 1540), "UMA VOZ POR EDIÇÃO", 38, (*light, 255), True)
    visual._center(draw, (540, 1630), "SIMONSPORTS", 70, (255, 255, 255, 255), True)
    visual._center(draw, (540, 1725), "SIMPLESMENTE O MELHOR", 42, (*light, 255), True)
    visual._center(draw, (540, 1850), "portalsimonsports.com", 31, (255, 255, 255, 225), False)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, quality=96)


def _horizontal_overlay(data: Dict[str, Any], output: Path, presenter: str) -> None:
    lottery = str(data.get("loteria") or "Loteria").strip()
    contest = str(data.get("concurso") or "").strip()
    draw_date = str(data.get("data") or "").strip()
    prize = str(data.get("premio") or "").strip()
    primary, dark, light = visual._palette(lottery, data.get("cor_fundo_rgb"))

    image = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((38, 38, 630, 1042), radius=44, fill=(*dark, 214), outline=(*light, 92), width=3)
    draw.rounded_rectangle((1290, 38, 1882, 1042), radius=44, fill=(*dark, 214), outline=(*light, 92), width=3)

    draw.ellipse((85, 86, 185, 186), fill=(*primary, 255), outline=(*light, 230), width=4)
    visual._center(draw, (135, 136), "S", 48, (255, 255, 255, 255), True)
    draw.text((225, 76), "PORTAL", font=visual._font(30, True), fill=(*light, 245))
    draw.text((225, 118), "SIMONSPORTS", font=visual._font(48, True), fill=(255, 255, 255, 255))

    visual._center(draw, (334, 292), "BOLETIM DE RESULTADOS", 39, (255, 255, 255, 255), True)
    visual._center(draw, (334, 350), f"APRESENTAÇÃO: {presenter.upper()}", 27, (*light, 255), True)
    draw.rounded_rectangle((105, 435, 565, 565), radius=36, fill=(*primary, 225), outline=(*light, 205), width=3)
    visual._center(draw, (335, 500), "RESULTADO OFICIAL", 35, (255, 255, 255, 255), True)
    visual._center(draw, (334, 645), "FONTE", 24, (*light, 220), True)
    visual._center(draw, (334, 693), "CAIXA LOTERIAS", 34, (255, 255, 255, 245), True)
    visual._center(draw, (334, 810), "CURTA • COMENTE", 29, (*light, 240), True)
    visual._center(draw, (334, 858), "INSCREVA-SE", 34, (255, 255, 255, 250), True)
    visual._center(draw, (334, 958), "CONTEÚDO INFORMATIVO", 23, (255, 255, 255, 205), False)

    visual._center(draw, (1586, 145), lottery.upper(), 49 if len(lottery) <= 16 else 38, (*light, 255), True)
    if contest:
        visual._center(draw, (1586, 225), f"CONCURSO {contest}", 31, (255, 255, 255, 245), True)
    if draw_date:
        visual._center(draw, (1586, 285), draw_date, 26, (*light, 235), False)

    draw.rounded_rectangle((1345, 375, 1827, 535), radius=42, fill=(*primary, 215), outline=(*light, 210), width=3)
    visual._center(draw, (1586, 437), "RESULTADO", 28, (255, 255, 255, 235), True)
    visual._center(draw, (1586, 485), "COMPLETO", 43, (255, 255, 255, 255), True)

    if prize:
        visual._center(draw, (1586, 630), "PRÊMIO / ESTIMATIVA", 23, (*light, 225), True)
        visual._center(draw, (1586, 685), prize[:32], 31, (255, 255, 255, 250), True)

    visual._center(draw, (1586, 810), "DEIXE SEU LIKE", 28, (*light, 240), True)
    visual._center(draw, (1586, 865), "E ESCREVA NOS COMENTÁRIOS", 27, (255, 255, 255, 250), True)
    visual._center(draw, (1586, 960), "portalsimonsports.com", 23, (255, 255, 255, 210), False)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def _create_short(base_video: Path, data: Dict[str, Any], output_dir: Path, voice: str) -> Path:
    lottery_text = str(data.get("loteria") or "Loteria").strip()
    contest_text = str(data.get("concurso") or "").strip()
    lottery = visual._slug(lottery_text) or "loteria"
    contest = visual._slug(contest_text or "resultado") or "resultado"
    output = output_dir / f"short_{lottery}_{contest}_30s_voz_v13.mp4"
    numbers = extract_numbers(data)
    reveals = reveal_times_short(lottery_text, len(numbers), intro_duration=5.4, result_duration=18.1)

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-short-v13-") as temp_dir:
        temp = Path(temp_dir)
        cta = temp / "cta_short.png"
        music = temp / "trilha_short.wav"
        narrated = temp / "audio_short_narrado.wav"

        _short_cta(data, cta, voice_label(voice))
        write_soundtrack(music, 30.0, lottery_text, contest_text, 23.4, 24.0)
        synthesize_narration_mix(data, 30.0, reveals, music, narrated, compact=True, voice=voice)

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

        visual._run([
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
    lottery = visual._slug(lottery_text) or "loteria"
    contest = visual._slug(contest_text or "resultado") or "resultado"
    output = output_dir / f"video_completo_{lottery}_{contest}_{round(FULL_DURATION)}s_voz_v13.mp4"
    reveals = reveal_times_full(
        lottery_text,
        len(numbers),
        intro_duration=FULL_INTRO_DURATION,
        result_duration=FULL_RESULT_DURATION,
    )

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-completo-v13-") as temp_dir:
        temp = Path(temp_dir)
        overlay = temp / "moldura_horizontal.png"
        music = temp / "trilha_completa.wav"
        narrated = temp / "audio_completo_narrado.wav"

        _horizontal_overlay(data, overlay, voice_label(voice))
        write_soundtrack(
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

        visual._run([
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
    base_video = Path(visual.gerar_base_vertical(data))
    short_path = _create_short(base_video, data, output_dir, selected_voice)
    full_path = _create_full(base_video, data, output_dir, selected_voice)

    print(
        f"[VÍDEO {VERSION}] Voz única desta edição: {presenter} | "
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
