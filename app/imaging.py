# imaging.py — Estilo Portal SimonSports (1080x1080)
# Rev: 2025-11-09 — cores oficiais, logo opcional, auto-fit e layout adaptativo
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os, math

# Paleta oficial (tons base primário, secundário p/ gradiente)
CORES = {
    "mega-sena":   ("#209869", "#155F42"),
    "quina":       ("#6C2AA6", "#4A1D73"),
    "lotofacil":   ("#DD4A91", "#9A2F60"),
    "lotomania":   ("#F39200", "#C96C00"),
    "timemania":   ("#00A650", "#04753A"),
    "dupla-sena":  ("#8B0000", "#5D0000"),
    "federal":     ("#8B4513", "#5E2F0D"),
    "dia-de-sorte":("#FFD700", "#C7A600"),
    "super-sete":  ("#FF4500", "#B53100"),
    "loteca":      ("#38761D", "#245212"),
}

# Quantidade típica de bolas
NUM_QTD = {
    "mega-sena": 6, "quina": 5, "lotofacil": 15, "lotomania": 20,
    "timemania": 10, "dupla-sena": 6, "federal": 5, "dia-de-sorte": 7,
    "super-sete": 7, "loteca": 14,
}

def _norm_key(lot):
    s = (lot or "").lower()
    subs = (
        (" ", "-"), ("á","a"),("à","a"),("â","a"),("ã","a"),
        ("é","e"),("ê","e"),("í","i"),("ó","o"),("ô","o"),("õ","o"),("ú","u"),("ç","c")
    )
    for a,b in subs: s = s.replace(a,b)
    return s

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _font(size, bold=False):
    # tenta Arial; fallback bitmap
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

def _shadow(canvas, box, radius=28, blur=22, opacity=140):
    x0,y0,x1,y1 = box
    w, h = x1-x0, y1-y0
    tmp = Image.new("RGBA", (w+blur*2, h+blur*2), (0,0,0,0))
    d = ImageDraw.Draw(tmp)
    d.rounded_rectangle((blur,blur,blur+w,blur+h), radius=radius, fill=(0,0,0,opacity))
    tmp = tmp.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(tmp, (x0-blur, y0-blur))

def _auto_fit_text(draw, text, max_w, start_size, bold=False, min_size=22):
    size = start_size
    while size >= min_size:
        f = _font(size, bold=bold)
        w = draw.textbbox((0,0), text, font=f)[2]
        if w <= max_w:
            return f, size
        size -= 2
    return _font(min_size, bold=bold), min_size

def _ball(draw, img, cx, cy, r, color_rgb, number: str):
    # Sombra inferior
    sh = Image.new("RGBA", (r*4, r*2), (0,0,0,0))
    sd = ImageDraw.Draw(sh)
    sd.ellipse((0, r*0.25, r*4, r*1.7), fill=(0,0,0,120))
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(sh, (int(cx-2*r), int(cy+r-12)))

    # Bola
    ball = Image.new("RGBA", (r*2, r*2), (0,0,0,0))
    bd = ImageDraw.Draw(ball)
    bd.ellipse((0,0,2*r,2*r), fill=(255,255,255,255))
    bd.ellipse((int(0.32*r), int(0.3*r), int(1.3*r), int(1.1*r)), fill=(255,255,255,255))
    ball = ball.filter(ImageFilter.GaussianBlur(0.5))
    img.alpha_composite(ball, (int(cx-r), int(cy-r)))

    # Número
    num_text = str(number)
    base_size = 56 if len(num_text)<=2 else 48
    f,_ = _auto_fit_text(draw, num_text, int(r*1.6), base_size, bold=True, min_size=34)
    w,h = draw.textbbox((0,0), num_text, font=f)[2:]
    draw.text((cx-w/2, cy-h/2-2), num_text, font=f, fill=color_rgb)

def _try_load_logo(slug):
    path = os.path.join("assets", "logos", f"{slug}.png")
    if os.path.exists(path):
        try:
            im = Image.open(path).convert("RGBA")
            return im
        except: pass
    return None

def _layout_rows_for(slug, n):
    # 2 linhas para: lotofacil (8+7), lotomania (10+10), timemania (5+5), loteca (7+7)
    if slug in ("lotofacil", "lotomania", "timemania", "loteca"):
        if slug == "lotofacil": return [8,7]
        if slug == "lotomania": return [10,10]
        if slug == "timemania": return [5,5]
        if slug == "loteca": return [7,7]
    # default 1 linha
    return [n]

def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url):
    key_raw = _norm_key(loteria)
    # normaliza chaves para o dicionário
    key = key_raw.replace(" ", "-")
    if key == "dia-de-sorte" or "dia" in key and "sorte" in key: key = "dia-de-sorte"
    if key == "dupla-sena" or "dupla" in key and "sena" in key: key = "dupla-sena"
    if key == "lotofácil": key = "lotofacil"

    c1,c2 = CORES.get(key, ("#4B0082","#2B004A"))
    color_rgb = _hex_to_rgb(c1)

    # Canvas
    W = H = 1080
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, W, H, c1, c2)

    # Header (logo + título)
    pad = 80
    title_y = 84

    logo = _try_load_logo(key)
    if logo:
        # redimensiona logo para ~88px de altura
        lh = 88
        lw = int(logo.width * (lh/logo.height))
        logo_r = logo.resize((lw, lh), Image.LANCZOS)
        img.alpha_composite(logo_r, (pad, title_y))
        title_x = pad + lw + 22
    else:
        title_x = pad

    title_max_w = W - title_x - pad
    titulo = (loteria or "").upper()
    f_title, _ = _auto_fit_text(draw, titulo, title_max_w, 92, bold=True, min_size=60)
    draw.text((title_x, title_y), titulo, font=f_title, fill=(255,255,255,255))

    # Subtítulo (Concurso + Data) — sem duplicar nome
    sub = f"Concurso {concurso}  •  {data_br}"
    f_sub,_ = _auto_fit_text(draw, sub, W - pad*2, 54, bold=False, min_size=34)
    draw.text((pad, title_y + 100), sub, font=f_sub, fill=(235,235,245,235))

    # Bloco central (bolas)
    # Layout adaptativo: 1 ou 2 linhas
    raw = (str(numeros_str or "").replace(";", ",").replace(" ", ","))
    nums = [n for n in (x.strip() for x in raw.split(",")) if n]
    maxn = NUM_QTD.get(key, 6)
    nums = nums[:maxn] if nums else ["?"]*maxn
    n = len(nums)

    rows = _layout_rows_for(key, n)
    total_rows = len(rows)

    # raio e spacing variam com n e linhas
    if total_rows == 1:
        r = 70
        spacing = 26
        base_y = 520
        row_offsets = [base_y]
    else:
        r = 62 if key != "lotomania" else 56
        spacing = 22
        base_y = 500
        row_offsets = [base_y-70, base_y+70]

    idx = 0
    for ri, q in enumerate(rows):
        row_nums = nums[idx:idx+q]
        idx += q
        total_w = q*(2*r) + (q-1)*spacing
        start_x = (W - total_w)//2 + r
        cy = row_offsets[ri]
        for j, num in enumerate(row_nums):
            cx = start_x + j*(2*r + spacing)
            _ball(draw, img, cx, cy, r, color_rgb, num)

    # Linha de “Ver resultado completo…”
    if url:
        f_link,_ = _auto_fit_text(draw, "Ver resultado completo no Portal SimonSports", W - pad*2 - 60, 42, False, 28)
        ix,iy = pad, H - 220
        # ícone simples
        draw.arc((ix,iy,ix+34,iy+34), start=200, end=340, fill=(230,230,240,230), width=5)
        draw.arc((ix+26,iy,ix+60,iy+34), start=20, end=160, fill=(230,230,240,230), width=5)
        draw.line((ix+18,iy+26, ix+42,iy+8), fill=(230,230,240,230), width=5)
        draw.text((ix+72, iy+2), "Ver resultado completo no Portal SimonSports", font=f_link, fill=(245,245,255,235))

    # Rodapé
    footer_h = 120
    _shadow(img, (0, H-footer_h-12, W, H), radius=0, blur=24, opacity=100)
    footer = Image.new("RGBA", (W, footer_h), _hex_to_rgb(c2) + (255,))
    img.alpha_composite(footer, (0, H-footer_h))
    f_foot,_ = _auto_fit_text(draw, "PORTAL SIMONSPORTS", W - 2*pad, 64, bold=True, min_size=42)
    wft, hft = draw.textbbox((0,0), "PORTAL SIMONSPORTS", font=f_foot)[2:]
    draw.text(((W-wft)/2, H-footer_h + (footer_h-hft)/2), "PORTAL SIMONSPORTS", font=f_foot, fill=(255,255,255,255))

    # Saída
    out = BytesIO()
    # PNG preserva qualidade e transparências
    img.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out
