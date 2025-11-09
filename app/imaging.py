# app/imaging.py — Portal SimonSports
# Rev: 2025-11-09 — Estilo “site”: título único, data, grade de números, logo no topo,
# CTA no rodapé; quebras por loteria; suporte básico Loteca (14 linhas – 1X2)
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io, os, re, math
from datetime import datetime

# ====== Caminhos de ativos (ajuste se precisar) ======
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
LOGOS_DIR  = os.path.join(ASSETS_DIR, "logos")

# ====== Tamanho base (quadrado p/ socials) ======
W, H = 1080, 1080
SAFE_LR = 72   # margem esquerda/direita
SAFE_T  = 90   # margem superior
SAFE_B  = 120  # margem inferior

# ====== Fontes (fallbacks de sistema) ======
def _try_fonts(cands, size):
    for p in cands:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except: 
                pass
    # fallback básico
    return ImageFont.load_default()

FONT_SERIF = lambda s: _try_fonts([
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
], s)

FONT_SANS  = lambda s: _try_fonts([
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
], s)

FONT_SANS_B = lambda s: _try_fonts([
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
], s)

# ====== Cores por loteria (oficiais/consistentes) ======
CORES = {
    "mega-sena":    (32,152,105),
    "quina":        (64, 40, 94),
    "lotofacil":    (149, 55, 148),
    "lotomania":    (243,112, 33),
    "timemania":    (39,127, 66),
    "dupla-sena":   (149, 32, 49),
    "federal":      (  0, 76,153),
    "dia-de-sorte": (184,134, 11),
    "super-sete":   ( 37, 62,116),
    "loteca":       (56,118, 29),  # #38761d
}
def slug(s):
    s = (s or "").lower()
    s = s.replace("ç","c")
    s = re.sub(r"[áàâãä]", "a", s)
    s = re.sub(r"[éèêë]", "e", s)
    s = re.sub(r"[íìîï]", "i", s)
    s = re.sub(r"[óòôõö]", "o", s)
    s = re.sub(r"[úùûü]", "u", s)
    s = re.sub(r"[^a-z0-9\- ]+","", s).strip()
    s = re.sub(r"\s+","-", s)
    m = {
        "lotofácil":"lotofacil",
        "dupla sena":"dupla-sena",
        "dia de sorte":"dia-de-sorte",
        "super sete":"super-sete",
    }
    return m.get(s, s)

def cor_loteria(name):
    return CORES.get(slug(name), (30,30,30))

# ====== Fundos ======
def fundo_gradient(base_rgb):
    # leve vinheta + gradiente radial discreto
    img = Image.new("RGB", (W,H), (20,18,22))
    draw = ImageDraw.Draw(img)
    cx, cy = W//2, H//2
    max_r = int(math.hypot(cx, cy))
    br, bg, bb = base_rgb
    for r in range(max_r, 0, -12):
        alpha = r / max_r
        col = tuple(int( (1-alpha)*x + alpha*br ) for x in (15,15,15))
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=col)
    # suaviza
    return img.filter(ImageFilter.GaussianBlur(12))

# ====== Util ======
def load_logo(name):
    p = os.path.join(LOGOS_DIR, f"{slug(name)}.png")
    if os.path.exists(p):
        try:
            return Image.open(p).convert("RGBA")
        except: 
            return None
    return None

def draw_text(draw, xy, text, font, fill=(255,255,255), anchor="la"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)

def circle(draw, cx, cy, r, fill, outline=None, ow=0):
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=fill, outline=outline, width=ow)

# ====== Regras de quebra por loteria ======
def split_numeros(loteria, numeros_str):
    """Retorna dict com linhas (lista de listas de textos) e metadados especiais."""
    s = (numeros_str or "").strip()

    # Achar itens “extras” (Time do Coração, mês, trevo, etc.) no final após hífen/; ou texto
    extra = None
    # se houver “ - algo ” no fim:
    m = re.search(r"(?:-|;)\s*([A-Za-zÀ-ÿ0-9/ \.\-]+)$", s)
    if m and slug(loteria) in ("timemania","dia-de-sorte"):
        extra = m.group(1).strip()
        s = s[:m.start()].strip(",; -")

    # normaliza separadores
    s = re.sub(r"[;| ]+", ",", s)
    parts = [p.strip() for p in s.split(",") if p.strip()]

    L = slug(loteria)
    lines = []

    def chunk(lst, n):
        return [lst[i:i+n] for i in range(0, len(lst), n)]

    if L == "lotofacil":
        # 15 → 3 linhas de 5
        parts = [p.zfill(2) if p.isdigit() else p for p in parts]
        lines = chunk(parts, 5)
    elif L == "lotomania":
        # 20 → 4x5
        parts = [p.zfill(2) if p.isdigit() else p for p in parts]
        lines = chunk(parts, 5)
    elif L == "timemania":
        # 10 números? padrão imagem: 2 linhas de 5 (você aprovou)
        parts = [p.zfill(2) if p.isdigit() else p for p in parts]
        # garante duas linhas, completa com vazio se faltar
        while len(parts) < 10: parts.append("")
        lines = [parts[:5], parts[5:10]]
    elif L == "dupla-sena":
        # dois sorteios de 6: se vier 12 números, quebra 6+6
        parts = [p.zfill(2) if p.isdigit() else p for p in parts]
        if len(parts) >= 12:
            lines = [parts[:6], parts[6:12]]
        else:
            lines = chunk(parts, 6)
    elif L == "loteca":
        # números devem ser “1X2” por jogo (14 linhas)
        # aceita lista com 14 tokens; se menos, preenche com vazio
        items = parts[:14]
        while len(items) < 14: items.append("")
        lines = [[items[i]] for i in range(14)]  # 14 linhas, 1 coluna (1X2)
    else:
        # Regra global: máx 7 por linha
        parts = [p.zfill(2) if p.isdigit() else p for p in parts]
        lines = chunk(parts, 7)

    return {"lines": lines, "extra": extra}

# ====== Render grade de números ======
def draw_grade_numeros(draw, area, loteria, numeros_str, color):
    """Desenha círculos/textos no retângulo area=(x0,y0,x1,y1)"""
    x0,y0,x1,y1 = area
    Wd, Hd = x1-x0, y1-y0
    spec = split_numeros(loteria, numeros_str)
    lines = spec["lines"]
    extra = spec["extra"]

    # Loteca: tabela 14 linhas 1X2
    if slug(loteria) == "loteca":
        # header
        title_f = FONT_SANS_B(38)
        cell_f  = FONT_SANS_B(36)
        draw_text(draw, (x0, y0), "#", title_f, (255,255,255), "la")
        draw_text(draw, (x0+70, y0), "1X2", title_f, (255,255,255), "la")
        yy = y0 + 54
        for i, row in enumerate(lines, start=1):
            token = (row[0] or "").upper()
            # cor especial em empate (X) e vitórias
            bg = None
            if token in ("1","X","2"):
                if token == "X": bg = (56,118,29)  # empate (seu padrão)
                else:             bg = (20,20,20)
            if bg:
                draw.rectangle((x0+60, yy-6, x0+200, yy+38), fill=bg)
                draw_text(draw, (x0+70, yy), token, cell_f, (255,255,255), "la")
            else:
                draw_text(draw, (x0+70, yy), token or "-", cell_f, (230,230,230), "la")
            draw_text(draw, (x0, yy), f"{i:02d}", cell_f, (200,200,200), "la")
            yy += 46
        return y0

    # Demais: círculos
    rows = len(lines)
    if rows == 0: return y0
    # altura por linha
    r = 38  # raio do círculo
    gap_y = 28
    line_h = 2*r + gap_y
    total_h = rows*line_h - gap_y
    start_y = y0 + (Hd - total_h)//2

    num_f = FONT_SANS_B(36)
    bg_circle = (250,250,250)
    fg_circle = (0,0,0)

    for ridx, row in enumerate(lines):
        ncols = len(row)
        # largura ocupada: cada bolinha 2r + gap_x
        gap_x = 22
        row_w = ncols*(2*r + gap_x) - gap_x
        cur_x = x0 + (Wd - row_w)//2 + r
        cy = start_y + ridx*(2*r + gap_y) + r

        for item in row:
            if not item:
                cur_x += 2*r + gap_x
                continue
            circle(draw, int(cur_x), int(cy), r, bg_circle)
            # número central
            tw, th = draw.textlength(item, font=num_f), num_f.size
            draw_text(draw, (cur_x - tw/2, cy - th/2 - 4), item, num_f, fg_circle, "la")
            cur_x += 2*r + gap_x

    # extra (Timemania/Dia de Sorte) embaixo
    if extra:
        ext_f = FONT_SANS_B(38)
        draw_text(draw, (x0 + Wd/2, y1 - 10), str(extra).strip(), ext_f, (240,240,240), "ms")

# ====== CTA rodapé ======
def draw_cta(img, texto="Ver resultado completo no Portal SimonSports"):
    draw = ImageDraw.Draw(img)
    pad = 20
    btn_h = 66
    x0, x1 = SAFE_LR, W - SAFE_LR
    y0 = H - SAFE_B + 18
    # barra translúcida
    draw.rounded_rectangle((x0, y0, x1, y0+btn_h), radius=16, fill=(0,0,0,140))
    f = FONT_SANS_B(30)
    draw_text(draw, ((x0+x1)//2, y0+btn_h//2), texto, f, (255,255,255), "mm")

# ====== Render principal ======
def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url=""):
    base = cor_loteria(loteria)
    img = fundo_gradient(base)
    draw = ImageDraw.Draw(img)

    # Título (único) + data
    title = f"{loteria} {concurso}".strip()
    tf = FONT_SERIF(86)
    df = FONT_SANS_B(40)
    draw_text(draw, (SAFE_LR, SAFE_T), title, tf, (255,255,255), "la")
    draw_text(draw, (SAFE_LR, SAFE_T+82), data_br, df, (230,230,230), "la")

    # Logo no topo-direito
    logo = load_logo(loteria)
    if logo:
        # redimensiona logo para caber ~160px largura
        max_w = 180
        scale = min(1.0, max_w / max(1, logo.width))
        lw = int(logo.width * scale)
        lh = int(logo.height * scale)
        lg = logo.resize((lw, lh), Image.LANCZOS)
        img.paste(lg, (W - SAFE_LR - lw, SAFE_T - 6), lg)

    # Área central para grade
    area = (SAFE_LR, SAFE_T + 150, W - SAFE_LR, H - SAFE_B - 120)
    draw_grade_numeros(draw, area, loteria, numeros_str, base)

    # CTA no rodapé
    draw_cta(img)

    # bordas suaves
    vign = Image.new("L", (W,H), 0)
    vd = ImageDraw.Draw(vign)
    vd.rectangle((40,40,W-40,H-40), fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(30))
    img.putalpha(vign)
    bg = Image.new("RGB", (W,H), (0,0,0))
    bg.paste(img, mask=img.split()[-1])

    # Salva em memória (PNG)
    buf = io.BytesIO()
    bg.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf