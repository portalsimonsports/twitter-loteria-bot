# app/imaging.py — Geração de imagem oficial das Loterias
# Rev: 2025-11-18 — Sem botão "Ver resultado", sem URL na imagem
#                    Rodapé com "Portal SimonSports" centralizado
#
# Função principal:
#   gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url_res) -> BytesIO (PNG)

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
    "loteca": (56, 118, 29),  # verde específico Loteca (texto branco em tabela quando usar)
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
    return COR_FUNDO_PADRAO


def _carregar_fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    """
    Tenta carregar fontes mais elegantes; cai para padrão se não encontrar.
    """
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


def _quebrar_texto(draw, texto, fonte, largura_max):
    """
    Quebra o texto em múltiplas linhas para caber na largura máxima.
    """
    palavras = (texto or "").split()
    if not palavras:
        return [""]

    linhas = []
    linha_atual = palavras[0]

    for palavra in palavras[1:]:
        teste = linha_atual + " " + palavra
        w, _ = draw.textsize(teste, font=fonte)
        if w <= largura_max:
            linha_atual = teste
        else:
            linhas.append(linha_atual)
            linha_atual = palavra

    linhas.append(linha_atual)
    return linhas


def _desenhar_circulo_com_texto(draw, cx, cy, r, texto, fonte, cor_fundo, cor_texto):
    """
    Desenha um círculo preenchido com texto centralizado dentro.
    """
    x0, y0 = cx - r, cy - r
    x1, y1 = cx + r, cy + r
    draw.ellipse((x0, y0, x1, y1), fill=cor_fundo)

    tw, th = draw.textsize(texto, font=fonte)
    tx = cx - tw / 2
    ty = cy - th / 2
    draw.text((tx, ty), texto, font=fonte, fill=cor_texto)


# =========================
# FUNÇÃO PRINCIPAL
# =========================

def gerar_imagem_loteria(loteria: str, concurso: str, data_br: str, numeros_str: str, url_res: str):
    """
    Gera imagem 1080x1080 com:
      - Faixa superior com nome da loteria
      - Subtítulo com "Concurso X — DD/MM/AAAA"
      - Números em círculos
      - Rodapé com "Portal SimonSports"
    NÃO desenha botão "Ver resultado completo" nem URL.
    """
    loteria = (loteria or "").strip()
    concurso = (concurso or "").strip()
    data_br = (data_br or "").strip()
    numeros_str = (numeros_str or "").strip()

    cor_base = _cor_para_loteria(loteria)

    img = Image.new("RGB", (IMG_LARGURA, IMG_ALTURA), COR_FUNDO_PADRAO)
    draw = ImageDraw.Draw(img)

    # Fundo com gradiente suave usando cor da loteria
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

    # Título (nome da loteria)
    margem_lateral = 80
    topo_titulo = 120
    titulo = loteria or "Loteria"
    linhas_titulo = _quebrar_texto(draw, titulo, fonte_titulo, IMG_LARGURA - 2 * margem_lateral)

    y_cursor = topo_titulo
    for linha in linhas_titulo:
        w, h = draw.textsize(linha, font=fonte_titulo)
        x = (IMG_LARGURA - w) / 2
        draw.text((x, y_cursor), linha, font=fonte_titulo, fill=COR_TEXTO_CLARO)
        y_cursor += h + 5

    # Subtítulo
    subtitulo_parts = []
    if concurso:
        subtitulo_parts.append(f"Concurso {concurso}")
    if data_br:
        subtitulo_parts.append(f"({data_br})")
    subtitulo = " — ".join(subtitulo_parts)

    if subtitulo:
        w, h = draw.textsize(subtitulo, font=fonte_sub)
        x = (IMG_LARGURA - w) / 2
        draw.text((x, y_cursor + 10), subtitulo, font=fonte_sub, fill=COR_TEXTO_SUAVE)
        y_cursor += h + 60
    else:
        y_cursor += 60

    # Números em círculos
    numeros = []
    if numeros_str:
        # aceita separadores ; , espaço
        tmp = numeros_str.replace(";", ",").replace(" ", ",")
        for parte in tmp.split(","):
            p = parte.strip()
            if p:
                numeros.append(p)

    if numeros:
        # layout em linhas (máx 8 por linha)
        max_por_linha = 8
        linhas_numeros = [
            numeros[i : i + max_por_linha] for i in range(0, len(numeros), max_por_linha)
        ]

        raio = 55
        espaco_h = 20
        espaco_v = 35

        # área central
        area_top = y_cursor
        area_bottom = IMG_ALTURA - 220  # deixa espaço para o rodapé

        total_altura_circulos = len(linhas_numeros) * (2 * raio) + (len(linhas_numeros) - 1) * espaco_v
        inicio_y = area_top + (area_bottom - area_top - total_altura_circulos) / 2

        for idx_linha, linha in enumerate(linhas_numeros):
            n_cols = len(linha)
            largura_linha = n_cols * (2 * raio) + (n_cols - 1) * espaco_h
            inicio_x = (IMG_LARGURA - largura_linha) / 2
            cy = inicio_y + idx_linha * ((2 * raio) + espaco_v)

            for idx_col, num in enumerate(linha):
                cx = inicio_x + idx_col * ((2 * raio) + espaco_h)
                _desenhar_circulo_com_texto(
                    draw,
                    cx,
                    cy,
                    raio,
                    num,
                    fonte_numeros,
                    cor_fundo=(255, 255, 255),
                    cor_texto=(0, 0, 0),
                )

    # Rodapé com "Portal SimonSports"
    rodape_altura = 120
    rodape_y0 = IMG_ALTURA - rodape_altura
    rodape_y1 = IMG_ALTURA

    # faixa semi-transparente sobre o fundo (simulada misturando)
    overlay_cor = (0, 0, 0, 180)
    # Como a imagem é RGB, desenhamos um retângulo sólido mais escuro
    draw.rectangle(
        (0, rodape_y0, IMG_LARGURA, rodape_y1),
        fill=(10, 10, 18),
    )

    texto_rodape = "Portal SimonSports"
    w, h = draw.textsize(texto_rodape, font=fonte_rodape)
    x = (IMG_LARGURA - w) / 2
    y = rodape_y0 + (rodape_altura - h) / 2
    draw.text((x, y), texto_rodape, font=fonte_rodape, fill=COR_TEXTO_CLARO)

    # Exporta para BytesIO
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf