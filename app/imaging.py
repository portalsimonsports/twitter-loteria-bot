# -*- coding: utf-8 -*-
"""
Geração de imagem 3D de resultados de loterias
- Logo central (se disponível)
- Título, data, números em bolas 3D e link
- Paleta e logos vêm de app/palette.py
"""

import io
import math
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .palette import CORES_LOTERIAS, LOGOS_LOTERIAS, NUMEROS_POR_LOTERIA, norm_key

# --------- util: fontes robustas ----------
def _font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        # fallback seguro para runners do GitHub
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()

def _font_bold(size: int):
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "arialbd.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

# --------- util: download de logo ----------
def _download_logo(url: str, timeout=10):
    if not url:
        return None
    try:
        r = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Twitter-Loterias Bot)"},
        )
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        return None

# --------- render da bola 3D ----------
def _bola_3d(cor_rgb, raio=64):
    w = h = raio * 2 + 36
    bola = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(bola)

    # gradiente radial fake
    for j in range(raio):
        k = 1.0 - (j / raio) * 0.55
        fill = tuple(int(c * k) for c in cor_rgb) + (255,)
        d.ellipse((j, j, w - j - 1, h - j - 1), fill=fill)

    # brilho
    brilho = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(brilho).ellipse((24, 18, 58, 52), fill=(255, 255, 255, 170))
    bola = Image.alpha_composite(bola, brilho)

    # sombra
    sombra = bola.filter(ImageFilter.GaussianBlur(12))
    return bola, sombra

def gerar_imagem_loteria(
    loteria: str,
    concurso: str,
    data_br: str,
    numeros_str: str,
    url_resultado: str = "",
    largura: int = 1080,
    altura: int = 1080,
):
    """Retorna um BytesIO PNG com a imagem do resultado."""

    loteria_norm = norm_key(loteria)
    cor_hex = CORES_LOTERIAS.get(loteria_norm, "#4B0082")
    cor_rgb = tuple(int(cor_hex.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    logo_url = LOGOS_LOTERIAS.get(loteria_norm)

    # Canvas base
    img = Image.new("RGB", (largura, altura), color=cor_hex)
    draw = ImageDraw.Draw(img)

    # Cartão central com sombra
    card = Image.new("RGBA", (largura - 120, altura - 120), (255, 255, 255, 255))
    sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sombra)
    rect = (60, 60, largura - 60, altura - 60)
    sd.rounded_rectangle(rect, radius=28, fill=(0, 0, 0, 110))
    sombra = sombra.filter(ImageFilter.GaussianBlur(12))
    img = Image.alpha_composite(img.convert("RGBA"), sombra).convert("RGB")
    img.paste(card, (60, 60))

    # Logo (opcional)
    y = 90
    logo = _download_logo(logo_url)
    if logo:
        # limitar tamanho
        logo.thumbnail((440, 200), Image.Resampling.LANCZOS)
        x_logo = (largura - logo.width) // 2
        img.paste(logo, (x_logo, y), logo)
        y += logo.height + 16
    else:
        y += 20

    # Títulos
    fonte_titulo = _font_bold(68)
    fonte_sub = _font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
    cx = largura // 2
    draw = ImageDraw.Draw(img)
    draw.text((cx, y), f"{loteria.upper()} — CONCURSO {concurso}", fill="#0f172a", font=fonte_titulo, anchor="ma")
    y += 86
    draw.text((cx, y), f"{data_br}", fill="#475569", font=fonte_sub, anchor="ma")
    y += 60

    # Números
    max_nums = NUMEROS_POR_LOTERIA.get(loteria_norm, 6)
    numeros = [n.strip() for n in str(numeros_str).replace(";", ",").replace(" ", ",").split(",") if n.strip()]
    if not numeros:
        numeros = ["?"] * max_nums

    # Quebra automática em linhas (até 7 por linha para caber lotofácil)
    por_linha = 7 if len(numeros) > 10 else min(len(numeros), 6)
    linhas = math.ceil(len(numeros) / por_linha)

    raio = 58
    esp = 120
    fonte_num = _font_bold(54)

    for li in range(linhas):
        start = li * por_linha
        fim = min(len(numeros), (li + 1) * por_linha)
        linha = numeros[start:fim]
        total_w = len(linha) * esp
        x_ini = (largura - total_w) // 2 + esp // 2
        y_linha = y + li * 160 + 10

        for i, num in enumerate(linha):
            x = x_ini + i * esp
            bola, sombra_bola = _bola_3d(cor_rgb, raio)
            img.paste((0, 0, 0, 60), (x - 18, y_linha + 12), sombra_bola)
            img.paste(bola, (x - (raio + 18), y_linha - (raio + 18)), bola)

            # número com leve "stroke" branco
            txt_img = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
            td = ImageDraw.Draw(txt_img)
            td.text((80, 74), str(num), font=fonte_num, fill=(0, 0, 0, 210), anchor="mm")
            td.text((78, 72), str(num), font=fonte_num, fill=(255, 255, 255, 255), anchor="mm")
            img.paste(txt_img, (x - 80, y_linha - 80), txt_img)

    y += linhas * 160 + 10

    # Link
    if url_resultado:
        y += 6
        draw.text((cx, y), "Resultado completo", fill="#0f172a", font=fonte_sub, anchor="ma")
        y += 48
        fonte_link = _font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        draw.text((cx, y), url_resultado, fill="#0ea5e9", font=fonte_link, anchor="ma")

    # Assinatura
    draw.text((largura - 78, altura - 70), "Portal SimonSports", fill="#0f172a", font=_font_bold(28), anchor="ra")

    # Pequena suavização
    out = img.filter(ImageFilter.GaussianBlur(0.2))
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf