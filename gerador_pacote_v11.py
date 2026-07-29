from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Sequence

from PIL import Image, ImageDraw, ImageFont

from audio_identity_v9 import write_soundtrack
from gerador_video_v9 import gerar_video_loteria as gerar_base_vertical
from video_visual_v5 import _palette
from voice_dialogue_v11 import (
    extract_numbers,
    reveal_times_full,
    reveal_times_short,
    synthesize_dialogue_mix,
)


VERSION = "V11"


def _run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Falha no FFmpeg {VERSION}: {process.stderr[-6000:]}")


def _slug(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.translate(str.maketrans("áàãâéêíóôõúç", "aaaaeeiooouc"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _center(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, fill, bold: bool = False) -> None:
    draw.text(xy, text, font=_font(size, bold), fill=fill, anchor="mm", align="center")


def _short_cta(data: Dict[str, Any], output: Path) -> None:
    lottery = str(data.get("loteria") or "Loteria").strip()
    primary, dark, light = _palette(lottery, data.get("cor_fundo_rgb"))
    image = Image.new("RGB", (1080, 1920), dark)
    draw = ImageDraw.Draw(image, "RGBA")

    for y in range(1920):
        ratio = y / 1919.0
        color = tuple(round(dark[i] * (1 - ratio * 0.38) + primary[i] * ratio * 0.38) for i in range(3))
        draw.line((0, y, 1080, y), fill=(*color, 255))

    for radius, alpha in ((440, 24), (330, 42), (225, 72)):
        draw.ellipse((540 - radius, 730 - radius, 540 + radius, 730 + radius), outline=(*light, alpha), width=5)

    draw.rounded_rectangle((55, 55, 1025, 205), radius=42, fill=(*dark, 225), outline=(*light, 115), width=3)
    draw.ellipse((90, 88, 170, 168), fill=(*primary, 255), outline=(*light, 230), width=3)
    _center(draw, (130, 128), "S", 42, (255, 255, 255, 255), True)
    draw.text((205, 83), "PORTAL", font=_font(29, True), fill=(*light, 245))
    draw.text((205, 120), "SIMONSPORTS", font=_font(50, True), fill=(255, 255, 255, 255))

    _center(draw, (540, 395), lottery.upper(), 68 if len(lottery) <= 16 else 54, (*light, 255), True)
    _center(draw, (540, 545), "RESULTADO CONFERIDO", 69, (255, 255, 255, 255), True)

    boxes = (
        (790, "DEIXE SEU LIKE"),
        (1010, "INSCREVA-SE NO CANAL"),
        (1230, "COMENTE E COMPARTILHE"),
    )
    for center_y, text in boxes:
        draw.rounded_rectangle((115, center_y - 75, 965, center_y + 75), radius=50, fill=(*primary, 238), outline=(*light, 220), width=4)
        _center(draw, (540, center_y), text, 40 if len(text) < 18 else 34, (255, 255, 255, 255), True)

    _center(draw, (540, 1510), "TRÊS VOZES. UM RESULTADO.", 38, (*light, 255), True)
    _center(draw, (540, 1600), "SIMONSPORTS", 70, (255, 255, 255, 255), True)
    _center(draw, (540, 1695), "SIMPLESMENTE O MELHOR", 42, (*light, 255), True)
    _center(draw, (540, 1840), "portalsimonsports.com", 31, (255, 255, 255, 225), False)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, quality=96)


def _horizontal_overlay(data: Dict[str, Any], output: Path) -> None:
    lottery = str(data.get("loteria") or "Loteria").strip()
    contest = str(data.get("concurso") or "").strip()
    draw_date = str(data.get("data") or "").strip()
    prize = str(data.get("premio") or "").strip()
    primary, dark, light = _palette(lottery, data.get("cor_fundo_rgb"))

    image = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((38, 38, 630, 1042), radius=44, fill=(*dark, 214), outline=(*light, 92), width=3)
    draw.rounded_rectangle((1290, 38, 1882, 1042), radius=44, fill=(*dark, 214), outline=(*light, 92), width=3)

    draw.ellipse((85, 86, 185, 186), fill=(*primary, 255), outline=(*light, 230), width=4)
    _center(draw, (135, 136), "S", 48, (255, 255, 255, 255), True)
    draw.text((225, 76), "PORTAL", font=_font(30, True), fill=(*light, 245))
    draw.text((225, 118), "SIMONSPORTS", font=_font(48, True), fill=(255, 255, 255, 255))

    _center(draw, (334, 305), "BOLETIM DE RESULTADOS", 39, (255, 255, 255, 255), True)
    _center(draw, (334, 365), "FRANCISCA • ANTÔNIO • THALITA", 25, (*light, 255), True)
    draw.rounded_rectangle((105, 445, 565, 575), radius=36, fill=(*primary, 225), outline=(*light, 205), width=3)
    _center(draw, (335, 510), "RESULTADO OFICIAL", 35, (255, 255, 255, 255), True)
    _center(draw, (334, 655), "FONTE", 24, (*light, 220), True)
    _center(draw, (334, 703), "CAIXA LOTERIAS", 34, (255, 255, 255, 245), True)
    _center(draw, (334, 820), "CURTA • COMENTE", 29, (*light, 240), True)
    _center(draw, (334, 868), "INSCREVA-SE", 34, (255, 255, 255, 250), True)
    _center(draw, (334, 958), "CONTEÚDO INFORMATIVO", 23, (255, 255, 255, 205), False)

    _center(draw, (1586, 145), lottery.upper(), 49 if len(lottery) <= 16 else 38, (*light, 255), True)
    if contest:
        _center(draw, (1586, 225), f"CONCURSO {contest}", 31, (255, 255, 255, 245), True)
    if draw_date:
        _center(draw, (1586, 285), draw_date, 26, (*light, 235), False)

    draw.rounded_rectangle((1345, 375, 1827, 535), radius=42, fill=(*primary, 215), outline=(*light, 210), width=3)
    _center(draw, (1586, 437), "RESULTADO", 28, (255, 255, 255, 235), True)
    _center(draw, (1586, 485), "COMPLETO", 43, (255, 255, 255, 255), True)

    if prize:
        _center(draw, (1586, 630), "PRÊMIO / ESTIMATIVA", 23, (*light, 225), True)
        _center(draw, (1586, 685), prize[:32], 31, (255, 255, 255, 250), True)

    _center(draw, (1586, 810), "DEIXE SEU LIKE", 28, (*light, 240), True)
    _center(draw, (1586, 865), "E ESCREVA NOS COMENTÁRIOS", 27, (255, 255, 255, 250), True)
    _center(draw, (1586, 960), "portalsimonsports.com", 23, (255, 255, 255, 210), False)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def _create_short(base_video: Path, data: Dict[str, Any], output_dir: Path) -> Path:
    lottery_text = str(data.get("loteria") or "Loteria").strip()
    contest_text = str(data.get("concurso") or "").strip()
    lottery = _slug(lottery_text) or "loteria"
    contest = _slug(contest_text or "resultado") or "resultado"
    output = output_dir / f"short_{lottery}_{contest}_30s_dialogo_v11.mp4"
    numbers = extract_numbers(data)
    reveals = reveal_times_short(lottery_text, len(numbers))

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-short-v11-") as temp_dir:
        temp = Path(temp_dir)
        cta = temp / "cta_short.png"
        music = temp / "trilha_short.wav"
        narrated = temp / "audio_short_narrado.wav"
        _short_cta(data, cta)
        write_soundtrack(music, 30.0, lottery_text, contest_text, 23.4, 24.0)
        synthesize_dialogue_mix(data, 30.0, reveals, music, narrated, compact=True)

        intro_duration = 5.4
        result_duration = 18.1
        filter_complex = (
            f"[0:v]trim=start=0:end=0.9,setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={intro_duration - 0.9:.3f},fps=30,format=yuv420p[intro];"
            f"[0:v]trim=start=7.0:end=54.0,setpts={(result_duration / 47.0):.9f}*PTS,fps=30,format=yuv420p[result];"
            "[intro][result]concat=n=2:v=1:a=0,trim=duration=23.5,setpts=PTS-STARTPTS[v0];"
            "[1:v]scale=1080:1920,trim=duration=6.5,setpts=PTS-STARTPTS,fps=30,format=yuv420p[v1];"
            "[v0][v1]xfade=transition=fade:duration=0.5:offset=23.5[v]"
        )
        _run([
            "ffmpeg", "-y", "-i", str(base_video), "-loop", "1", "-t", "6.5", "-i", str(cta), "-i", str(narrated),
            "-filter_complex", filter_complex, "-map", "[v]", "-map", "2:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-t", "30", "-movflags", "+faststart", str(output),
        ])
    return output


def _create_full(base_video: Path, data: Dict[str, Any], output_dir: Path) -> Path:
    numbers = extract_numbers(data)
    count = max(1, len(numbers))
    duration = float(min(120, max(108, round(90 + count * 2.8))))
    factor = duration / 60.0
    lottery_text = str(data.get("loteria") or "Loteria").strip()
    contest_text = str(data.get("concurso") or "").strip()
    lottery = _slug(lottery_text) or "loteria"
    contest = _slug(contest_text or "resultado") or "resultado"
    output = output_dir / f"video_completo_{lottery}_{contest}_{round(duration)}s_dialogo_v11.mp4"
    reveals = reveal_times_full(lottery_text, len(numbers), factor)

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-completo-v11-") as temp_dir:
        temp = Path(temp_dir)
        overlay = temp / "moldura_horizontal.png"
        music = temp / "trilha_completa.wav"
        narrated = temp / "audio_completo_narrado.wav"
        _horizontal_overlay(data, overlay)
        write_soundtrack(music, duration, lottery_text, contest_text, 49.0 * factor, 54.2 * factor)
        synthesize_dialogue_mix(data, duration, reveals, music, narrated, compact=False)

        filter_complex = (
            f"[0:v]setpts={factor:.9f}*PTS,split=2[bg][fg];"
            "[bg]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
            "boxblur=28:2,eq=brightness=-0.24:saturation=1.18[bg2];"
            "[fg]scale=-2:1080[fg2];"
            "[bg2][fg2]overlay=(W-w)/2:0[main];"
            "[main][1:v]overlay=0:0,format=yuv420p[v]"
        )
        _run([
            "ffmpeg", "-y", "-i", str(base_video), "-loop", "1", "-t", f"{duration:.3f}", "-i", str(overlay), "-i", str(narrated),
            "-filter_complex", filter_complex, "-map", "[v]", "-map", "2:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}",
            "-movflags", "+faststart", str(output),
        ])
    return output


def gerar_pacote(data: Dict[str, Any]) -> Dict[str, str]:
    output_dir = Path(str(data.get("output_dir") or "output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    base_video = Path(gerar_base_vertical(data))
    short_path = _create_short(base_video, data, output_dir)
    full_path = _create_full(base_video, data, output_dir)
    print(
        f"[VÍDEO {VERSION}] Pacote gerado com Francisca, Antônio e Thalita | "
        f"Short={short_path.name} | completo={full_path.name}",
        flush=True,
    )
    return {"short": str(short_path), "completo": str(full_path), "base": str(base_video)}


def executar(data: Dict[str, Any]) -> str:
    """Compatibilidade: retorna o Short; use gerar_pacote para obter os dois vídeos."""
    return gerar_pacote(data)["short"]


__all__ = ["executar", "gerar_pacote"]
