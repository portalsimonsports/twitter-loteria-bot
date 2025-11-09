# imaging.py — Estilo Portal SimonSports (1080x1080)
# Rev: 2025-11-09b — estilo do “print 2” sem duplicar nome + anti-estouro
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os, math

# Paleta oficial (primária, secundária p/ gradiente)
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

# Quantidade típica de bolas (máximo usado)
NUM_QTD = {
    "mega-sena": 6, "quina": 5, "lotofacil": 15, "lotomania": 20,
    "timemania": 10, "dupla-sena": 6, "federal": 5, "dia-de-sorte": 7,
    "super-sete": 7, "loteca": 14,
}

def _norm_key(lot):
    s = (lot or "").lower()
    transl = (("á","a"),("à","a"),("â","a"),("ã","a"),("é","e"),("ê","e"),
              ("í","i"),("ó","o"),("ô","o"),("õ","o"),("ú","u"),("ç","c"))
    for a,b in transl: s = s.replace(a,b)
    return s.replace(" ", "-")

def _hex_to_rgb(h): h=h.lstrip("#"); return tuple(int(h[i:i+2],16) for i in (0,2,4))

def _font(size, bold=False):
    try:
        return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)
    except:  # fallback
        return ImageFont.load_default()

def _draw_gradient(draw, w, h, c1, c2):
    r1,g1,b1 = _hex_to_rgb(c1); r2,g2,b2 = _hex_to_rgb(c2)
    for y in range(h):
        t = y/max(h-1,1)
        draw.line([(0,y),(w,y)],
                  fill=(int(r1*(1-t)+r2*t), int(g1*(1-t)+g2*t), int(b1*(1-t)+b2*t)))

def _shadow(canvas, box, radius=28, blur=24, opacity=110):
    x0,y0,x1,y1 = box; w,h=x1-x0,y1-y0
    tmp = Image.new("RGBA", (w+blur*2, h+blur*2), (0,0,0,0))
    d = ImageDraw.Draw(tmp)
    d.rounded_rectangle((blur,blur,blur+w,blur+h), radius=radius, fill=(0,0,0,opacity))
    tmp = tmp.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(tmp, (x0-blur, y0-blur))

def _text_fit(draw, text, max_w, start, bold=False, min_size=24):
    s = start
    while s >= min_size:
        f = _font(s, bold)
        w = draw.textbbox((0,0), text, font=f)[2]
        if w <= max_w: return f
        s -= 2
    return _font(min_size, bold)

def _ball(draw, img, cx, cy, r, color_rgb, number):
    # sombra
    sh = Image.new("RGBA", (r*4, r*2), (0,0,0,0))
    sd = ImageDraw.Draw(sh)
    sd.ellipse((0, r*0.28, r*4, r*1.7), fill=(0,0,0,120))
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(sh, (int(cx-2*r), int(cy+r-12)))

    # bola
    ball = Image.new("RGBA", (r*2, r*2), (0,0,0,0))
    bd = ImageDraw.Draw(ball)
    bd.ellipse((0,0,2*r,2*r), fill=(255,255,255,255))
    bd.ellipse((int(0.35*r), int(0.32*r), int(1.25*r), int(1.05*r)), fill=(255,255,255,255))
    ball = ball.filter(ImageFilter.GaussianBlur(0.4))
    img.alpha_composite(ball, (int(cx-r), int(cy-r)))

    # número
    txt = str(number)
    base = 56 if len(txt)<=2 else 48
    f = _text_fit(draw, txt, int(r*1.55), base, bold=True, min_size=34)
    w,h = draw.textbbox((0,0), txt, font=f)[2:]
    draw.text((cx-w/2, cy-h/2-1), txt, font=f, fill=color_rgb)

def _try_logo(slug):
    p = os.path.join("assets","logos", f"{slug}.png")
    if os.path.exists(p):
        try:
            return Image.open(p).convert("RGBA")
        except: pass
    return None

def _rows_for(slug, n):
    # Mantém o “print 2”: uma linha quando couber; 2 linhas nas loterias grandes
    two_lines = {"lotofacil": (8,7), "lotomania": (10,10), "timemania": (5,5), "loteca": (7,7)}
    if slug in two_lines: return list(two_lines[slug])
    return [n]

