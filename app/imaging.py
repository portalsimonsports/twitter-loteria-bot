# app/imaging.py — Portal SimonSports
# Rev: 2025-11-13 — Layout tipo “bolinhas” (inspirado no print 2)
#
# Funções públicas:
#   gerar_imagem_loteria(loteria, concurso, data_str, numeros_str, url_res) -> BytesIO
#   render_image(loteria, concurso, data_str, numeros_list, url_res, out_path, logos_dir) -> salva PNG
#
# Observações:
#   - Tamanho: 1080x1080 (quadrado, bom para X/Instagram)
#   - Fundo na cor oficial da loteria (quando encontrada)
#   - Números em círculos brancos, com quebra em 1 ou 2 linhas
#   - Texto “Ver resultado completo no Portal SimonSports” perto do rodapé
#   - “PORTAL SIMONSPORTS” em destaque no rodapé
#   - Se o logo existir em LOGOS_DIR/slug.png, ele aparece no topo à direita

import os
import io
import re
from typing import List, Tuple, Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# =========================
# Config / Constantes
# =========================

WIDTH, HEIGHT = 1080, 1080

# Cores oficiais aproximadas das loterias (RGB)
CORES_LOTERIAS = {
    "mega-sena":    (32, 152, 105),
    "quina":        (80, 43, 136),
    "lotofacil":    (198, 33, 104),
    "lotofácil":    (198, 33, 104),
    "lotomania":    (243, 118, 33),
    "timemania":    (0, 153, 68),
    "dupla-sena":   (141, 0, 28),
    "dupla sena":   (141, 0, 28),
    "federal":      (0, 87, 159),
    "dia-de-sorte": (213, 143, 34),
    "dia de sorte": (213, 143, 34),
    "super-sete":   (37, 62, 116),
    "super sete":   (37, 62, 116),
    "loteca":       (56, 118, 29),
}

# Diretório padrão de logos (pode ser sobrescrito via env)
LOGOS_DIR_DEFAULT = os.getenv("LOGOS_DIR", "./assets/logos").strip() or "./assets/logos"


# =========================
# Helpers de texto / cores
# =========================

def _slugify(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[áàâãä]", "a", s)
    s = re.sub(r"[éèêë]", "e", s)
    s = re.sub(r"[íìîï]", "i", s)
    s = re.sub(r"[óòôõö]", "o", s)
    s = re.sub(r"[úùûü]", "u", s)
    s = re.sub(r"ç", "c", s)
    s = re.sub(r"[^a-z0-9\- ]+", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s or "loteria"


def _guess_slug(loteria: str) -> str:
    p = (loteria or "").lower()
    for k in CORES_LOTERIAS.keys():
        if k in p:
            return k
    return _slugify(loteria or "loteria")


def _get_loteria_color(loteria: str) -> Tuple[int, int, int]:
    slug = _guess_slug(loteria)
    return CORES_LOTERIAS.get(slug, (32, 32, 32))


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Tenta carregar uma fonte 'decente'. Se não achar, cai na default do Pillow.
    """
    candidates = []
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "DejaVuSans-Bold.ttf",
            "arialbd.ttf",
            "Arial Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "DejaVuSans.ttf",
            "arial.ttf",
            "Arial.ttf",
        ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    # fallback
    return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, y: int, font: ImageFont.FreeTypeFont, fill=(255, 255, 255)):
    w, h = draw.textsize(text, font=font)
    x = (WIDTH - w) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _load_logo(loteria: str, logos_dir: Optional[str] = None) -> Optional[Image.Image]:
    logos_dir = logos_dir or LOGOS_DIR_DEFAULT
    slug = _guess_slug(loteria)
    if not os.path.isdir(logos_dir):
        return None
    # tenta slug.png / slug.jpg
    for ext in (".png", ".jpg", ".jpeg"):
        path = os.path.join(logos_dir, slug + ext)
        if os.path.exists(path):
            try:
                img = Image.open(path).convert("RGBA")
                return img
            except Exception:
                return None
    return None


# =========================
# Layout principal
# =========================

def _draw_background(img: Image.Image, base_color: Tuple[int, int, int]):
    """
    Fundo em leve gradiente radial escurecendo nas bordas.
    """
    r, g, b = base_color
    base = Image.new("RGB", (WIDTH, HEIGHT), (r, g, b))
    overlay = Image.new("L", (WIDTH, HEIGHT), 0)
    ov_draw = ImageDraw.Draw(overlay)

    max_radius = int((WIDTH + HEIGHT) / 1.5)
    center = (WIDTH // 2, HEIGHT // 2)

    for i in range(max_radius, 0, -20):
        alpha = int(255 * (i / max_radius) ** 2 * 0.6)
        bbox = [
            center[0] - i,
            center[1] - i,
            center[0] + i,
            center[1] + i,
        ]
        ov_draw.ellipse(bbox, fill=alpha)

    overlay = overlay.filter(ImageFilter.GaussianBlur(80))
    img.paste(base, (0, 0))
    img.putalpha(255)
    img = Image.composite(img, Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 200)), overlay)
    return img.convert("RGB")


def _layout_header(draw: ImageDraw.ImageDraw, loteria: str, concurso: str, data_str: str, base_color: Tuple[int, int, int], logos_dir: Optional[str]):
    title_font = _load_font(72, bold=True)
    sub_font   = _load_font(38, bold=False)

    loteria_txt = (loteria or "").upper().strip()
    concurso_txt = f"Concurso {concurso}".strip() if concurso else ""
    data_txt = data_str.strip() if data_str else ""

    # Título à esquerda
    margin_left = 90
    y = 110

    draw.text((margin_left, y), loteria_txt, font=title_font, fill=(255, 255, 255))
    tw, th = draw.textsize(loteria_txt, font=title_font)

    if concurso_txt:
        y2 = y + th + 10
        draw.text((margin_left, y2), concurso_txt, font=sub_font, fill=(230, 230, 230))
        _, sh = draw.textsize(concurso_txt, font=sub_font)
    else:
        y2 = y + th
        sh = 0

    if data_txt:
        y3 = y2 + sh + 6
        draw.text((margin_left, y3), data_txt, font=sub_font, fill=(230, 230, 230))

    # Logo no topo direito (se existir)
    logo = _load_logo(loteria, logos_dir)
    if logo:
        target_h = 110
        ratio = target_h / logo.height
        new_w = int(logo.width * ratio)
        logo = logo.resize((new_w, target_h), Image.LANCZOS)
        x_logo = WIDTH - new_w - 80
        y_logo = 80
        img_rgba = logo.convert("RGBA")
        draw_im = draw.im  # PIL internals
        # desenhar via paste
        bg = draw_im  # type: ignore
        base_img = Image.frombytes("RGBA", bg.size, bg.tobytes())
        base_img.paste(img_rgba, (x_logo, y_logo), img_rgba)
        draw_im.frombytes(base_img.tobytes())


def _split_numbers_tokens(numeros_str: str) -> List[str]:
    if not numeros_str:
        return []
    # separa por vírgula, ponto-e-vírgula, espaço
    tokens = re.split(r"[,\s;]+", numeros_str)
    return [t for t in tokens if t.strip()]


def _layout_bolinhas(draw: ImageDraw.ImageDraw, numeros_str: str):
    tokens = _split_numbers_tokens(numeros_str)
    if not tokens:
        return

    # Limita exageros visuais para 20 itens
    tokens = tokens[:20]

    # duas linhas no máximo
    max_por_linha = 10
    linhas = [tokens[i:i + max_por_linha] for i in range(0, len(tokens), max_por_linha)]
    if len(linhas) > 2:
        linhas = linhas[:2]

    n_linhas = len(linhas)
    # área central aproximada
    top_area = 360
    available_height = 360
    line_spacing = available_height // (n_linhas + 1)

    # raio baseado no maior comprimento da linha
    max_len = max(len(l) for l in linhas)
    total_padding = 2 * (max_len + 1)  # espaços entre círculos
    max_diameter = min(120, WIDTH // (max_len + 2))
    radius = max(40, min(60, max_diameter // 2))

    font = _load_font(40, bold=True)

    for li, linha_tokens in enumerate(linhas):
        y_center = top_area + (li + 1) * line_spacing
        n = len(linha_tokens)
        if n <= 0:
            continue

        total_width = n * (2 * radius) + (n - 1) * 20
        start_x = (WIDTH - total_width) // 2

        for idx, tok in enumerate(linha_tokens):
            x_center = start_x + radius + idx * (2 * radius + 20)
            # círculo
            bbox = [
                x_center - radius,
                y_center - radius,
                x_center + radius,
                y_center + radius,
            ]
            draw.ellipse(bbox, fill=(255, 255, 255), outline=(230, 230, 230), width=3)

            num_txt = tok
            tw, th = draw.textsize(num_txt, font=font)
            tx = x_center - tw // 2
            ty = y_center - th // 2 - 2
            draw.text((tx, ty), num_txt, font=font, fill=(0, 0, 0))


def _layout_footer(draw: ImageDraw.ImageDraw, url_res: str):
    small_font = _load_font(30, bold=False)
    big_font   = _load_font(42, bold=True)

    # texto "Ver resultado completo..."
    txt1 = "↻ Ver resultado completo no Portal SimonSports"
    w1, h1 = draw.textsize(txt1, font=small_font)
    x1 = (WIDTH - w1) // 2
    y1 = HEIGHT - 220
    draw.text((x1, y1), txt1, font=small_font, fill=(245, 245, 245))

    # URL (se tiver)
    if url_res:
        w2, h2 = draw.textsize(url_res, font=small_font)
        x2 = (WIDTH - w2) // 2
        y2 = y1 + h1 + 8
        draw.text((x2, y2), url_res, font=small_font, fill=(230, 230, 230))

    # "PORTAL SIMONSPORTS"
    txt_brand = "PORTAL SIMONSPORTS"
    w3, h3 = draw.textsize(txt_brand, font=big_font)
    x3 = (WIDTH - w3) // 2
    y3 = HEIGHT - 120
    draw.text((x3, y3), txt_brand, font=big_font, fill=(255, 255, 255))


# =========================
# Funções públicas
# =========================

def gerar_imagem_loteria(loteria: str, concurso: str, data_str: str, numeros_str: str, url_res: str):
    """
    Gera a imagem padrão em memória (BytesIO) a partir dos dados da loteria.
    Usada diretamente pelo bot.py atual.
    """
    base_color = _get_loteria_color(loteria)
    img = Image.new("RGB", (WIDTH, HEIGHT), base_color)
    img = _draw_background(img, base_color)

    draw = ImageDraw.Draw(img)

    _layout_header(draw, loteria, concurso, data_str, base_color, LOGOS_DIR_DEFAULT)
    _layout_bolinhas(draw, numeros_str)
    _layout_footer(draw, url_res)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def render_image(loteria: str, concurso: str, data_str: str, numeros_list: List[int], url_res: str, out_path: str, logos_dir: str = None):
    """
    Versão “PRO” que salva a imagem em disco.
    Útil para o bot novo (quando você quiser usar de novo).
    """
    numeros_str = ", ".join(str(n) for n in numeros_list) if numeros_list else ""
    base_color = _get_loteria_color(loteria)
    img = Image.new("RGB", (WIDTH, HEIGHT), base_color)
    img = _draw_background(img, base_color)

    draw = ImageDraw.Draw(img)
    _layout_header(draw, loteria, concurso, data_str, base_color, logos_dir or LOGOS_DIR_DEFAULT)
    _layout_bolinhas(draw, numeros_str)
    _layout_footer(draw, url_res)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, format="PNG", optimize=True)