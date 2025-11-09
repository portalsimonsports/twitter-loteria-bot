# imaging.py — Estilo Portal SimonSports (1080x1080)
# Rev: 2025-11-09d — regras: 7/linha (padrão); lotofacil=3x5; lotomania=4x5;
# timemania=2x5 (+extra time); dupla-sena=6+6 com títulos; loteca=14 linhas
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os, re

# Paleta oficial
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

# Quantidades “oficiais” (para truncar se vier excedente)
NUM_QTD = {
    "mega-sena": 6, "quina": 5, "lotofacil": 15, "lotomania": 20,
    "timemania": 10, "dupla-sena": 12, "federal": 5, "dia-de-sorte": 7,
    "super-sete": 7, "loteca": 14,
}

# ---------------- utils básicos ----------------
def _norm_key(lot):
    s = (lot or "").lower()
    for a,b in (("á","a"),("à","a"),("â","a"),("ã","a"),("é","e"),("ê","e"),
                ("í","i"),("ó","o"),("ô","o"),("õ","o"),("ú","u"),("ç","c")):
        s = s.replace(a,b)
    return s.replace(" ", "-")

def _hex_to_rgb(h): h=h.lstrip("#"); return tuple(int(h[i:i+2],16) for i in (0,2,4))
def _font(size, bold=False):
    try: return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)
    except: return ImageFont.load_default()

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

def _text_fit(draw, text, max_w, start, bold=False, min_size=22):
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
    f = _text_fit(draw, txt, int(r*1.55), 56 if len(txt)<=2 else 48, bold=True, min_size=34)
    w,h = draw.textbbox((0,0), txt, font=f)[2:]
    draw.text((cx-w/2, cy-h/2-1), txt, font=f, fill=color_rgb)

def _try_logo(slug):
    p = os.path.join("assets","logos", f"{slug}.png")
    if os.path.exists(p):
        try: return Image.open(p).convert("RGBA")
        except: pass
    return None

# ------------ parsing & regras de linhas -------------
def _split_tokens(numeros_str):
    raw = (str(numeros_str or "").replace(";", ",").replace(" ", ","))
    tokens = [x.strip() for x in raw.split(",") if x.strip()]
    nums, extras = [], []
    for t in tokens:
        if re.fullmatch(r"\d{1,2}", t):
            nums.append(t)
        else:
            x = t.strip("-_/., ")
            if x: extras.append(x)
    return nums, extras

def _rows_default_max7(qtd):
    # quebra em linhas de até 7
    rows = []
    i = 0
    while i < qtd:
        take = min(7, qtd - i)
        rows.append(take)
        i += take
    return rows

def _layout_rows(slug, nums):
    n = len(nums)
    if slug == "lotofacil" and n >= 15:    # 15 → 5+5+5
        return [5,5,5]
    if slug == "lotomania" and n >= 20:    # 20 → 5+5+5+5
        return [5,5,5,5]
    if slug == "timemania" and n >= 10:    # 10 → 5+5
        return [5,5]
    if slug == "dupla-sena" and n >= 12:   # 12 → 6+6 (tratado em bloco especial)
        return [6,6]
    # padrão: até 7 por linha
    return _rows_default_max7(n)

# ------------- renderizadores especiais ---------------
def _render_loteca(img, draw, slug, loteria, concurso, data_br, items, c1, c2):
    # 14 linhas verticais (#1..#14) em cartões
    W = H = img.size
    pad = 80
    # header
    titulo = loteria.upper().strip()
    ftitle = _text_fit(draw, titulo, W - pad*2 - 260, 96, bold=True, min_size=58)
    draw.text((pad, 92), titulo, font=ftitle, fill=(255,255,255,255))
    lg = _try_logo(slug)
    if lg:
        lh = 96
        lw = int(lg.width*(lh/lg.height))
        img.alpha_composite(lg.resize((lw,lh), Image.LANCZOS), (W - pad - lw, 88))
    # painel concurso
    box_h = 160; top = 210
    _shadow(img, (pad, top-10, W-pad, top-10+box_h), radius=28, blur=30, opacity=110)
    box = Image.new("RGBA", (W-pad*2, box_h), (255,255,255,12))
    bd = ImageDraw.Draw(box)
    f1 = _text_fit(bd, f"Concurso {concurso}", W - pad*2 - 120, 74, bold=True, min_size=46)
    f2 = _text_fit(bd, f"Sorteio: {data_br}", W - pad*2 - 120, 52, bold=False, min_size=30)
    bd.text((60, 20), f"Concurso {concurso}", font=f1, fill=(255,255,255,235))
    bd.text((60, 20+70), f"Sorteio: {data_br}", font=f2, fill=(235,235,245,220))
    img.alpha_composite(box, (pad, top-10))
    # lista 14 linhas
    y0 = top + box_h + 20
    card_h = 40
    row_gap = 18
    fline = _font(36, bold=True)
    for i in range(14):
        val = items[i] if i < len(items) else ""
        y = y0 + i*(card_h + row_gap)
        # tarja
        draw.rounded_rectangle((pad, y, W-pad, y+card_h), radius=12, fill=_hex_to_rgb(c2)+(160,))
        # índice + valor
        idx_txt = f"#{i+1}"
        draw.text((pad+16, y+6), idx_txt, font=_font(30, bold=True), fill=(255,255,255,240))
        draw.text((pad+90, y+2), str(val), font=fline, fill=(255,255,255,245))
    # rodapé
    footer_h = 110
    _shadow(img, (0, H-footer_h-8, W, H), radius=0, blur=24, opacity=90)
    footer = Image.new("RGBA", (W, footer_h), _hex_to_rgb(c2)+(255,))
    img.alpha_composite(footer, (0, H-footer_h))
    brand = "PORTAL SIMONSPORTS"
    fb = _text_fit(draw, brand, W - pad*2, 64, bold=True, min_size=42)
    bw,bh = draw.textbbox((0,0), brand, font=fb)[2:]
    draw.text(((W-bw)/2, H-footer_h + (footer_h-bh)/2), brand, font=fb, fill=(255,255,255,255))
    return

# ----------------- principal -----------------
def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url):
    # slug normalizado
    slug = _norm_key(loteria)
    if "dupla" in slug and "sena" in slug: slug = "dupla-sena"
    if "dia" in slug and "sorte" in slug: slug = "dia-de-sorte"
    if "lotofac" in slug: slug = "lotofacil"

    c1,c2 = CORES.get(slug, ("#4B0082","#2B004A"))
    color_rgb = _hex_to_rgb(c1)

    W = H = 1080
    img = Image.new("RGBA", (W,H), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, W, H, c1, c2)

    pad = 80

    # header
    titulo = (loteria or "").upper().strip()
    f_title = _text_fit(draw, titulo, W - pad*2 - 260, 96, bold=True, min_size=58)
    draw.text((pad, 92), titulo, font=f_title, fill=(255,255,255,255))
    lg = _try_logo(slug)
    if lg:
        lh = 96; lw = int(lg.width*(lh/lg.height))
        img.alpha_composite(lg.resize((lw,lh), Image.LANCZOS), (W - pad - lw, 88))

    # painel concurso
    if slug != "loteca":
        box_h = 180; top = 210
        _shadow(img, (pad, top-10, W-pad, top-10+box_h), radius=28, blur=30, opacity=110)
        box = Image.new("RGBA", (W-pad*2, box_h), (255,255,255,12))
        bd = ImageDraw.Draw(box)
        f1 = _text_fit(bd, f"Concurso {concurso}", W - pad*2 - 120, 72, bold=True, min_size=48)
        f2 = _text_fit(bd, f"Sorteio: {data_br}", W - pad*2 - 120, 54, bold=False, min_size=30)
        bd.text((60, 20), f"Concurso {concurso}", font=f1, fill=(255,255,255,235))
        bd.text((60, 20+70), f"Sorteio: {data_br}", font=f2, fill=(235,235,245,220))
        img.alpha_composite(box, (pad, top-10))
    else:
        top = 210  # usado pelo renderer da loteca

    # tokens
    nums_all, extras = _split_tokens(numeros_str)

    # LOTECA: 14 linhas em lista
    if slug == "loteca":
        items = nums_all + extras
        _render_loteca(img, draw, slug, loteria, concurso, data_br, items, c1, c2)
        out = BytesIO(); img.convert("RGB").save(out, format="PNG", optimize=True); out.seek(0)
        return out

    # truncar ao máximo oficial
    maxn = NUM_QTD.get(slug, 6)
    nums = nums_all[:maxn] if nums_all else []

    # DUPLA SENA (6 + 6, dois blocos com título)
    if slug == "dupla-sena":
        # garante 12 elementos (ou o que houver)
        a = nums[:6]
        b = nums[6:12] if len(nums) > 6 else []
        # desenha dois blocos de bolas
        blocks = [("1º SORTEIO", a), ("2º SORTEIO", b)]
        y = 470
        for title, arr in blocks:
            if not arr: continue
            # título do bloco
            fb = _font(54, bold=True)
            tw,_ = draw.textbbox((0,0), title, font=fb)[2:]
            draw.text(((W-tw)/2, y-58), title, font=fb, fill=(255,255,255,240))
            # medidas
            r = 70; spacing = 24
            while len(arr)*(2*r)+(len(arr)-1)*spacing > (W - pad*2) and r > 46:
                r -= 2; spacing = max(16, spacing-1)
            total_w = len(arr)*(2*r) + (len(arr)-1)*spacing
            start_x = pad + (W - pad*2 - total_w)//2 + r
            cy = y
            for j, num in enumerate(arr):
                cx = start_x + j*(2*r + spacing)
                _ball(draw, img, cx, cy, r, color_rgb, num)
            y += 2*r + 110  # separação entre blocos
        # extras (se vier time/mês por engano)
        if extras:
            extra_text = " • ".join([e.upper() for e in extras])
            fextra = _text_fit(draw, extra_text, W - pad*2, 46, bold=True, min_size=28)
            tw,th = draw.textbbox((0,0), extra_text, font=fextra)[2:]
            px = pad + (W - pad*2 - tw)//2
            py = y - 20
            draw.text((px, py), extra_text, font=fextra, fill=(255,255,255,235))
    else:
        # demais loterias (inclui regras especiais)
        rows_cfg = _layout_rows(slug, nums if nums else ["?"])
        # medidas base
        avail_w = W - pad*2
        total_rows = len(rows_cfg)
        vgap = 120
        r = 70
        spacing = 24
        # ajuste p/ maior linha
        qmax = max(rows_cfg) if rows_cfg else 1
        while qmax*(2*r)+(qmax-1)*spacing > avail_w and r > 46:
            r -= 2
            spacing = max(16, spacing-1)
        # bloco vertical central
        block_h = total_rows*(2*r) + (total_rows-1)*vgap
        start_y = 480 - block_h//2 + r
        centers_y = [start_y + i*(2*r + vgap) for i in range(total_rows)]
        # desenha
        idx = 0
        for ri, q in enumerate(rows_cfg):
            line = (nums or ["?"]*q)[idx:idx+q]; idx += q
            total_w = q*(2*r) + (q-1)*spacing
            start_x = pad + (avail_w - total_w)//2 + r
            cy = centers_y[ri]
            for j, num in enumerate(line):
                cx = start_x + j*(2*r + spacing)
                _ball(draw, img, cx, cy, r, color_rgb, num)

        # extras em “pill” na linha de baixo
        if extras:
            extra_text = " • ".join([e.upper() for e in extras])
            fextra = _text_fit(draw, extra_text, avail_w, 46, bold=True, min_size=28)
            tw,th = draw.textbbox((0,0), extra_text, font=fextra)[2:]
            pill_pad_x, pill_pad_y = 22, 10
            px0 = pad + (avail_w - (tw+pill_pad_x*2))//2
            py0 = centers_y[-1] + r + 26
            px1 = px0 + tw + pill_pad_x*2
            py1 = py0 + th + pill_pad_y*2
            draw.rounded_rectangle((px0,py0,px1,py1), radius=18, fill=(0,0,0,90))
            draw.text((px0+pill_pad_x, py0+pill_pad_y), extra_text, font=fextra, fill=(255,255,255,230))

    # linha “Ver resultado completo…”
    if url:
        label = "Ver resultado completo no Portal SimonSports"
        f3 = _text_fit(draw, label, W - pad*2 - 92, 42, bold=False, min_size=28)
        ix = pad; iy = 860
        draw.arc((ix,iy,ix+34,iy+34), start=200, end=340, fill=(230,230,240,230), width=5)
        draw.arc((ix+26,iy,ix+60,iy+34), start=20, end=160, fill=(230,230,240,230), width=5)
        draw.line((ix+18,iy+26, ix+42,iy+8), fill=(230,230,240,230), width=5)
        draw.text((ix+72, iy+2), label, font=f3, fill=(245,245,255,235))

    # rodapé
    footer_h = 110
    _shadow(img, (0, H-footer_h-8, W, H), radius=0, blur=24, opacity=90)
    footer = Image.new("RGBA", (W, footer_h), _hex_to_rgb(c2)+(255,))
    img.alpha_composite(footer, (0, H-footer_h))
    brand = "PORTAL SIMONSPORTS"
    fb = _text_fit(draw, brand, W - pad*2, 64, bold=True, min_size=42)
    bw,bh = draw.textbbox((0,0), brand, font=fb)[2:]
    draw.text(((W-bw)/2, H-footer_h + (footer_h-bh)/2), brand, font=fb, fill=(255,255,255,255))

    out = BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out