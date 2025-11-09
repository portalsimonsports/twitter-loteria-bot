# app/imaging.py — Portal SimonSports (1080x1080) com LOGO por loteria
# Gera imagem oficial para X/FB/Telegram/Discord/Pinterest
# Uso:
#   from app.imaging import gerar_imagem_loteria
#   buf = gerar_imagem_loteria("Quina", "6870", "04/11/2025", "18,19,20,42,46", "https://...")

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import math

# =========================
# Paleta oficial por loteria
# =========================
CORES = {
    "mega-sena":   ("#209869", "#155f42"),
    "quina":       ("#6c2aa6", "#4a1d73"),
    "lotofacil":   ("#dd4a91", "#9a2f60"),
    "lotofácil":   ("#dd4a91", "#9a2f60"),
    "lotomania":   ("#ff8c00", "#c96c00"),
    "timemania":   ("#00a650", "#04753a"),
    "dupla sena":  ("#8b0000", "#5d0000"),
    "dupla-sena":  ("#8b0000", "#5d0000"),
    "federal":     ("#8b4513", "#5e2f0d"),
    "dia de sorte":("#ffd700", "#c7a600"),
    "dia-de-sorte":("#ffd700", "#c7a600"),
    "super sete":  ("#ff4500", "#b53100"),
    "super-sete":  ("#ff4500", "#b53100"),
    "loteca":      ("#38761d", "#245212"),  # solicitado
}

# Quantidade de bolas (apenas informativo; layout é dinâmico)
NUM_QTD = {
    "mega-sena": 6, "quina": 5, "lotofácil": 15, "lotofacil": 15, "lotomania": 20,
    "timemania": 10, "dupla sena": 6, "dupla-sena": 6, "federal": 5, "dia de sorte": 7,
    "dia-de-sorte": 7, "super sete": 7, "super-sete": 7, "loteca": 14,
}

# Caminho dos logos (repo)
LOGOS_DIR = os.path.join("assets", "logos")

# =========================
# Helpers de desenho
# =========================
def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _font(size, bold=False):
    # Tenta fontes comuns; volta p/ default se não houver
    try:
        path = "arialbd.ttf" if bold else "arial.ttf"
        return ImageFont.truetype(path, size)
    except:
        try:
            path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
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

def _load_logo(slug: str, max_h: int = 120):
    """
    Carrega assets/logos/<slug>.png se existir; redimensiona mantendo proporção
    e retorna a imagem (RGBA) ou None.
    """
    if not slug: return None
    fname = os.path.join(LOGOS_DIR, f"{slug}.png")
    if not os.path.exists(fname):  # tenta variação sem hifen
        alt = os.path.join(LOGOS_DIR, f"{slug.replace('-', '')}.png")
        if os.path.exists(alt): fname = alt
        else: return None
    try:
        lg = Image.open(fname).convert("RGBA")
        w, h = lg.size
        if h > max_h:
            scale = max_h / float(h)
            lg = lg.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
        return lg
    except Exception:
        return None

def _ball(draw, img, cx, cy, r, number: str, color_rgb):
    # sombra abaixo
    sh = Image.new("RGBA", (r*4, r*2), (0,0,0,0))
    sd = ImageDraw.Draw(sh)
    sd.ellipse((0, r*0.2, r*4, r*1.6), fill=(0,0,0,115))
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(sh, (int(cx-2*r), int(cy+r-10)))

    # esfera
    ball = Image.new("RGBA", (r*2, r*2), (0,0,0,0))
    bd = ImageDraw.Draw(ball)
    bd.ellipse((0,0,2*r,2*r), fill=(255,255,255,255))
    # brilho
    bd.ellipse((int(0.34*r), int(0.32*r), int(1.28*r), int(1.1*r)), fill=(255,255,255,255))
    ball = ball.filter(ImageFilter.GaussianBlur(0.5))
    img.alpha_composite(ball, (int(cx-r), int(cy-r)))

    # número
    f = _font(56 if len(number)<=2 else 48, bold=True)
    w,h = draw.textbbox((0,0), number, font=f)[2:]
    draw.text((cx-w/2, cy-h/2-1), number, font=f, fill=color_rgb)

def _format_numeros(raw: str):
    s = (raw or "").replace(";", ",").replace(" ", ",")
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out = []
    for p in parts:
        only = "".join(ch for ch in p if ch.isdigit())
        if only and len(only) <= 2:
            out.append(only.zfill(2))
        else:
            # mantém token (ex.: 1X2 da Loteca)
            out.append(p)
    return out

def _slug(text: str):
    t = (text or "").lower()
    # mapeia por inclusão
    for k in ["mega-sena","quina","lotofácil","lotofacil","lotomania","timemania",
              "dupla sena","dupla-sena","federal","dia de sorte","dia-de-sorte",
              "super sete","super-sete","loteca"]:
        if k in t:
            return k.replace(" ", "-")
    # fallback simples
    return t.replace(" ", "-")

# =========================
# Layout principal
# =========================
def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url):
    # Normaliza chaves/cores
    key = _slug(loteria)
    c1,c2 = CORES.get(key, ("#4b0082","#2b004a"))
    color_rgb = _hex_to_rgb(c1)

    # Canvas
    W = H = 1080
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, W, H, c1, c2)

    # Header com logo/título
    top_y = 60
    logo = _load_logo(key, max_h=120)
    if logo:
        lw, lh = logo.size
        x = 80
        img.alpha_composite(logo, (x, top_y))
        # Título ao lado, adaptando tamanho para não estourar
        max_w = W - (x+lw+80) - 80
        size = 92
        title = (loteria or "").upper()
        while size > 40 and draw.textbbox((0,0), title, font=_font(size, True))[2] > max_w:
            size -= 2
        draw.text((x+lw+60, top_y + max(0,(lh-size)//2)), title, font=_font(size, True), fill=(255,255,255,255))
    else:
        # Sem logo: centraliza título grande
        size = 110
        title = (loteria or "").upper()
        while size > 48 and draw.textbbox((0,0), title, font=_font(size, True))[2] > W - 160:
            size -= 2
        tw, th = draw.textbbox((0,0), title, font=_font(size, True))[2:]
        draw.text(((W-tw)//2, top_y), title, font=_font(size, True), fill=(255,255,255,255))

    # Bloco com concurso + data
    bloc_top = 230
    _shadow_rounded_rect(img, (80, bloc_top-12, W-80, bloc_top+210), radius=26, blur=26, opacity=110)
    box = Image.new("RGBA", (W-160, 210), (255,255,255,12))
    boxd = ImageDraw.Draw(box)

    f1 = _font(68, True)
    f2 = _font(60, True)
    f3 = _font(48, False)

    t1 = "CONCURSO"
    t2 = str(concurso or "")
    t3 = f"Sorteio: {data_br}"

    # Ajustes para não estourar
    # reduz número do concurso se necessário
    while boxd.textbbox((0,0), t2, font=f2)[2] > (W-160 - 120):
        f2 = _font(f2.size-2, True)
        if f2.size <= 36: break

    boxd.text((60, 16), t1, font=f1, fill=(255,255,255,235))
    # centra o número do concurso
    w2,_ = boxd.textbbox((0,0), t2, font=f2)[2:]
    boxd.text(((W-160-w2)/2, 16+68+6), t2, font=f2, fill=(255,255,255,235))
    boxd.text((60, 16+68+6+60+8), t3, font=f3, fill=(235,235,245,220))
    img.alpha_composite(box, (80, bloc_top-12))

    # Área de números (grade)
    nums = _format_numeros(numeros_str)
    if key in ("loteca",):
        # Para Loteca (placares 1X2), mostra uma faixa com o texto (sem bolas)
        info_h = 120
        _shadow_rounded_rect(img, (80, 520-10, W-80, 520-10+info_h), radius=22, blur=24, opacity=110)
        info = Image.new("RGBA", (W-160, info_h), (255,255,255,14))
        infd = ImageDraw.Draw(info)
        ft = _font(44, True)
        text = ", ".join(nums) if nums else "—"
        # encolhe se passar
        while infd.textbbox((0,0), text, font=ft)[2] > (W-160 - 120) and ft.size > 24:
            ft = _font(ft.size-2, True)
        tw, th = infd.textbbox((0,0), text, font=ft)[2:]
        infd.text(((W-160-tw)//2, (info_h-th)//2), text, font=ft, fill=(255,255,255,240))
        img.alpha_composite(info, (80, 520-10))
    else:
        # Distribuição automática de bolas em até 3 linhas
        n = max(1, len(nums))
        # regra simples: muitas (>=18) → 3 linhas; 9..17 → 2 linhas; <=8 → 1 linha
        if n >= 18:
            rows_layout = [math.ceil(n/3.0)]*3
            while sum(rows_layout) > n: rows_layout[-1] -= 1
        elif n >= 9:
            a = math.ceil(n/2.0); b = n - a
            rows_layout = [a, b]
        else:
            rows_layout = [n]

        r = 68  # raio base
        gap = 22
        start_y = 520
        color = color_rgb

        idx = 0
        for row_count in rows_layout:
            total_w = row_count*(2*r) + (row_count-1)*gap
            start_x = (W - total_w)//2 + r
            cy = start_y
            for _ in range(row_count):
                if idx >= n: break
                cx = start_x + _*(2*r + gap)
                _ball(draw, img, cx, cy, r, nums[idx], color)
                idx += 1
            start_y += 2*r + 24  # próxima linha

    # Linha do link "Ver resultado completo…"
    if url:
        f_link = _font(40, False)
        link_text = "Ver resultado completo no Portal SimonSports"
        ix,iy = 110, 760
        # ícone corrente
        draw.arc((ix,iy,ix+34,iy+34), start=200, end=340, fill=(230,230,240,230), width=5)
        draw.arc((ix+26,iy,ix+60,iy+34), start=20, end=160, fill=(230,230,240,230), width=5)
        draw.line((ix+18,iy+26, ix+42,iy+8), fill=(230,230,240,230), width=5)
        # encolhe link se necessário
        while draw.textbbox((0,0), link_text, font=f_link)[2] > (W-220) and f_link.size > 26:
            f_link = _font(f_link.size-2, False)
        draw.text((ix+72, iy+2), link_text, font=f_link, fill=(245,245,255,235))

    # Rodapé
    footer_h = 120
    footer = Image.new("RGBA", (W, footer_h), _hex_to_rgb(c2) + (255,))
    img.alpha_composite(footer, (0, H-footer_h))
    f_foot = _font(64, True)
    text_footer = "PORTAL SIMONSPORTS"
    # encolhe se necessário
    while draw.textbbox((0,0), text_footer, font=f_foot)[2] > (W-120) and f_foot.size > 36:
        f_foot = _font(f_foot.size-2, True)
    wft, hft = draw.textbbox((0,0), text_footer, font=f_foot)[2:]
    draw.text(((W-wft)/2, H-footer_h + (footer_h-hft)/2), text_footer, font=f_foot, fill=(255,255,255,255))

    out = BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out