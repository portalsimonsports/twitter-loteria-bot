# app/imaging.py — Geração de imagem oficial das Loterias
# Rev: 2025-11-19 — Corrigido para Pillow 10+ (textsize removido)
#                    Sem botão "Ver resultado", sem URL na imagem
#                    Rodapé com "Portal SimonSports" centralizado

import io
import math
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
    return (100, 100, 100)  # fallback mais visível que o fundo padrão


def _carregar_fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    fontes_tentativa = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in fontes_tentativa:
        try:
            return ImageFont.truetype(path, tamanho)
        except Exception:
            continue
    return ImageFont.load_default()


def _tamanho_texto(draw: ImageDraw.Draw, texto: str, fonte: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    """
    Compatível com Pillow ≥ 10 (textsize foi removido)
    """
    if hasattr(draw, "textbbox"):  # Pillow 8+
        bbox = draw.textbbox((0, 0), texto, font=fonte)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    else:
        # fallback para versões muito antigas (quase nunca usado)
        return fonte.getsize(texto)


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
    cx: float, cy: float,
    r: int,
    texto: str,
    fonte: ImageFont.FreeTypeFont,
 tw, th = _tamanho_texto(draw, texto, fonte)
    tx = cx - tw / 2
    ty = cy - th / 2
    draw.text((tx, ty), texto, font=fonte, fill=cor_texto)


# =========================
# FUNÇÃO PRINCIPAL
# =========================

def gerar_imagem_loteria(loteria: str, concurso: str, data_br: str, numeros_str: str, url_res: str = "") -> io.BytesIO:
    loteria = (loteria or "").strip()
    concurso = (concurso or "").strip()
    data_br = (data_br or "").strip()
    numeros_str = (numeros_str or "").strip()

    cor_base = _cor_para_loteria(loteria)

    img = Image.new("RGB", (IMG_LARGURA, IMG_ALTURA), COR_FUNDO_PADRAO)
    draw = ImageDraw.Draw(img)

    # Gradiente suave de fundo
    for y in range(IMG_ALTURA):
        fator = y / IMG_ALTURA
        r = int(COR_FUNDO_PADRAO[0] * (1 - fator) + cor_base[0] * fator)
        g = int(COR_FUNDO_PADRAO[1] * (1 - fator) + cor_base[1] * fator)
        b = int(COR_FUNDO_PADRAO[2] * (1 - fator) + cor_base[2] * fator)
        draw.line([(0, y), (IMG_LARGURA, y)], fill=(r, g, b))

    # Fontes
    fonte_titulo = _carregar_fonte(80)
    fonte_sub = _carregar_fonte(42)
    fonte_numeros = _carregar_fonte(60)
    fonte_rodape = _carregar_fonte(38)

    margem_lateral = 80
    y_cursor = 120

    # Título da loteria
    titulo = loteria.upper() if loteria else "LOTARIA"
    linhas_titulo = _quebrar_texto(draw, titulo, fonte_titulo, IMG_LARGURA - 2 * margem_lateral)

    for linha in linhas_titulo:
        w, h = _tamanho_texto(draw, linha, fonte_titulo)
        x = (IMG_LARGURA - w) / 2
        draw.text((x, y_cursor), linha, font=fonte_titulo, fill=COR_TEXTO_CLARO)
        y_cursor += h + 5

    # Subtítulo (Concurso + data)
    subtitulo_parts = []
    if concurso:
        subtitulo_parts.append(f"Concurso {concurso}")
    if data_br:
        subtitulo_parts.append(f"({data_br})")
    subtitulo = " — ".join(subtitulo_parts)

    if subtitulo:
        w, h = _tamanho_texto(draw, subtitulo, fonte_sub)
        x = (IMG_LARGURA - w) / 2
        draw.text((x, y_cursor + 30), subtitulo, font=fonte_sub, fill=COR_TEXTO_SUAVE)
        y_cursor += h + 80
    else:
        y_cursor += 80

    # Números em círculos
    numeros = [n.strip() for n in numeros_str.replace(";", ",").replace(" ", ",").split(",") if n.strip()]

    if numeros:
        max_por_linha = 8
        linhas_numeros = [numeros[i:i + max_por_linha] for i in range(0, len(numeros), max_por_linha)]

        raio = 55
        espaco_h = 20
        espaco_v = 35

        area_top = y_cursor
        area_bottom = IMG_ALTURA - 220
        total_altura = len(linhas_numeros) * (2 * raio) + (len(linhas_numeros) - 1) * espaco_v
        inicio_y = area_top + (area_bottom - area_top - total_altura) / 2

        for idx_linha, linha in enumerate(linhas_numeros):
            n_cols = len(linha)
            largura_linha = n_cols * (2 * raio) + (n_cols - 1) * espaco_h
            inicio_x = (IMG_LARGURA - largura_linha) / 2
            cy = inicio_y + idx_linha * (2 * raio + espaco_v)

            for idx_col, num in enumerate(linha):
                cx = inicio_x + idx_col * (2 * raio + espaco_h)
                _desenhar_circulo_com_texto(
                    draw, cx, cy, raio, num, fonte_numeros,
                    cor_fundo=(255, 255, 255), cor_texto=(0, 0, 0)
                )

    # Rodapé
    rodape_y0 = IMG_ALTURA - 120
    draw.rectangle((0, rodape_y0, IMG_LARGURA, IMG_ALTURA), fill=(10, 10, 18))

    texto_rodape = "Portal SimonSports"
    w, h = _tamanho_texto(draw, texto_rodape, fonte_rodape)
    draw.text(((IMG_LARGURA - w) / 2, rodape_y0 + (120 - h) / 2),
              texto_rodape, font=fonte_rodape, fill=COR_TEXTO_CLARO)

    # Salvar em BytesIO
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf