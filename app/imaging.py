# app/imaging.py — Portal SimonSports
# Rev: 2025-11-14 — Layout bolinhas unificado para todas as loterias
#
# - Fundo em degradê na cor da loteria
# - Logo no topo direito (./assets/logos/slug.png)
# - Título: "<Loteria> <Concurso>"
# - Data do sorteio
# - Números em bolinhas brancas centralizadas
# - Botão amarelo "VER RESULTADO COMPLETO"
# - URL e marca no rodapé
#
# Compatível com:
#   gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url="")
#   render_image(loteria, concurso, data_br, numeros_list, url, out_path, logos_dir, marca="Portal SimonSports")

import os
import io
import math
import re
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ------------------------
# Constantes básicas
# ------------------------
W, H = 1080, 1080  # tamanho quadrado padrão

# ------------------------
# Cores por loteria
# ------------------------
CORES_LOTERIAS = {
    "mega-sena":    (32, 152, 105),
    "quina":        (64, 40, 94),
    "lotofacil":    (149, 55, 148),
    "lotomania":    (243, 112, 33),
    "timemania":    (39, 127, 66),
    "dupla-sena":   (149, 32, 49),
    "federal":      (0, 76, 153),
    "dia-de-sorte": (184, 134, 11),
    "super-sete":   (37, 62, 116),
    "loteca":       (56, 118, 29),  # #38761d
}

def _slug(text: str) -> str:
    s = (text or "").lower().strip()
    s = s.replace("ç", "c")
    s = re.sub(r"[áàâãä]", "a", s)
    s = re.sub(r"[éèêë]", "e", s)
    s = re.sub(r"[íìîï]", "i", s)
    s = re.sub(r"[óòôõö]", "o", s)
    s = re.sub(r"[úùûü]", "u", s)
    s = re.sub(r"[^a-z0-9\- ]+", "", s)
    s = re.sub(r"\s+", "-", s)

    # mapeamentos especiais
    mapa = {
        "lotofácil": "lotofacil",
        "dupla sena": "dupla-sena",
        "dia de sorte": "dia-de-sorte",
        "super sete": "super-sete",
    }
    return mapa.get(s, s)

def _cor_loteria(nome: str):
    return CORES_LOTERIAS.get(_slug(nome), (40, 40, 60))

# ------------------------
# Fontes
# ------------------------
def _load_font(candidates, size):
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()

def _font_regular(size):
    return _load_font(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/Library/Fonts/Arial.ttf",
        ],
        size,
    )

def _font_bold(size):
    return _load_font(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
        ],
        size,
    )

def _font_serif(size):
    return _load_font(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        ],
        size,
    )

# ------------------------
# Fundo / gradiente / vinheta
# ------------------------
def _gradiente_vertical(w, h, top_color, bottom_color):
    base = Image.new("RGB", (w, h), top_color)
    over = Image.new("RGB", (w, h), bottom_color)
    mask = Image.linear_gradient("L").resize((1, h)).resize((w, h))
    return Image.composite(over, base, mask)

def _vinheta(img, strength=220, blur=120):
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    # elipse maior que o quadro para ficar suave
    d.ellipse((-200, -80, w + 200, h + 280), fill=strength)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    return Image.composite(img, Image.new("RGB", (w, h), (0, 0, 0)), mask)

# ------------------------
# Util: logo, chip, texto com sombra
# ------------------------
def _load_logo(logos_dir, loteria_slug):
    if not logos_dir:
        return None
    path = os.path.join(logos_dir, f"{loteria_slug}.png")
    if os.path.exists(path):
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            return None
    return None

def _texto_sombra(draw, x, y, texto, font, fill=(255, 255, 255), shadow=(0, 0, 0), off=2, anchor="la"):
    draw.text((x + off, y + off), texto, font=font, fill=shadow, anchor=anchor)
    draw.text((x, y), texto, font=font, fill=fill, anchor=anchor)

