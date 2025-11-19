# app/imaging.py — Versão FINAL 100% corrigida (19/11/2025)
# Funciona com Pillow 10+ e sem nenhum SyntaxError

import io
from typing import Tuple
from PIL import Image, ImageDraw, ImageFont

CORES_LOTERIAS = {
    "mega-sena": (32, 152, 105), "quina": (94, 54, 139), "lotofacil": (212, 0, 120),
    "lotofácil": (212, 0, 120), "lotomania": (242, 144, 0), "timemania": (0, 128, 0),
    "dupla sena": (153, 0, 51), "dupla-sena": (153, 0, 51), "federal": (0, 84, 150),
    "dia de sorte": (178, 120, 50), "dia-de-sorte": (178, 120, 50),
    "super sete": (37, 62, 116), "super-sete": (37, 62, 116), "loteca": (56, 118, 29),
}

COR_FUNDO_PADRAO = (25, 25, 35)
COR_TEXTO_CLARO = (255, 255, 255)
COR_TEXTO_SUAVE = (230, 230, 240)
W, H = 1080, 1080

def _cor_loteria(nome: str) -> Tuple[int, int, int]:
    nome = (nome or "").lower()
    for chave, cor in CORES_LOTERIAS.items():
        if chave.replace(" ", "") in nome.replace(" ", ""):
            return cor
    return (100, 100, 100)

def _fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    caminhos = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/system/fonts/Roboto-Bold.ttf",
        "/system/fonts/DroidSans-Bold.ttf",
    ]
    for p in caminhos:
        try:
            return ImageFont.truetype(p, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()

def _tamanho(draw: ImageDraw.Draw, texto: str, fonte: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), texto, font=fonte)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def _circulo_texto(draw: ImageDraw.Draw, cx: float, cy: float, r: int, num: str,
                   fonte: ImageFont.FreeTypeFont, fundo=(255,255,255), texto=(0,0,0)):
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=fundo)
    w, h = _tamanho(draw, num, fonte)
    draw.text((cx - w/2, cy - h/2), num, font=fonte, fill=texto)

def gerar_imagem_loteria(loteria: str, concurso: str, data_br: str, numeros_str: str, url_res: str = "") -> io.BytesIO:
    loteria = loteria.strip() if loteria else ""
    cor = _cor_loteria(loteria)

    img = Image.new("RGB", (W, H), COR_FUNDO_PADRAO)
    d = ImageDraw.Draw(img)

    # Gradiente
    for y in range(H):
        f = y / H
        r = int(COR_FUNDO_PADRAO[0]*(1-f) + cor[0]*f)
        g = int(COR_FUNDO_PADRAO[1]*(1-f) + cor[1]*f)
        b = int(COR_FUNDO_PADRAO[2]*(1-f) + cor[2]*f)
        d.line([(0,y),(W,y)], fill=(r,g,b))

    ftitulo = _fonte(80)
    fsub = _fonte(42)
    fnum = _fonte(60)
    frodape = _fonte(38)

    y = 120
    titulo = loteria.upper() or "LOTERIA"
    for linha in [titulo]:  # quase nunca quebra, mas mantém compatibilidade
        w, h = _tamanho(d, linha, ftitulo)
        d.text(((W-w)/2, y), linha, font=ftitulo, fill=COR_TEXTO_CLARO)
        y += h + 10

    sub = []
    if concurso: sub.append(f"Concurso {concurso}")
    if data_br: sub.append(f"({data_br})")
    if sub:
        texto_sub = " — ".join(sub)
        w, h = _tamanho(d, texto_sub, fsub)
        d.text(((W-w)/2, y + 30), texto_sub, font=fsub, fill=COR_TEXTO_SUAVE)
        y += h + 80
    else:
        y += 80

    # Números
    nums = [n.strip() for n in numeros_str.replace(";",",").replace(" ","").split(",") if n]
    if nums:
        por_linha = 8
        linhas = [nums[i:i+por_linha] for i in range(0, len(nums), por_linha)]
        r = 55
        esp_h, esp_v = 20, 35
        area_h = H - 220 - y
        alt_total = len(linhas)*(2*r) + max(0, len(linhas)-1)*esp_v
        iy = y + (area_h - alt_total)/2

        for linha in linhas:
            larg_linha = len(linha)*(2*r) + max(0, len(linha)-1)*esp_h
            ix = (W - larg_linha)/2
            cy = iy + linhas.index(linha)*(2*r + esp_v)
            for j, n in enumerate(linha):
                cx = ix + j*(2*r + esp_h)
                _circulo_texto(d, cx, cy, r, n, fnum)

            iy += 2*r + esp_v  # só pra próxima linha

    # Rodapé
    d.rectangle((0, H-120, W, H), fill=(10,10,18))
    rodape = "Portal SimonSports"
    w, h = _tamanho(d, rodape, frodape)
    d.text(((W-w)/2, H-120 + (120-h)/2), rodape, font=frodape, fill=COR_TEXTO_CLARO)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf