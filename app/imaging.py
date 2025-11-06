# imaging.py — Estilo Portal SimonSports (quadrado 1080x1080)
# Fundo em degradê por loteria, título grande, bolas brancas com sombra,
# linha "Ver resultado completo..." e rodapé PORTAL SIMONSPORTS.
#
# Uso:
#   from app.imaging import gerar_imagem_loteria
#   buf = gerar_imagem_loteria("Quina", "6870", "04/11/2025", "18,19,20,42,46", "https://...")
#   # buf é um BytesIO (PNG) pronto para upload

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import textwrap

# Paleta oficial (tons base)
CORES = {
    "mega-sena":  ("#209869", "#155f42"),
    "quina":      ("#6c2aa6", "#4a1d73"),  # roxo
    "lotofácil":  ("#dd4a91", "#9a2f60"),
    "lotomania":  ("#ff8c00", "#c96c00"),
    "timemania":  ("#00a650", "#04753a"),
    "dupla sena": ("#8b0000", "#5d0000"),
    "federal":    ("#8b4513", "#5e2f0d"),
    "dia de sorte": ("#ffd700", "#c7a600"),
    "super sete": ("#ff4500", "#b53100"),
    "loteca":     ("#38761d", "#245212"),
}

# Quantidade de bolas por loteria (para truncar caso venham a mais)
NUM_QTD = {
    "mega-sena": 6, "quina": 5, "lotofácil": 15, "lotomania": 20,
    "timemania": 10, "dupla sena": 6, "federal": 5, "dia de sorte": 7,
    "super sete": 7, "loteca": 14,
}

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _font(size, bold=False):
    # Tenta Arial; volta pro default se não tiver na runner
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
    # Sombra inferior
    sh = Image.new("RGBA", (r*4, r*2), (0,0,0,0))
    sd = ImageDraw.Draw(sh)
    sd.ellipse((0, r*0.2, r*4, r*1.6), fill=(0,0,0,120))
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(sh, (int(cx-2*r), int(cy+r-10)))

    # Bola (branca com leve gradiente)
    ball = Image.new("RGBA", (r*2, r*2), (0,0,0,0))
    bd = ImageDraw.Draw(ball)
    bd.ellipse((0,0,2*r,2*r), fill=(255,255,255,255))
    # brilho
    bd.ellipse((int(0.32*r), int(0.3*r), int(1.3*r), int(1.1*r)), fill=(255,255,255,255))
    ball = ball.filter(ImageFilter.GaussianBlur(0.5))
    img.alpha_composite(ball, (int(cx-r), int(cy-r)))

    # Número (na cor da loteria)
    f = _font(56 if len(number)<=2 else 48, bold=True)
    w,h = draw.textbbox((0,0), number, font=f)[2:]
    draw.text((cx-w/2, cy-h/2-2), number, font=f, fill=color_rgb)

def _draw_quina_icon(draw, x, y, size, fill):  # trevo estilizado
    r = size//2
    for dx,dy in ((-r,0),(r,0),(0,-r),(0,r)):
        draw.ellipse((x+dx-r//1.3, y+dy-r//1.3, x+dx+r//1.3, y+dy+r//1.3), fill=fill)
    draw.rectangle((x-6, y-6, x+6, y+6), fill=fill)

def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url):
    lot = (loteria or "").strip()
    key = lot.lower()

    # Cores da loteria (gradiente)
    c1,c2 = CORES.get(key, ("#4b0082","#2b004a"))
    color_rgb = _hex_to_rgb(c1)

    # Canvas
    W = H = 1080
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, W, H, c1, c2)

    # Header com logo/título
    title_y = 90
    # Ícone da Quina (trevo); para outras, só texto por enquanto
    if key == "quina":
        _draw_quina_icon(draw, 140, title_y+18, 84, (255,255,255,255))
    f_brand = _font(88, bold=True)
    draw.text((230 if key=="quina" else 80, title_y), lot.upper(), font=f_brand, fill=(255,255,255,255))

    # Bloco central com título do concurso e data
    bloc_top = 210
    _shadow_rounded_rect(img, (80, bloc_top-10, W-80, bloc_top+210), radius=28, blur=30, opacity=110)
    box = Image.new("RGBA", (W-160, 210), (255,255,255,10))
    box_draw = ImageDraw.Draw(box)
    f_title = _font(72, bold=True)
    f_mid   = _font(54, bold=False)
    text1 = f"{lot.upper()} – CONCURSO"
    text2 = str(concurso)
    text3 = f"Sorteio: {data_br}"
    box_draw.text((60, 18), text1, font=f_title, fill=(255,255,255,235))
    # centralizar o número do concurso
    w2,_ = box_draw.textbbox((0,0), text2, font=f_title)[2:]
    box_draw.text(((W-160-w2)/2, 18+72+6), text2, font=f_title, fill=(255,255,255,235))
    box_draw.text((60, 18+72+6+72+8), text3, font=f_mid, fill=(235,235,245,220))
    img.alpha_composite(box, (80, bloc_top-10))

    # Números (bolas)
    raw = (str(numeros_str or "").replace(";", ",").replace(" ", ","))
    nums = [n for n in (x.strip() for x in raw.split(",")) if n]
    maxn = NUM_QTD.get(key, 6)
    nums = nums[:maxn] if nums else ["?"]*maxn

    n = len(nums)
    row_y = 520
    r = 70
    spacing = 24
    total_w = n*(2*r) + (n-1)*spacing
    start_x = (W - total_w)//2 + r

    for i, num in enumerate(nums):
        cx = start_x + i*(2*r + spacing)
        _ball(draw, img, cx, row_y, r, color_rgb, num)

    # Linha do link "Ver resultado completo…"
    if url:
        f_link = _font(40, bold=False)
        link_text = "Ver resultado completo no Portal SimonSports"
        # ícone de corrente simples
        ix,iy = 110, 650
        draw.arc((ix,iy,ix+34,iy+34), start=200, end=340, fill=(230,230,240,230), width=5)
        draw.arc((ix+26,iy,ix+60,iy+34), start=20, end=160, fill=(230,230,240,230), width=5)
        draw.line((ix+18,iy+26, ix+42,iy+8), fill=(230,230,240,230), width=5)
        draw.text((ix+72, iy+2), link_text, font=f_link, fill=(245,245,255,235))

    # Rodapé com barra
    footer_h = 120
    footer = Image.new("RGBA", (W, footer_h), _hex_to_rgb(c2) + (255,))
    img.alpha_composite(footer, (0, H-footer_h))
    f_foot = _font(64, bold=True)
    text_footer = "PORTAL SIMONSPORTS"
    wft, hft = draw.textbbox((0,0), text_footer, font=f_foot)[2:]
    draw.text(((W-wft)/2, H-footer_h + (footer_h-hft)/2), text_footer, font=f_foot, fill=(255,255,255,255))

    # Saída
    out = BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out