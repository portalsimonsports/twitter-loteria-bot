from __future__ import annotations

import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Sequence

from PIL import Image, ImageDraw, ImageFont

from audio_identity_v9 import write_soundtrack
from gerador_video_v9 import gerar_video_loteria as gerar_base_vertical
from video_visual_v5 import _palette


def _run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Falha no FFmpeg V10: {process.stderr[-6000:]}")


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


def _numbers_count(data: Dict[str, Any]) -> int:
    raw = str(data.get("numeros") or data.get("descricao") or "")
    values = re.findall(r"\d+", raw)
    return max(1, len(values))


def _short_cta(data: Dict[str, Any], output: Path) -> None:
    loteria = str(data.get("loteria") or "Loteria").strip()
    primary, dark, light = _palette(loteria, data.get("cor_fundo_rgb"))
    image = Image.new("RGB", (1080, 1920), dark)
    draw = ImageDraw.Draw(image, "RGBA")

    for y in range(1920):
        ratio = y / 1919.0
        color = tuple(round(dark[i] * (1 - ratio * 0.34) + primary[i] * ratio * 0.34) for i in range(3))
        draw.line((0, y, 1080, y), fill=(*color, 255))

    for radius, alpha in ((430, 28), (330, 44), (235, 72)):
        draw.ellipse((540 - radius, 790 - radius, 540 + radius, 790 + radius), outline=(*light, alpha), width=5)

    draw.rounded_rectangle((55, 55, 1025, 205), radius=42, fill=(*dark, 225), outline=(*light, 115), width=3)
    draw.ellipse((90, 88, 170, 168), fill=(*primary, 255), outline=(*light, 230), width=3)
    _center(draw, (130, 128), "S", 42, (255, 255, 255, 255), True)
    draw.text((205, 83), "PORTAL", font=_font(29, True), fill=(*light, 245))
    draw.text((205, 120), "SIMONSPORTS", font=_font(50, True), fill=(255, 255, 255, 255))

    _center(draw, (540, 460), loteria.upper(), 72 if len(loteria) <= 16 else 56, (*light, 255), True)
    _center(draw, (540, 650), "RESULTADO COMPLETO", 76, (255, 255, 255, 255), True)
    _center(draw, (540, 760), "DISPONÍVEL NO CANAL", 48, (*light, 255), True)

    draw.rounded_rectangle((125, 965, 955, 1145), radius=58, fill=(*primary, 245), outline=(*light, 230), width=4)
    _center(draw, (540, 1055), "TOQUE NO VÍDEO RELACIONADO", 38, (255, 255, 255, 255), True)

    _center(draw, (540, 1355), "SIMONSPORTS", 70, (255, 255, 255, 255), True)
    _center(draw, (540, 1450), "SIMPLESMENTE O MELHOR", 42, (*light, 255), True)
    _center(draw, (540, 1710), "portalsimonsports.com", 31, (255, 255, 255, 225), False)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, quality=96)


def _horizontal_overlay(data: Dict[str, Any], output: Path) -> None:
    loteria = str(data.get("loteria") or "Loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    data_sorteio = str(data.get("data") or "").strip()
    premio = str(data.get("premio") or "").strip()
    primary, dark, light = _palette(loteria, data.get("cor_fundo_rgb"))

    image = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((38, 38, 630, 1042), radius=44, fill=(*dark, 214), outline=(*light, 92), width=3)
    draw.rounded_rectangle((1290, 38, 1882, 1042), radius=44, fill=(*dark, 214), outline=(*light, 92), width=3)

    draw.ellipse((85, 86, 185, 186), fill=(*primary, 255), outline=(*light, 230), width=4)
    _center(draw, (135, 136), "S", 48, (255, 255, 255, 255), True)
    draw.text((225, 76), "PORTAL", font=_font(30, True), fill=(*light, 245))
    draw.text((225, 118), "SIMONSPORTS", font=_font(48, True), fill=(255, 255, 255, 255))

    _center(draw, (334, 315), "SIMONSPORTS", 53, (255, 255, 255, 255), True)
    _center(draw, (334, 382), "SIMPLESMENTE O MELHOR", 29, (*light, 255), True)
    draw.rounded_rectangle((105, 470, 565, 600), radius=36, fill=(*primary, 225), outline=(*light, 205), width=3)
    _center(draw, (335, 535), "RESULTADO OFICIAL", 35, (255, 255, 255, 255), True)
    _center(draw, (334, 690), "FONTE", 24, (*light, 220), True)
    _center(draw, (334, 738), "CAIXA LOTERIAS", 34, (255, 255, 255, 245), True)
    _center(draw, (334, 913), "CONTEÚDO INFORMATIVO", 23, (255, 255, 255, 205), False)

    _center(draw, (1586, 155), loteria.upper(), 49 if len(loteria) <= 16 else 38, (*light, 255), True)
    if concurso:
        _center(draw, (1586, 235), f"CONCURSO {concurso}", 31, (255, 255, 255, 245), True)
    if data_sorteio:
        _center(draw, (1586, 295), data_sorteio, 26, (*light, 235), False)

    draw.rounded_rectangle((1345, 385, 1827, 545), radius=42, fill=(*primary, 215), outline=(*light, 210), width=3)
    _center(draw, (1586, 447), "RESULTADO", 28, (255, 255, 255, 235), True)
    _center(draw, (1586, 495), "COMPLETO", 43, (255, 255, 255, 255), True)

    if premio:
        _center(draw, (1586, 650), "PRÊMIO / ESTIMATIVA", 23, (*light, 225), True)
        _center(draw, (1586, 705), premio[:32], 31, (255, 255, 255, 250), True)

    _center(draw, (1586, 860), "OUTROS RESULTADOS", 25, (*light, 225), True)
    _center(draw, (1586, 910), "NO CANAL SIMONSPORTS", 30, (255, 255, 255, 250), True)
    _center(draw, (1586, 985), "portalsimonsports.com", 23, (255, 255, 255, 210), False)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def _create_short(base_video: Path, data: Dict[str, Any], output_dir: Path) -> Path:
    loteria = _slug(str(data.get("loteria") or "loteria")) or "loteria"
    concurso = _slug(str(data.get("concurso") or "resultado")) or "resultado"
    output = output_dir / f"short_{loteria}_{concurso}_30s.mp4"
    with tempfile.TemporaryDirectory(prefix="portalsimonsports-short-v10-") as temp_dir:
        cta = Path(temp_dir) / "cta_short.png"
        _short_cta(data, cta)
        filter_complex = (
            "[0:v]trim=start=0:end=24,setpts=PTS-STARTPTS,fps=30,format=yuv420p[v0];"
            "[1:v]scale=1080:1920,trim=duration=6.5,setpts=PTS-STARTPTS,fps=30,format=yuv420p[v1];"
            "[v0][v1]xfade=transition=fade:duration=0.5:offset=23.5[v];"
            "[0:a]atrim=start=0:end=24,asetpts=PTS-STARTPTS[a0];"
            "[0:a]atrim=start=53.5:end=60,asetpts=PTS-STARTPTS[a1];"
            "[a0][a1]acrossfade=d=0.5:c1=tri:c2=tri[a]"
        )
        _run([
            "ffmpeg", "-y", "-i", str(base_video), "-loop", "1", "-t", "6.5", "-i", str(cta),
            "-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-t", "30", "-movflags", "+faststart", str(output),
        ])
    return output


def _create_full(base_video: Path, data: Dict[str, Any], output_dir: Path) -> Path:
    count = _numbers_count(data)
    duration = float(min(120, max(90, round(80 + count * 1.75))))
    factor = duration / 60.0
    loteria_text = str(data.get("loteria") or "Loteria").strip()
    concurso_text = str(data.get("concurso") or "").strip()
    loteria = _slug(loteria_text) or "loteria"
    concurso = _slug(concurso_text or "resultado") or "resultado"
    output = output_dir / f"video_completo_{loteria}_{concurso}_{round(duration)}s.mp4"

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-completo-v10-") as temp_dir:
        temp = Path(temp_dir)
        overlay = temp / "moldura_horizontal.png"
        soundtrack = temp / "trilha_completa.wav"
        _horizontal_overlay(data, overlay)
        write_soundtrack(soundtrack, duration, loteria_text, concurso_text, 49.0 * factor, 54.2 * factor)

        filter_complex = (
            f"[0:v]setpts={factor:.8f}*PTS,split=2[bg][fg];"
            "[bg]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
            "boxblur=28:2,eq=brightness=-0.24:saturation=1.18[bg2];"
            "[fg]scale=-2:1080[fg2];"
            "[bg2][fg2]overlay=(W-w)/2:0[main];"
            "[main][2:v]overlay=0:0,format=yuv420p[v]"
        )
        _run([
            "ffmpeg", "-y", "-i", str(base_video), "-i", str(soundtrack),
            "-loop", "1", "-t", f"{duration:.2f}", "-i", str(overlay),
            "-filter_complex", filter_complex, "-map", "[v]", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.2f}",
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
        f"[VÍDEO V10] Pacote gerado | Short={short_path.name} | completo={full_path.name}",
        flush=True,
    )
    return {"short": str(short_path), "completo": str(full_path), "base": str(base_video)}


def executar(data: Dict[str, Any]) -> str:
    """Compatibilidade: retorna o Short; use gerar_pacote para obter ambos."""
    return gerar_pacote(data)["short"]


__all__ = ["executar", "gerar_pacote"]
