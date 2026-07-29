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

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

WIDTH = 1080
HEIGHT = 1920
DEFAULT_DURATION = 8.0
DEFAULT_FPS = 30

PALETTES: Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]] = {
    "mega-sena": ((0, 110, 70), (0, 65, 55), (83, 220, 145)),
    "lotofacil": ((126, 31, 137), (65, 18, 82), (229, 150, 255)),
    "quina": ((39, 50, 145), (20, 29, 80), (143, 170, 255)),
    "lotomania": ((242, 102, 36), (133, 44, 16), (255, 201, 130)),
    "timemania": ((0, 130, 160), (0, 70, 88), (117, 228, 244)),
    "dupla-sena": ((154, 32, 54), (87, 16, 32), (255, 156, 173)),
    "dia-de-sorte": ((193, 136, 26), (93, 61, 9), (255, 224, 138)),
    "super-sete": ((56, 120, 55), (20, 65, 33), (154, 229, 151)),
    "mais-milionaria": ((45, 46, 55), (17, 18, 23), (219, 187, 90)),
    "federal": ((26, 89, 166), (13, 44, 89), (126, 191, 255)),
    "loteca": ((0, 113, 188), (0, 55, 102), (128, 211, 255)),
}


def _slug(value: str) -> str:
    text = (value or "").strip().lower()
    text = (
        text.replace("á", "a").replace("à", "a").replace("ã", "a").replace("â", "a")
        .replace("é", "e").replace("ê", "e").replace("í", "i")
        .replace("ó", "o").replace("ô", "o").replace("õ", "o")
        .replace("ú", "u").replace("ç", "c").replace("+", "mais-")
    )
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _palette(loteria: str, override: Any = None):
    if isinstance(override, (list, tuple)) and len(override) == 3:
        try:
            c = tuple(int(x) for x in override)
            return c, tuple(max(0, int(x * 0.5)) for x in c), (255, 255, 255)
        except Exception:
            pass
    key = _slug(loteria)
    for name, colors in PALETTES.items():
        if name in key or key in name:
            return colors
    return (25, 91, 135), (10, 37, 74), (136, 215, 255)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _gradient(size: Tuple[int, int], top: Tuple[int, int, int], bottom: Tuple[int, int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        t2 = t * t * (3 - 2 * t)
        row = tuple(round(top[i] * (1 - t2) + bottom[i] * t2) for i in range(3))
        for x in range(w):
            px[x, y] = row
    return img


def _cover(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    image = image.convert("RGB")
    sw, sh = size
    scale = max(sw / image.width, sh / image.height)
    nw, nh = int(image.width * scale), int(image.height * scale)
    image = image.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - sw) // 2)
    top = max(0, (nh - sh) // 2)
    return image.crop((left, top, left + sw, top + sh))


def _load_background(path: str, colors) -> Image.Image:
    top, bottom, _ = colors
    base = _gradient((WIDTH, HEIGHT), top, bottom)
    if path and os.path.exists(path):
        try:
            photo = _cover(Image.open(path), (WIDTH, HEIGHT)).filter(ImageFilter.GaussianBlur(2.5))
            photo = ImageEnhance.Contrast(photo).enhance(1.15)
            photo = ImageEnhance.Brightness(photo).enhance(0.55)
            base = Image.blend(base, photo, 0.46)
        except Exception:
            pass
    return base


def _split_numbers(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value or "").strip()
    text = re.sub(r"^n[uú]meros?\s*:\s*", "", text, flags=re.I)
    return [p.strip() for p in re.split(r"[,;|\n]+", text) if p.strip()]


def _draw_centered(draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: str, font, fill, anchor="mm", stroke_width=0, stroke_fill=None):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor, stroke_width=stroke_width, stroke_fill=stroke_fill)


def _rounded_panel(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _number_layout(count: int) -> Tuple[int, int, int]:
    if count <= 6:
        return count, 1, 126
    if count <= 10:
        return math.ceil(count / 2), 2, 112
    if count <= 15:
        return 5, 3, 100
    if count <= 20:
        return 5, 4, 88
    return 5, math.ceil(count / 5), 82


def criar_poster(dados: Dict[str, Any], output_path: str | os.PathLike[str]) -> str:
    loteria = str(dados.get("loteria") or dados.get("produto") or "Loteria").strip()
    concurso = str(dados.get("concurso") or "").strip()
    data = str(dados.get("data") or dados.get("data_sorteio") or "").strip()
    numeros = _split_numbers(dados.get("numeros") or dados.get("descricao") or "")
    premio = str(dados.get("premio") or dados.get("estimativa") or "").strip()
    url = str(dados.get("url") or "www.portalsimonsports.com").strip()
    imagem_path = str(dados.get("imagem_path") or "").strip()
    logo_path = str(dados.get("logo_path") or "").strip()
    previa = bool(dados.get("previa", False))

    colors = _palette(loteria, dados.get("cor_fundo_rgb"))
    top, bottom, accent = colors
    img = _load_background(imagem_path, colors).convert("RGBA")

    deco = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    dd.ellipse((-280, -200, 680, 760), fill=(*accent, 25))
    dd.ellipse((580, 1180, 1430, 2080), fill=(255, 255, 255, 16))
    dd.polygon([(0, 1420), (1080, 1100), (1080, 1920), (0, 1920)], fill=(0, 0, 0, 35))
    deco = deco.filter(ImageFilter.GaussianBlur(8))
    img = Image.alpha_composite(img, deco)

    draw = ImageDraw.Draw(img)
    _rounded_panel(draw, (58, 52, 1022, 174), 34, (5, 11, 24, 155), outline=(255, 255, 255, 36), width=2)
    draw.ellipse((86, 78, 148, 140), fill=accent)
    _draw_centered(draw, (117, 110), "S", _font(32, True), bottom)
    draw.text((172, 76), "PORTAL", font=_font(27, True), fill=(255, 255, 255, 215))
    draw.text((172, 107), "SIMONSPORTS", font=_font(42, True), fill=(255, 255, 255, 255))
    draw.text((991, 111), "RESULTADOS", font=_font(24, True), fill=accent, anchor="rm")

    if previa:
        _rounded_panel(draw, (742, 195, 1022, 258), 25, (240, 190, 42, 235))
        _draw_centered(draw, (882, 226), "PRÉVIA DE APROVAÇÃO", _font(20, True), (26, 24, 18))

    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((260, 180), Image.Resampling.LANCZOS)
            img.alpha_composite(logo, ((WIDTH - logo.width) // 2, 205))
        except Exception:
            pass

    title_y = 355 if logo_path and os.path.exists(logo_path) else 292
    _draw_centered(draw, (WIDTH // 2, title_y), loteria.upper(), _font(82, True), (255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 80))

    meta_parts = []
    if concurso:
        meta_parts.append(f"CONCURSO {concurso}")
    if data:
        meta_parts.append(data)
    meta = "  •  ".join(meta_parts) or "RESULTADO OFICIAL"
    _draw_centered(draw, (WIDTH // 2, title_y + 93), meta, _font(33, True), accent)

    panel_top = title_y + 170
    panel_bottom = 1320 if premio else 1435
    _rounded_panel(draw, (55, panel_top, 1025, panel_bottom), 54, (4, 11, 24, 158), outline=(255, 255, 255, 38), width=2)
    _draw_centered(draw, (WIDTH // 2, panel_top + 76), "NÚMEROS SORTEADOS", _font(29, True), (255, 255, 255, 210))

    cols, rows, diameter = _number_layout(max(1, len(numeros)))
    gap_x = 26 if diameter >= 100 else 22
    gap_y = 34 if rows <= 2 else 26
    total_h = rows * diameter + (rows - 1) * gap_y
    content_top = panel_top + 140
    available_h = panel_bottom - content_top - 50
    start_y = content_top + max(0, (available_h - total_h) // 2)

    if not numeros:
        numeros = ["-"]
    for i, number in enumerate(numeros):
        row = i // cols
        col = i % cols
        row_count = min(cols, len(numeros) - row * cols)
        row_w = row_count * diameter + (row_count - 1) * gap_x
        row_start_x = (WIDTH - row_w) // 2
        x = row_start_x + col * (diameter + gap_x)
        y = start_y + row * (diameter + gap_y)

        draw.ellipse((x + 7, y + 12, x + diameter + 7, y + diameter + 12), fill=(0, 0, 0, 78))
        draw.ellipse((x, y, x + diameter, y + diameter), fill=(250, 252, 255, 255), outline=accent, width=max(5, diameter // 18))
        draw.arc((x + 15, y + 13, x + diameter - 15, y + diameter - 13), 205, 334, fill=(255, 255, 255, 220), width=5)
        font_size = 52 if diameter >= 112 else 42 if diameter >= 96 else 34
        if len(number) > 3:
            font_size = max(22, int(font_size * 0.62))
        _draw_centered(draw, (x + diameter // 2, y + diameter // 2 + 2), number, _font(font_size, True), bottom)

    if premio:
        _rounded_panel(draw, (95, 1372, 985, 1545), 42, (*accent, 224))
        _draw_centered(draw, (WIDTH // 2, 1416), "PRÓXIMO PRÊMIO ESTIMADO", _font(24, True), bottom)
        _draw_centered(draw, (WIDTH // 2, 1488), premio, _font(52, True), bottom)
        footer_y = 1618
    else:
        footer_y = 1545

    draw.text((70, footer_y), "Confira o resultado completo", font=_font(34, True), fill=(255, 255, 255))
    draw.text((70, footer_y + 54), "no Portal SimonSports", font=_font(31, False), fill=(255, 255, 255, 210))

    display_url = re.sub(r"^https?://", "", url).split("/")[0] or "www.portalsimonsports.com"
    _rounded_panel(draw, (65, footer_y + 125, 1015, footer_y + 226), 34, (255, 255, 255, 238))
    _draw_centered(draw, (WIDTH // 2, footer_y + 176), display_url, _font(32, True), bottom)
    _draw_centered(draw, (WIDTH // 2, 1865), "Conteúdo informativo • Resultados de loterias", _font(22, False), (255, 255, 255, 165))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, quality=95)
    return str(out)


def _ffmpeg_binary() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("FFmpeg não encontrado no ambiente.")
    return exe


def gerar_video_loteria(dados: Dict[str, Any]) -> str:
    loteria = str(dados.get("loteria") or dados.get("produto") or "loteria").strip()
    concurso = str(dados.get("concurso") or "").strip()
    duracao = max(4.0, min(30.0, float(dados.get("duracao") or DEFAULT_DURATION)))
    fps = int(dados.get("fps") or DEFAULT_FPS)
    output_dir = Path(str(dados.get("output_dir") or "output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_loteria = _slug(loteria) or "loteria"
    safe_concurso = _slug(concurso) or "resultado"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    video_path = output_dir / f"video_{safe_loteria}_{safe_concurso}_{timestamp}.mp4"

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-video-") as tmp:
        poster = Path(tmp) / "poster.png"
        criar_poster(dados, poster)

        frames = max(1, round(duracao * fps))
        fade_out_start = max(0.0, duracao - 0.75)
        vf = (
            f"scale=1188:2112,"
            f"zoompan=z='min(zoom+0.00045,1.055)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={WIDTH}x{HEIGHT}:fps={fps},"
            f"fade=t=in:st=0:d=0.45,fade=t=out:st={fade_out_start:.2f}:d=0.70,format=yuv420p"
        )
        cmd = [
            _ffmpeg_binary(), "-y", "-loop", "1", "-i", str(poster),
            "-vf", vf, "-t", f"{duracao:.2f}", "-r", str(fps),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-movflags", "+faststart", "-an", str(video_path),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Falha no FFmpeg: {proc.stderr[-1800:]}")

    print(f"[VÍDEO] OK: {video_path}", flush=True)
    return str(video_path)


def executar(dados: Dict[str, Any]) -> str:
    """Alias estável usado por post_video.py e pelos workflows existentes."""
    return gerar_video_loteria(dados)