def _chip_numero(numero: int, raio: int, cor, fonte):
    img = Image.new("RGBA", (raio * 2, raio * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # bolinha principal
    d.ellipse((0, 0, raio * 2 - 1, raio * 2 - 1), fill=(255, 255, 255, 255))
    # highlight suave
    hl = Image.new("RGBA", (raio * 2, raio * 2), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(hl)
    d2.ellipse((raio * 0.2, raio * 0.1, raio * 1.8, raio * 1.3), fill=(255, 255, 255, 70))
    img = Image.alpha_composite(img, hl)

    txt = str(numero).zfill(2)
    tw = d.textlength(txt, font=fonte)
    bbox = fonte.getbbox(txt)
    th = bbox[3] - bbox[1]
    d.text((raio - tw / 2, raio - th / 2 - 2), txt, font=fonte, fill=cor)
    return img

# ------------------------
# Layout de números (bolinhas)
# ------------------------
def _layout_bolinhas(canvas, numeros, loteria_slug):
    """
    Desenha as bolinhas de números centralizadas.
    numeros: lista de inteiros
    """
    d = ImageDraw.Draw(canvas)
    n = len(numeros)
    if n == 0:
        return

    # parâmetros gerais
    area_top = 320
    area_bottom = 780
    area_height = area_bottom - area_top
    margin_lr = 90

    # define grid básico (rows x cols)
    if n <= 6:
        rows, cols = 1, n
    elif n <= 10:
        rows, cols = 2, math.ceil(n / 2)
    elif n <= 15:
        rows, cols = 3, 5
    elif n <= 20:
        rows, cols = 4, 5
    else:
        cols = 7
        rows = math.ceil(n / cols)

    # raio dependendo do número de linhas
    if rows == 1:
        r = 90
    elif rows == 2:
        r = 80
    elif rows == 3:
        r = 74
    elif rows == 4:
        r = 68
    else:
        r = 60

    # fonte dos números
    f_num = _font_bold(52 if rows <= 2 else 46)

    # espaço vertical
    total_h = rows * (2 * r) + (rows - 1) * 26
    start_y = area_top + (area_height - total_h) / 2

    idx = 0
    for r_idx in range(rows):
        # números nesta linha
        remaining = n - idx
        line_cols = min(cols, remaining)
        row_w = line_cols * (2 * r) + (line_cols - 1) * 26
        start_x = (W - row_w) / 2

        cy = start_y + r_idx * (2 * r + 26) + r
        cx = start_x + r

        for c_idx in range(line_cols):
            num = numeros[idx]
            chip = _chip_numero(num, r, (0, 0, 0), f_num)
            canvas.paste(chip, (int(cx - r), int(cy - r)), chip)
            cx += 2 * r + 26
            idx += 1

# ------------------------
# CTA botão + URL + marca
# ------------------------
def _draw_cta_url_marca(canvas, url, marca):
    d = ImageDraw.Draw(canvas)

    # botão
    btn_w, btn_h = 760, 100
    bx = (W - btn_w) // 2
    by = 820
    d.rounded_rectangle(
        (bx, by, bx + btn_w, by + btn_h),
        radius=26,
        fill=(255, 215, 0),
        outline=(0, 0, 0),
        width=2,
    )
    f_btn = _font_bold(46)
    txt_btn = "VER RESULTADO COMPLETO"
    tw = d.textlength(txt_btn, font=f_btn)
    d.text((W / 2 - tw / 2, by + (btn_h - 50) / 2), txt_btn, font=f_btn, fill=(0, 0, 0))

    # URL (sem https://)
    if url:
        f_url = _font_regular(34)
        clean = url.replace("https://", "").replace("http://", "")
        tw = d.textlength(clean, font=f_url)
        d.text((W / 2 - tw / 2, by + btn_h + 18), clean, font=f_url, fill=(235, 235, 235))

    # marca
    if marca:
        f_marca = _font_regular(26)
        mw = d.textlength(marca, font=f_marca)
        d.text((W / 2 - mw / 2, H - 54), marca, font=f_marca, fill=(255, 255, 255, 160))

# ------------------------
# Construção principal da imagem
# ------------------------
def _build_canvas(loteria, concurso, data_br, numeros_list, url, logos_dir, marca="Portal SimonSports"):
    lot_slug = _slug(loteria)
    base_cor = _cor_loteria(loteria)

    # gradiente + vinheta
    top = tuple(min(255, int(c * 1.1)) for c in base_cor)
    bottom = tuple(max(0, int(c * 0.6)) for c in base_cor)
    bg = _gradiente_vertical(W, H, top, bottom)
    bg = _vinheta(bg)

    d = ImageDraw.Draw(bg)

    # título + data
    f_title = _font_serif(96)
    f_data = _font_bold(40)

    titulo = f"{loteria} {concurso}".strip()
    _texto_sombra(d, 64, 72, titulo, f_title, fill=(255, 255, 255), shadow=(0, 0, 0), off=3, anchor="la")
    _texto_sombra(d, 64, 170, data_br, f_data, fill=(230, 230, 230), shadow=(0, 0, 0), off=2, anchor="la")

    # logo topo-direito
    logo = _load_logo(logos_dir, lot_slug)
    if logo:
        max_w = 220
        max_h = 140
        logo.thumbnail((max_w, max_h), Image.LANCZOS)
        x = W - 64 - logo.width
        y = 70
        bg.paste(logo, (x, y), logo)

    # grade de bolinhas
    _layout_bolinhas(bg, numeros_list, lot_slug)

    # CTA, URL e marca
    _draw_cta_url_marca(bg, url, marca)

    return bg

# ------------------------
# Função usada pelo bot como fallback (BytesIO)
# ------------------------
def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url=""):
    """
    Função original usada pelo bot quando não utiliza render_image().
    Aqui convertemos numeros_str em lista de ints e chamamos o mesmo layout.
    """
    # extrai inteiros do texto (ignorando palavras como 'Setembro', 'Time do Coração', etc.)
    numeros = [int(x) for x in re.split(r"[^\d]+", numeros_str or "") if x.isdigit()]
    if not numeros:
        # se não achar nada, apenas não desenha bolinhas
        numeros = []

    img = _build_canvas(loteria, concurso, data_br, numeros, url, logos_dir="./assets/logos")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ------------------------
# Função PRO usada pelo bot.py (salva em disco)
# ------------------------
def render_image(loteria, concurso, data_ddmmaa, numeros, url, out_path, logos_dir, marca="Portal SimonSports"):
    """
    Usada pelo bot.py quando disponível (_render_image_pro).
    numeros: lista de inteiros (já tratados no bot)
    """
    numeros_list = list(numeros or [])
    img = _build_canvas(loteria, concurso, data_ddmmaa, numeros_list, url, logos_dir, marca=marca)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "PNG")
    return out_path