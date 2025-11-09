# app/imaging.py — Estilo Portal SimonSports v2 (1080x1080)
# - Usa logo oficial em assets/logos/<slug>.png (fallback: texto)
# - Cores por loteria (gradiente oficial)
# - Título SEM duplicar o nome (mostra apenas "CONCURSO <n>" + data)
# - Bolas escalam conforme quantidade para não estourar
# - Linha "Ver resultado..." + rodapé PORTAL SIMONSPORTS

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os, unicodedata, re

ROOT = os.getcwd()

def _slug(s: str) -> str:
    s = str(s or '').strip().lower()
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'[^a-z0-9\- ]+', '', s).strip().replace('  ',' ')
    return s.replace(' ', '-')

# mapa de slugs aceitos
SLUGS = {
    'mega-sena':'mega-sena',
    'quina':'quina',
    'lotofacil':'lotofacil',
    'lotomania':'lotomania',
    'timemania':'timemania',
    'dupla-sena':'dupla-sena',
    'dupla sena':'dupla-sena',
    'federal':'federal',
    'dia-de-sorte':'dia-de-sorte',
    'dia de sorte':'dia-de-sorte',
    'super-sete':'super-sete',
    'super sete':'super-sete',
    'loteca':'loteca',
}

def _slug_from_name(name: str) -> str:
    p = _slug(name)
    for k,v in SLUGS.items():
        if k in p: return v
    return p or 'loteria'

# Paleta (tons oficiais aproximados)
CORES = {
    "mega-sena":  ("#209869", "#155f42"),
    "quina":      ("#6C2AA6", "#4A1D73"),
    "lotofacil":  ("#DD4A91", "#9A2F60"),
    "lotomania":  ("#F7941D", "#C26E00"),
    "timemania":  ("#00A650", "#04753A"),
    "dupla-sena": ("#8B0000", "#5D0000"),
    "federal":    ("#0C5FA8", "#073C68"),
    "dia-de-sorte": ("#FFC000", "#B68600"),
    "super-sete": ("#FF4500", "#B53100"),
    "loteca":     ("#38761D", "#245212"),
}

# Quantidade de bolas por loteria
NUM_QTD = {
    "mega-sena":6, "quina":5, "lotofacil":15, "lotomania":20,
    "timemania":10, "dupla-sena":6, "federal":5, "dia-de-sorte":7,
    "super-sete":7, "loteca":14,
}

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _font(size, bold=False):
    # tenta Arial; senão fallback padrão
    try:
        path = "arialbd.ttf" if bold else "arial.ttf"
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()

def _draw_gradient(draw, w, h, c1, c2):
    r1,g1,b1 = _hex_to_rgb(c1); r2,g2,b2 = _hex_to_rgb(c2)
    for y in range(h):
        t = y / max(h-1, 1)
        r = int(r1*(1-t) + r2*t)
        g = int(g1*(1-t) + g2*t)
        b = int(b1*(1-t) + b2*t)
        draw.line([(0,y),(w,y)], fill=(r,g,b))

def _shadow_rounded_rect(canvas, box, radius=28, blur=18, opacity=140):
    x0,y0,x1,y1 = box
    w, h = x1-x0, y1-y0
    tmp = Image.new("RGBA", (w+blur*2, h+blur*2), (0,0,0,0))
    d = ImageDraw.Draw(tmp)
    d.rounded_rectangle((blur,blur,blur+w,blur+h), radius=radius, fill=(0,0,0,opacity))
    tmp = tmp.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(tmp, (x0-blur, y0-blur))

def _ball(draw, img, cx, cy, r, color_rgb, number: str):
    # sombra
    sh = Image.new("RGBA", (int(r*4), int(r*2)), (0,0,0,0))
    sd = ImageDraw.Draw(sh)
    sd.ellipse((0, r*0.2, r*4, r*1.6), fill=(0,0,0,120))
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(sh, (int(cx-2*r), int(cy+r-10)))
    # bola
    ball = Image.new("RGBA", (int(r*2), int(r*2)), (0,0,0,0))
    bd = ImageDraw.Draw(ball)
    bd.ellipse((0,0,2*r,2*r), fill=(255,255,255,255))
    bd.ellipse((int(0.32*r), int(0.3*r), int(1.3*r), int(1.1*r)), fill=(255,255,255,255))
    ball = ball.filter(ImageFilter.GaussianBlur(0.5))
    img.alpha_composite(ball, (int(cx-r), int(cy-r)))
    # número (ajuste automático)
    s = 56 if len(number)<=2 else (48 if len(number)==3 else 40)
    f = _font(s, bold=True)
    w,h = draw.textbbox((0,0), number, font=f)[2:]
    draw.text((cx-w/2, cy-h/2-2), number, font=f, fill=color_rgb)

def _load_logo(slug: str):
    p = os.path.join(ROOT, "assets", "logos", f"{slug}.png")
    if os.path.exists(p):
        try:
            return Image.open(p).convert("RGBA")
        except: pass
    return None

def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url):
    loteria = (loteria or "").strip()
    slug = _slug_from_name(loteria)
    c1, c2 = CORES.get(slug, ("#4B0082","#2B004A"))
    color_rgb = _hex_to_rgb(c1)

    W = H = 1080
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, W, H, c1, c2)

    # ===== HEADER: logo + nome menor (se necessário) =====
    logo = _load_logo(slug)
    header_y = 70
    if logo:
        # encaixa em altura ~120px mantendo proporção
        ratio = 120 / max(logo.height, 1)
        lw, lh = int(logo.width*ratio), int(logo.height*ratio)
        logo_res = logo.resize((lw, lh), Image.LANCZOS)
        img.alpha_composite(logo_res, (80, header_y))
    # Nome discreto ao lado (caso logo não exista)
    if not logo:
        f_brand = _font(96, bold=True)
        draw.text((80, header_y+10), loteria.upper(), font=f_brand, fill=(255,255,255,255))

    # ===== BLOCO: "CONCURSO <n>" + data =====
    bloc_top = 220
    _shadow_rounded_rect(img, (80, bloc_top-10, W-80, bloc_top+200), radius=28, blur=30, opacity=110)
    box = Image.new("RGBA", (W-160, 200), (255,255,255,12))
    box_draw = ImageDraw.Draw(box)
    f1 = _font(66, bold=True)
    f2 = _font(50, bold=False)
    t1 = f"CONCURSO {concurso}".strip()
    t2 = f"Sorteio: {data_br}".strip()
    # centraliza t1
    w1,_ = box_draw.textbbox((0,0), t1, font=f1)[2:]
    box_draw.text(((W-160-w1)/2, 24), t1, font=f1, fill=(255,255,255,235))
    box_draw.text((60, 24+66+14), t2, font=f2, fill=(235,235,245,220))
    img.alpha_composite(box, (80, bloc_top-10))

    # ===== NÚMEROS (escalonamento automático) =====
    raw = str(numeros_str or "").replace(";", ",").replace(" ", ",")
    nums = [x.strip() for x in raw.split(",") if x.strip()]
    maxn = NUM_QTD.get(slug, 6)
    if not nums: nums = ["?"]*maxn
    nums = nums[:maxn]

    n = len(nums)
    # calcula raio e espaçamento para caber sempre
    base_r = 74
    r = max(46, min(base_r, int((W*0.82)/(n*2 + (n-1)*0.34))))
    spacing = int(r*0.34)
    total_w = n*(2*r) + (n-1)*spacing
    start_x = (W - total_w)//2 + r
    row_y = 520

    for i, num in enumerate(nums):
        cx = start_x + i*(2*r + spacing)
        _ball(draw, img, cx, row_y, r, color_rgb, num)

    # ===== Link "Ver resultado completo..." =====
    if url:
        f_link = _font(40, bold=False)
        link_text = "Ver resultado completo no Portal SimonSports"
        ix,iy = 110, 660
        draw.arc((ix,iy,ix+34,iy+34), start=200, end=340, fill=(230,230,240,230), width=5)
        draw.arc((ix+26,iy,ix+60,iy+34), start=20, end=160, fill=(230,230,240,230), width=5)
        draw.line((ix+18,iy+26, ix+42,iy+8), fill=(230,230,240,230), width=5)
        draw.text((ix+72, iy+2), link_text, font=f_link, fill=(245,245,255,235))

    # ===== Rodapé =====
    footer_h = 120
    footer = Image.new("RGBA", (W, footer_h), _hex_to_rgb(c2) + (255,))
    img.alpha_composite(footer, (0, H-footer_h))
    f_foot = _font(64, bold=True)
    text_footer = "PORTAL SIMONSPORTS"
    wft, hft = draw.textbbox((0,0), text_footer, font=f_foot)[2:]
    draw.text(((W-wft)/2, H-footer_h + (footer_h-hft)/2), text_footer, font=f_foot, fill=(255,255,255,255))

    out = BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out