def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url):
    slug = _norm_key(loteria)
    if "dupla" in slug and "sena" in slug: slug = "dupla-sena"
    if "dia" in slug and "sorte" in slug: slug = "dia-de-sorte"
    if "lotofac" in slug: slug = "lotofacil"

    c1,c2 = CORES.get(slug, ("#4B0082","#2B004A"))
    color_rgb = _hex_to_rgb(c1)

    # Canvas
    W = H = 1080
    img = Image.new("RGBA", (W,H), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, W, H, c1, c2)

    pad = 80

    # ===== Cabeçalho (apenas NOME da loteria) – evita duplicidade
    titulo = (loteria or "").upper().strip()
    f_title = _text_fit(draw, titulo, W - pad*2 - 260, 96, bold=True, min_size=58)
    draw.text((pad, 92), titulo, font=f_title, fill=(255,255,255,255))

    # Logo opcional, pequeno à direita (se existir)
    lg = _try_logo(slug)
    if lg:
        lh = 96
        lw = int(lg.width*(lh/lg.height))
        img.alpha_composite(lg.resize((lw,lh), Image.LANCZOS), (W - pad - lw, 88))

    # ===== Painel (“Concurso XXXX” + data) — SEM nome da loteria
    box_h = 210
    top = 210
    _shadow(img, (pad, top-10, W-pad, top-10+box_h), radius=28, blur=30, opacity=110)
    box = Image.new("RGBA", (W-pad*2, box_h), (255,255,255,12))
    bd = ImageDraw.Draw(box)
    txt1 = f"Concurso {concurso}"
    txt2 = f"Sorteio: {data_br}"
    f1 = _text_fit(bd, txt1, W - pad*2 - 120, 80, bold=True, min_size=52)
    f2 = _text_fit(bd, txt2, W - pad*2 - 120, 56, bold=False, min_size=34)
    bd.text((60, 26), txt1, font=f1, fill=(255,255,255,235))
    bd.text((60, 26 + 78 + 16), txt2, font=f2, fill=(235,235,245,220))
    img.alpha_composite(box, (pad, top-10))

    # ===== Números (anti-estouro)
    raw = (str(numeros_str or "").replace(";", ",").replace(" ", ","))
    nums = [n for n in (x.strip() for x in raw.split(",")) if n]
    maxn = NUM_QTD.get(slug, 6)
    nums = nums[:maxn] if nums else ["?"]*maxn
    n = len(nums)

    rows = _rows_for(slug, n)
    total_rows = len(rows)

    # Calcula raio/spacing para caber na largura útil
    left_margin = pad
    right_margin = pad
    avail_w = W - left_margin - right_margin

    if total_rows == 1:
        # tentamos do maior para o menor até caber
        r = 74
        spacing = 26
        while True:
            width_needed = n*(2*r) + (n-1)*spacing
            if width_needed <= avail_w or r <= 48:
                break
            r -= 2
            if (n-1)*spacing > avail_w*0.35: spacing = max(18, spacing-1)
        centers_y = [520]
    else:
        # duas linhas mais compactas
        r = 60
        spacing = 22
        # também garante largura
        for q in rows:
            while q*(2*r)+(q-1)*spacing > avail_w and r > 46:
                r -= 2
                if spacing > 16: spacing -= 1
        centers_y = [500-70, 500+70]

    # desenha
    idx = 0
    for ri, q in enumerate(rows):
        line = nums[idx:idx+q]; idx += q
        total_w = q*(2*r) + (q-1)*spacing
        start_x = left_margin + (avail_w - total_w)//2 + r
        cy = centers_y[ri]
        for j, num in enumerate(line):
            cx = start_x + j*(2*r + spacing)
            _ball(draw, img, cx, cy, r, color_rgb, num)

    # ===== Linha “Ver resultado completo…”
    if url:
        label = "Ver resultado completo no Portal SimonSports"
        f3 = _text_fit(draw, label, W - pad*2 - 92, 42, bold=False, min_size=28)
        ix,iy = pad, 660
        draw.arc((ix,iy,ix+34,iy+34), start=200, end=340, fill=(230,230,240,230), width=5)
        draw.arc((ix+26,iy,ix+60,iy+34), start=20, end=160, fill=(230,230,240,230), width=5)
        draw.line((ix+18,iy+26, ix+42,iy+8), fill=(230,230,240,230), width=5)
        draw.text((ix+72, iy+2), label, font=f3, fill=(245,245,255,235))

    # ===== Rodapé
    footer_h = 120
    _shadow(img, (0, H-footer_h-10, W, H), radius=0, blur=24, opacity=90)
    footer = Image.new("RGBA", (W, footer_h), _hex_to_rgb(c2)+(255,))
    img.alpha_composite(footer, (0, H-footer_h))
    brand = "PORTAL SIMONSPORTS"
    fb = _text_fit(draw, brand, W - pad*2, 64, bold=True, min_size=42)
    bw,bh = draw.textbbox((0,0), brand, font=fb)[2:]
    draw.text(((W-bw)/2, H-footer_h + (footer_h-bh)/2),
              brand, font=fb, fill=(255,255,255,255))

    out = BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out