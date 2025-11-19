# app/imaging.py — Geração de imagem oficial das Loterias
# Rev: 2025-11-19 — Corrigido Pillow 10+ e SyntaxError resolvido
#                    Sem botão "Ver resultado", sem URL na imagem
#                    Rodapé com "Portal SimonSports" centralizado

import io
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont


# =========================
# CORES POR LOTERIA
# =========================

CORES_LOTERIAS = {
    "mega-sena": (32, 152, 105),
    "quina": (94, 54, 139),
    "lotofacil": (212, 0, 120),
    "lotofácil": (212, 0, 120),
    "lotomania": (242, 144, 0),
    "timemania": (0, 128, 0),
    "dupla sena": (153, 0, 51),
    "dupla-sena": (153, 0, 51),
    "federal": (0, 84, 150),
    "dia de sorte": (178, 120, 50),
    "dia-de-sorte": (178, 120, 50),
    "super sete": (37, 62, 116),
    "super-sete": (37, 62, 116),
    "loteca": (56, 118, 29),
}

COR_FUNDO_PADRAO = (25, 25, 35)
COR_TEXTO_CLARO = (255, 255, 255)
COR_TEXTO_SUAVE = (230, 230, 240)

IMG_LARGURA = 1080
IMG_ALTURA = 1080


# =========================
# HELPERS
# =========================

def _normaliza_loteria(nome: str) -> str:
    return (nome or "").strip().lower()


def _cor_para_loteria(nome: str) -> Tuple[int, int, int]:
    key = _normaliza_loteria(nome)
    for k, v in CORES_LOTERIAS.items():
        if k in key:
            return v
    return (100, 100, 100)  # fallback


def _carregar_fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    tentativas = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/system/fonts/Roboto-Bold.ttf",
        "/system/fonts/DroidSans-Bold.ttf",
    ]
    for caminho in tentativas:
        try:
            return ImageFont.truetype(caminho, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def _tamanho_texto(draw: ImageDraw.Draw, texto: str, fonte: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    """Compatível com Pillow ≥ 10 (textsize foi removido)"""
    bbox = draw.textbbox((0, 0), texto, font=fonte)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _quebrar_texto(draw: ImageDraw.Draw, texto: str, fonte: ImageFont.FreeTypeFont, largura_max: int):
    palavras = (texto or "").split()
    if not palavras:
        return [""]

    linhas = []
    linha_atual = palavras[0]

    for palavra in palavras[1:]:
        teste = linha_atual + " " + palavra
        w, _ = _tamanho_texto(draw, teste, fonte)
        if w <= largura_max:
            linha_atual = teste
        else:
            linhas.append(linha_atual)
            linha_atual = palavra
    linhas.append(linha_atual)
    return linhas


def _desenhar_circulo_com_texto(
    draw: ImageDraw.Draw,
    cx: float,
    cy: float,
    raio: int,
    texto: str,
    fonte: ImageFont.FreeTypeFont,
    cor_fundo: Tuple[int, int, int],
    cor_texto: Tuple[int, int, int],
):
    """Desenha círculo com número centralizado"""
    draw.ellipse((cx - raio, cy - raio, cx + raio, cy + raio), fill=cor_fundo)
    tw, th = _tamanho_texto(draw, texto, fonte)
    draw.text((cx - tw / 2, cy - th / 2), texto, font=fonte, fill=cor_texto)


# =========================
# FUNÇÃO PRINCIPAL
# =========================

def gerar_imagem_loteria(
    loteria: str,
    concurso: str,
    data_br: str,
    numeros_str: str,
    url_res: str = "",
) -> io.BytesIO:
    loteria = (loteria or "").strip()
    concurso = (concurso or "").strip()
    data_br = (data_br or "").strip()
    numeros_str = (numeros_str or "").strip()

    cor_base = _cor_para_loteria(loteria)

    img = Image.new("RGB", (IMG_LARGURA, IMG_ALTURA), COR_FUNDO_PADRAO)
    draw = ImageDraw.Draw(img)

    # Gradiente de fundo
    for y in range(IMG_ALTURA):
        fator = y / IMG_ALTURA
        r = int(COR_FUNDO_PADRAO[0] * (1 - fator) + cor_base[0] * fator)
        g = int(COR_FUNDO_PADRAO[1] * (1 - fator) + cor_base[1] * fator)
        b = int(COR_FUNDO_PADRAO[2] * (1 - fator) + cor_base[2] * fator)
        draw.line([(0, y), (IMG_LARGURA, y)], fill=(r, g, b))

    # Fontes
    fonte_titulo = _carregar_fonte(80)
    fonte_sub = _carregar_fonte(42)
    fonte_num = _carregar_fonte(60)
    fonte_rodape = _carregar_fonte(38)

    margem = 80
    y = 120

    # Título
    titulo = loteria.upper() if loteria else "LOTARIA"
    for linha in _quebrar_texto(draw, titulo, fonte_titulo, IMG_LARGURA - 2 * margem):
        w, h = _tamanho_texto(draw, linha, fonte_titulo)
        draw.text(((IMG_LARGURA - w) / 2, y), linha, font=fonte_titulo, fill=COR_TEXTO_CLARO)
        y += h + 5

    # Subtítulo
    partes = []
    if concurso:
        partes.append(f"Concurso {concurso}")
    if data_br:
        partes.append(f"({data_br})")
    subtitulo = " — ".join(partes)

    if subtitulo:
        w, h = _tamanho_texto(draw, subtitulo, fonte_sub)
        draw.text(((IMG_LARGURA - w) / 2, y + 30), subtitulo, font=fonte_sub, fill=COR_TEXTO_SUAVE)
        y += h + 80
    else:
        y += 80

    # Números
    numeros = [n.strip() for n in numeros_str.replace(";", ",").replace(" ", ",").split(",") if n.strip()]
    if numeros:
        max_por_linha = 8
        linhas = [numeros[i:i + max_por_linha] for i in range(0, len(numeros), max_por_linha)]
        raio = 55
        esp_h = 20
        esp_v = 35

        area_top = y
        area_bottom = IMG_ALTURA - 220
        altura_total = len(linhas) * (2 * raio) + (len(linhas) - 1) * esp_v
        inicio_y = area_top + (area_bottom - area_top - altura_total) / 2

        for i, linha in enumerate(linhas):
            largura_linha = len(linha) * (2 * raio) + (len(linha) - 1) * esp_h
            inicio_x = (IMG_LARGURA - largura_linha) / 2
            cy = inicio_y + i * (2 * raio + esp_v)

            for j, num in enumerate(linha):
                cx = inicio_x + j * (2 * raio + esp_h)
                _desenhar_circulo_com_texto(draw, cx, cy, raio, num, fonte_num,
                                            cor_fundo=(255, 255, 255), cor_texto=(0, 0, 0))

    # Rodapé
    rodape_y = IMG_ALTURA - 120
    draw.rectangle((0, rodape_y, IMG_LARGURA, IMG_ALTURA), fill=(10, 10, 18))
    texto = "Portal SimonSports"
    w, h = _tamanho_texto(draw, texto, fonte_rodape)
    draw.text(((IMG_LARGURA - w) / 2, rodape_y + (120 - h) / 2), texto, font=fonte_rodape, fill=COR_TEXTO_CLARO)

    # Exportar
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf