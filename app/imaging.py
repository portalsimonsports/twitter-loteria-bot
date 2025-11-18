# app/imaging.py — Portal SimonSports
# Rev: 2025-11-15c — Layout “bolinhas” com cores da loteria + logo + CTA
# Ajustes:
# - Lotofácil agora exibe TODOS os números (suporta 2º sorteio via "|")
# - Dupla Sena agora exibe TODOS os números em blocos de 6 (1 linha por sorteio)

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import os
import re
import math
from datetime import datetime

# ==========================
# CONFIG GERAL DA IMAGEM
# ==========================

W, H = 1080, 1080          # tamanho quadrado padrão
M = 80                     # margem lateral

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
LOGOS_DIR  = os.path.join(ASSETS_DIR, "logos")

# ==========================
# FONTES
# ==========================

def _try_fonts(cands, size):
    for p in cands:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def FONT_SANS(size, bold=False):
    if bold:
        cands = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        cands = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    return _try_fonts(cands, size)

def FONT_SERIF(size):
    cands = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    ]
    return _try_fonts(cands, size)

# ==========================
# CORES POR LOTERIA
# ==========================

CORES_LOTERIAS = {
    "mega-sena":    (32, 152, 105),
    "quina":        (64, 40, 94),
    "lotofacil":    (149, 55, 148),
    "lotofácil":    (149, 55, 148),
    "lotomania":    (243, 112, 33),
    "timemania":    (39, 127, 66),
    "dupla-sena":   (149, 32, 49),
    "dupla sena":   (149, 32, 49),
    "federal":      (0, 76, 153),
    "dia-de-sorte": (184, 134, 11),
    "dia de sorte": (184, 134, 11),
    "super-sete":   (37, 62, 116),
    "super sete":   (37, 62, 116),
    "loteca":       (56, 118, 29),   # verde que você usa (#38761d approx)
}

def _slug(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("ç", "c")
    s = re.sub(r"[áàâãä]", "a", s)
    s = re.sub(r"[éèêë]", "e", s)
    s = re.sub(r"[íìîï]", "i", s)
    s = re.sub(r"[óòôõö]", "o", s)
    s = re.sub(r"[úùûü]", "u", s)
    s = re.sub(r"[^a-z0-9\- ]+", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s

def cor_loteria(nome: str):
    nome = nome or "Loteria"
    if nome.lower() in CORES_LOTERIAS:
        return CORES_LOTERIAS[nome.lower()]
    sl = _slug(nome)
    return CORES_LOTERIAS.get(sl, (30, 30, 30))

# ==========================
# FUNDOS / GRADIENTE
# ==========================

def _gradient_vertical(w, h, top_rgb, bottom_rgb):
    base = Image.new("RGB", (w, h), top_rgb)
    top = Image.new("RGB", (w, h), bottom_rgb)
    mask = Image.linear_gradient("L").resize((1, h)).resize((w, h))
    return Image.composite(top, base, mask)

def _vinheta(img, strength=220, blur=180):
    w, h = img.size
    v = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(v)
    d.ellipse([-200, -80, w + 200, h + 280], fill=strength)
    v = v.filter(ImageFilter.GaussianBlur(blur))
    return Image.composite(img, Image.new("RGB", (w, h), (0, 0, 0)), v)

def criar_fundo(loteria_nome: str):
    base = cor_loteria(loteria_nome)
    # clareia um pouco no topo
    top = tuple(min(255, int(c * 1.3)) for c in base)
    bottom = tuple(int(c * 0.8) for c in base)
    g = _gradient_vertical(W, H, top, bottom)
    g = _vinheta(g)
    return g

# ==========================
# LOGO
# ==========================

def load_logo(loteria_nome: str):
    slug = _slug(loteria_nome)
    cand = [
        os.path.join(LOGOS_DIR, f"{slug}.png"),
        os.path.join(LOGOS_DIR, f"{slug}.jpg"),
        os.path.join(LOGOS_DIR, f"{slug}.jpeg"),
    ]
    for p in cand:
        if os.path.exists(p):
            try:
                return Image.open(p).convert("RGBA")
            except Exception:
                pass
    return None

def desenhar_logo(canvas: Image.Image, loteria_nome: str):
    logo = load_logo(loteria_nome)
    if not logo:
        return
    max_w, max_h = 210, 120
    logo.thumbnail((max_w, max_h), Image.LANCZOS)
    x = W - M - logo.width
    y = M
    canvas.paste(logo, (x, y), logo)

# ==========================
# PARSE DE NÚMEROS
# ==========================

def parse_numeros(loteria_nome: str, numeros_str: str):
    """
    Retorna (lista_de_listas, extra_text).
    Cada sublista = uma linha de bolinhas.
    Suporta:
    - Lotofácil com 1 ou 2 sorteios (via "|", todos os números entram)
    - Dupla Sena com 1 ou mais sorteios (blocos de 6 por linha)
    """
    s = (numeros_str or "").strip()

    extra = None
    # Se tiver um texto final depois de " - " ou "; " (ex.: mês, Time do Coração)
    m = re.search(r"(?:-|;)\s*([A-Za-zÀ-ÿ0-9/ \.\-]+)$", s)
    if m:
        extra = m.group(1).strip()
        s = s[:m.start()].strip(",; -")

    # normaliza separadores (inclui "|")
    s = s.replace("–", "-")
    s = re.sub(r"[;| ]+", ",", s)
    parts = [p.strip() for p in s.split(",") if p.strip()]

    # deixa dois dígitos em números
    nums = [p.zfill(2) if re.fullmatch(r"\d+", p) else p for p in parts]

    n = len(nums)
    rows = []

    nome = loteria_nome.lower()

    if "lotofacil" in nome:
        # Lotofácil: exibe TODOS os números em blocos de 5
        # 15 dezenas → 3 linhas; 30 dezenas (2 sorteios) → 6 linhas, etc.
        rows = [nums[i:i+5] for i in range(0, n, 5)]

    elif "lotomania" in nome:
        rows = [nums[i:i+5] for i in range(0, min(20, n), 5)]

    elif "timemania" in nome:
        # 7 números + time -> duas linhas se passar de 7
        if n <= 7:
            rows = [nums]
        else:
            rows = [nums[:7], nums[7:]]

    elif "dupla" in nome:
        # Dupla Sena: TODOS os números em blocos de 6
        # 6 dezenas → 1 linha, 12 dezenas (2 sorteios) → 2 linhas, etc.
        rows = [nums[i:i+6] for i in range(0, n, 6)]

    else:
        # regra geral: máx 8 por linha, 1–3 linhas
        if n <= 8:
            rows = [nums]
        elif n <= 16:
            rows = [nums[:math.ceil(n/2)], nums[math.ceil(n/2):]]
        else:
            # três linhas
            terc = math.ceil(n / 3)
            rows = [nums[:terc], nums[terc:2*terc], nums[2*terc:]]

    # limpa linhas vazias
    rows = [r for r in rows if r]

    return rows, extra

# ==========================
# DESENHO DAS BOLINHAS
# ==========================

def desenhar_bolinhas(draw: ImageDraw.ImageDraw, loteria_nome: str,
                      numeros_str: str, area_box):
    """
    area_box = (x0,y0,x1,y1) onde a grade de números deve caber.
    """
    x0, y0, x1, y1 = area_box
    largura = x1 - x0
    altura = y1 - y0

    rows, extra = parse_numeros(loteria_nome, numeros_str)
    if not rows:
        return

    qtd_linhas = len(rows)
    max_cols = max(len(r) for r in rows)

    # Define raio conforme a quantidade
    if max_cols <= 5:
        r = 62
        gap_x = 28
    elif max_cols <= 8:
        r = 54
        gap_x = 22
    else:
        r = 46
        gap_x = 20

    if qtd_linhas == 1:
        gap_y = 0
    elif qtd_linhas == 2:
        gap_y = 40
    else:
        gap_y = 30

    line_height = 2 * r + gap_y
    total_h = qtd_linhas * line_height - gap_y
    start_y = y0 + (altura - total_h) // 2

    # Cores das bolinhas (branco) e texto
    circle_color = (255, 255, 255)
    text_color = (20, 20, 20)
    font_num = FONT_SANS(46, bold=True)

    for ridx, row in enumerate(rows):
        cols = len(row)
        total_w_row = cols * (2 * r + gap_x) - gap_x
        start_x = x0 + (largura - total_w_row) // 2
        cy = start_y + ridx * (2 * r + gap_y) + r

        for cidx, token in enumerate(row):
            cx = start_x + cidx * (2 * r + gap_x) + r
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=circle_color)

            if token:
                txt = str(token)
                tw = draw.textlength(txt, font=font_num)
                # aproximar altura
                bbox = font_num.getbbox(txt)
                th = bbox[3] - bbox[1]
                draw.text(
                    (cx - tw / 2, cy - th / 2 - 2),
                    txt,
                    font=font_num,
                    fill=text_color,
                )

    # Extra (mês, time do coração etc.) embaixo, se houver
    if extra:
        font_extra = FONT_SANS(38, bold=True)
        txt = extra.strip()
        tw = draw.textlength(txt, font=font_extra)
        draw.text(
            ((x0 + x1) / 2 - tw / 2, y1 + 10),
            txt,
            font=font_extra,
            fill=(255, 255, 255),
        )

# ==========================
# CTA E MARCA
# ==========================

def desenhar_cta(draw: ImageDraw.ImageDraw, url: str = ""):
    # botão amarelo tipo “VER RESULTADO COMPLETO”
    btn_w, btn_h = 760, 96
    bx = (W - btn_w) // 2
    by = H - 260

    draw.rounded_rectangle(
        (bx, by, bx + btn_w, by + btn_h),
        radius=28,
        fill=(255, 215, 0),
        outline=(0, 0, 0),
        width=2,
    )

    txt = "VER RESULTADO COMPLETO"
    font_btn = FONT_SANS(44, bold=True)
    tw = draw.textlength(txt, font=font_btn)
    draw.text(
        (W / 2 - tw / 2, by + (btn_h - 48) / 2),
        txt,
        font=font_btn,
        fill=(0, 0, 0),
    )

    # URL do post (sem http) logo abaixo, se tiver
    if url:
        url_clean = url.replace("https://", "").replace("http://", "")
        font_url = FONT_SANS(32, bold=False)
        tw = draw.textlength(url_clean, font=font_url)
        draw.text(
            (W / 2 - tw / 2, by + btn_h + 18),
            font=font_url,
            text=url_clean,
            fill=(245, 245, 245),
        )

    # Marca PORTAL SIMONSPORTS no rodapé
    marca = "PORTAL SIMONSPORTS"
    font_marca = FONT_SANS(30, bold=True)
    tw = draw.textlength(marca, font=font_marca)
    draw.text(
        (W / 2 - tw / 2, H - 72),
        marca,
        font=font_marca,
        fill=(255, 255, 255, 200),
    )

# ==========================
# TÍTULOS / TOPO
# ==========================

def desenhar_titulo(draw: ImageDraw.ImageDraw, loteria: str,
                    concurso: str, data_br: str):
    loteria_txt = (loteria or "").strip()
    if not loteria_txt:
        loteria_txt = "Loteria"

    # linha principal (nome da loteria)
    font_title = FONT_SERIF(88)
    draw.text(
        (M, M),
        loteria_txt,
        font=font_title,
        fill=(255, 255, 255),
    )

    # segunda linha: concurso
    font_sub = FONT_SANS(40, bold=True)
    sub = ""
    if concurso:
        sub = f"Concurso {concurso}"
    if sub:
        draw.text(
            (M, M + 90),
            sub,
            font=font_sub,
            fill=(230, 230, 230),
        )

    # terceira linha: data
    if data_br:
        font_date = FONT_SANS(34, bold=False)
        draw.text(
            (M, M + 90 + 48),
            data_br,
            font=font_date,
            fill=(220, 220, 220),
        )

# ==========================
# FUNÇÃO PRINCIPAL
# ==========================

def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url=""):
    """
    Gera imagem em BytesIO (PNG) no layout aprovado:
    - fundo na cor da loteria (gradiente)
    - logo no topo direito
    - título + concurso + data
    - grade de bolinhas com números
    - CTA amarelo + URL + PORTAL SIMONSPORTS
    """
    loteria = str(loteria or "").strip()
    concurso = str(concurso or "").strip()
    data_br = str(data_br or "").strip()
    numeros_str = str(numeros_str or "").strip()
    url = str(url or "").strip()

    # fundo
    img = criar_fundo(loteria)
    draw = ImageDraw.Draw(img)

    # topo
    desenhar_titulo(draw, loteria, concurso, data_br)
    desenhar_logo(img, loteria)

    # área central de números
    # (depois dos títulos e antes do CTA)
    area_top = M + 180
    area_bottom = H - 320
    area_box = (M, area_top, W - M, area_bottom)
    desenhar_bolinhas(draw, loteria, numeros_str, area_box)

    # CTA & marca
    desenhar_cta(draw, url=url)

    # salva em memória
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf