# imaging.py — Portal SimonSports
# Rev: 2025-11-18 — Imagem oficial sem botão / sem link interno
# - Mantém layout profissional com:
#   • Logo (opcional)
#   • Nome da loteria
#   • Concurso + data
#   • Números em bolas
#   • Rodapé: apenas "Portal SimonSports"
# - NÃO desenha mais:
#   • Botão "Ver resultado completo"
#   • URL dentro da imagem

import io
import math
from typing import List, Tuple, Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# =========================
# CONFIG GERAL
# =========================

IMG_WIDTH = 1080
IMG_HEIGHT = 1080

BG_COLOR = (10, 12, 28)     # fundo geral (quase preto azulado)
CARD_COLOR = (18, 22, 48)   # cartão central
CARD_RADIUS = 48

TEXT_COLOR = (255, 255, 255)
SUBTEXT_COLOR = (200, 205, 220)
NUM_BG_DEFAULT = (60, 90, 140)

FOOTER_TEXT = "Portal SimonSports"
FOOTER_COLOR = (180, 185, 200)

PADDING = 80

# Se tiver logo em disco, você pode ajustar aqui depois
DEFAULT_LOGO_PATH = None  # ex: "assets/logos/pss.png"

# =========================
# CORES POR LOTERIA
# =========================

CORES_LOTERIAS = {
    # Caixa oficiais aproximadas (RGB)
    "mega-sena": (32, 152, 105),
    "quina": (117, 81, 145),
    "lotofacil": (193, 40, 135),
    "lotofácil": (193, 40, 135),
    "lotomania": (255, 140, 0),
    "timemania": (0, 153, 68),
    "dupla-sena": (170, 0, 0),
    "dupla sena": (170, 0, 0),
    "federal": (0, 102, 179),
    "dia de sorte": (189, 140, 51),
    "dia-de-sorte": (189, 140, 51),
    "super sete": (37, 62, 116),
    "super-sete": (37, 62, 116),
    # Loteca com cor especial pedida
    "loteca": (56, 118, 29),  # #38761d
}

# =========================
# HELPERS DE FONTE
# =========================

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Tenta carregar uma fonte mais bonita; se não encontrar, cai no padrão.
    Você pode alterar os caminhos para fontes específicas do seu ambiente Replit.
    """
    possible = []
    if bold:
        possible = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        possible = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for path in possible:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    # fallback
    return ImageFont.load_default()


# =========================
# HELPERS GRÁFICOS
# =========================

def _rounded_rectangle(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width: int = 1):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=width)


def _center_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, cx: int, y: int, fill):
    w, h = draw.textbbox((0, 0), text, font=font)[2:]
    draw.text((cx - w // 2, y), text, font=font, fill=fill)


def _split_numeros(numeros_str: str) -> List[str]:
    if not numeros_str:
        return []
    tmp = (
        numeros_str.replace(";", ",")
        .replace("|", ",")
        .replace("  ", " ")
        .replace("–", "-")
    )
    parts = [p.strip() for p in tmp.replace(" ", ",").split(",") if p.strip()]
    # Mantém ordem, remove duplicados simples
    seen = set()
    result = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def _get_cor_loteria(nome: str) -> Tuple[int, int, int]:
    if not nome:
        return NUM_BG_DEFAULT
    key = nome.strip().lower()
    for k, v in CORES_LOTERIAS.items():
        if k in key:
            return v
    return NUM_BG_DEFAULT


def _desenhar_bolinhas(
    draw: ImageDraw.ImageDraw,
    area_xy,
    numeros: List[str],
    cor_base: Tuple[int, int, int],
    fonte_num: ImageFont.FreeTypeFont,
):
    """
    Desenha as bolinhas com os números na área fornecida (x1,y1,x2,y2).
    Tenta organizar em 1 ou 2 linhas de forma equilibrada.
    """
    if not numeros:
        return

    x1, y1, x2, y2 = area_xy
    largura = x2 - x1
    altura = y2 - y1

    n = len(numeros)
    # definimos tamanho de bola aproximado em função da quantidade
    if n <= 6:
        r = 64
    elif n <= 10:
        r = 52
    elif n <= 15:
        r = 44
    else:
        r = 40

    di = r * 2
    margem_h = 16

    # decide linhas
    if n <= 7:
        linhas = [numeros]
    else:
        metade = math.ceil(n / 2)
        linhas = [numeros[:metade], numeros[metade:]]

    total_linhas = len(linhas)
    if total_linhas == 1:
        linhas_y = [y1 + (altura - di) // 2]
    else:
        gap_linha = (altura - total_linhas * di) // (total_linhas + 1)
        linhas_y = []
        yy = y1 + gap_linha
        for _ in range(total_linhas):
            linhas_y.append(yy)
            yy += di + gap_linha

    for line_idx, linha in enumerate(linhas):
        k = len(linha)
        if k == 0:
            continue
        total_larg_bolas = k * di + (k - 1) * margem_h
        start_x = x1 + (largura - total_larg_bolas) // 2
        y = linhas_y[line_idx]

        for i, num in enumerate(linha):
            cx = start_x + i * (di + margem_h) + r
            cy = y + r
            # círculo
            draw.ellipse(
                (cx - r, cy - r, cx + r, cy + r),
                fill=cor_base,
            )
            # contorno suave
            outline = tuple(max(0, c - 25) for c in cor_base)
            draw.ellipse(
                (cx - r, cy - r, cx + r, cy + r),
                outline=outline,
                width=3,
            )

            # número centralizado
            tw, th = draw.textbbox((0, 0), num, font=fonte_num)[2:]
            draw.text(
                (cx - tw // 2, cy - th // 2),
                num,
                font=fonte_num,
                fill=(255, 255, 255),
            )


def _carregar_logo(path: Optional[str], tamanho_max: int = 120) -> Optional[Image.Image]:
    if not path:
        return None
    try:
        logo = Image.open(path).convert("RGBA")
        w, h = logo.size
        scale = min(tamanho_max / w, tamanho_max / h)
        if scale < 1:
            logo = logo.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        return logo
    except Exception:
        return None


# =========================
# GERADOR PRINCIPAL
# =========================

def gerar_imagem_loteria(
    nome_loteria: str,
    concurso: str,
    data_str: str,
    numeros_str: str,
    url_resultado: str = "",
) -> io.BytesIO:
    """
    Gera imagem oficial da loteria em PNG dentro de um BytesIO,
    pronta para ser enviada pelo bot.
    Não escreve botão, não escreve URL. Apenas:
      - logo (se houver)
      - nome da loteria
      - concurso + data
      - números em bolas
      - rodapé "Portal SimonSports"
    """

    # Normalizações básicas
    nome_loteria = (nome_loteria or "").strip()
    concurso = (concurso or "").strip()
    data_str = (data_str or "").strip()
    numeros = _split_numeros(numeros_str or "")

    cor_loteria = _get_cor_loteria(nome_loteria)

    # Cria base
    img = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Leve vinheta / blur de fundo (cartão central depois)
    overlay = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), BG_COLOR)
    blur = overlay.filter(ImageFilter.GaussianBlur(radius=40))
    img = Image.blend(img, blur, alpha=0.35)
    draw = ImageDraw.Draw(img)

    # Card central
    card_x1 = PADDING
    card_x2 = IMG_WIDTH - PADDING
    card_y1 = PADDING
    card_y2 = IMG_HEIGHT - PADDING
    _rounded_rectangle(draw, (card_x1, card_y1, card_x2, card_y2), CARD_RADIUS, fill=CARD_COLOR)

    # Faixa superior colorida
    faixa_alt = 90
    _rounded_rectangle(
        draw,
        (card_x1, card_y1, card_x2, card_y1 + faixa_alt),
        radius=CARD_RADIUS,
        fill=cor_loteria,
    )

    # Títulos / fontes
    font_titulo = _load_font(54, bold=True)
    font_sub = _load_font(32, bold=False)
    font_concurso = _load_font(30, bold=False)
    font_numeros = _load_font(44, bold=True)
    font_footer = _load_font(28, bold=False)

    center_x = IMG_WIDTH // 2

    # LOGO (opcional) — lado esquerdo
    logo = _carregar_logo(DEFAULT_LOGO_PATH, tamanho_max=120)
    titulo_y = card_y1 + 16
    if logo:
        lw, lh = logo.size
        logo_x = card_x1 + 32
        logo_y = card_y1 + (faixa_alt - lh) // 2
        img.paste(logo, (logo_x, logo_y), logo)
        # Título deslocado um pouco à direita
        titulo_cx = center_x + int(lw * 0.2)
    else:
        titulo_cx = center_x

    # Nome da loteria na faixa
    nome_exibicao = nome_loteria or "Resultado da Loteria"
    _center_text(draw, nome_exibicao, font_titulo, titulo_cx, titulo_y, fill=(255, 255, 255))

    # Subtítulo concurso + data (logo abaixo da faixa)
    subt_y = card_y1 + faixa_alt + 24
    if concurso or data_str:
        if concurso and data_str:
            subt = f"Concurso {concurso} · {data_str}"
        elif concurso:
            subt = f"Concurso {concurso}"
        else:
            subt = data_str
        _center_text(draw, subt, font_concurso, center_x, subt_y, fill=SUBTEXT_COLOR)

    # Área dos números (centro do card)
    numeros_area_top = subt_y + 80
    numeros_area_bottom = card_y2 - 140  # deixa espaço para rodapé interno
    _desenhar_bolinhas(
        draw,
        (card_x1 + 60, numeros_area_top, card_x2 - 60, numeros_area_bottom),
        numeros,
        cor_loteria,
        font_numeros,
    )

    # Rodapé interno: apenas linha divisória sutil (opcional)
    # (Deixamos limpo para a imagem respirar)

    # Rodapé externo: "Portal SimonSports" — ÚNICO texto de marca
    footer_y = IMG_HEIGHT - PADDING - 10
    _center_text(draw, FOOTER_TEXT, font_footer, center_x, footer_y, fill=FOOTER_COLOR)

    # Exporta para BytesIO
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf