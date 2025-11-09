# imaging.py — Estilo Portal SimonSports (1080x1080)
# Rev: 2025-11-09e
# - Regras de linhas:
#   • Máx. 7/linha (padrão)
#   • Lotofácil = 5+5+5
#   • Lotomania = 5+5+5+5
#   • Timemania = 5+5 (+ extra "time" em pill)
#   • Dupla Sena = 6 + 6 com títulos
#   • Dia de Sorte = 7 (+ extra "mês" em pill)
#   • Loteca = Tabela 14 jogos (# | Mandante | Placar/1X2 | Visitante)
#     - Destaque #38761d no vencedor (nome do time) ou, em empate, na coluna Placar/1X2

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

# Quantidades oficiais (para truncar se vier excedente)
NUM_QTD = {
    "mega-sena": 6, "quina": 5, "lotofacil": 15, "lotomania": 20,
    "timemania": 10, "dupla-sena": 12, "federal": 5, "dia-de-sorte": 7,
    "super-sete": 7, "loteca": 14,
}

# -------------- utils básicos --------------
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

# ------------- parsing -------------
def _split_tokens_numbers_and_extras(numeros_str):
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

def _split_loteca_lines(numeros_str):
    s = str(numeros_str or "").strip()
    if not s: return []
    # divide por quebras comuns
    for sep in ("\n", ";", "|"):
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            if len(parts) >= 10:  # geralmente 14
                return parts[:14]
    # fallback por vírgula (pode vir agrupado por linha)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    # junta de 3 em 3 quando possível (#heurística)
    if len(parts) >= 30:
        out = []
        chunk, acc = [], []
        for p in parts:
            acc.append(p)
            if len(acc) >= 3:
                out.append(" ".join(acc)); acc = []
            if len(out) == 14: break
        return out
    return parts[:14]

# ------------- regras de linhas -------------
def _rows_default_max7(qtd):
    rows = []
    i = 0
    while i < qtd:
        take = min(7, qtd - i)
        rows.append(take)
        i += take
    return rows

def _layout_rows(slug, nums):
    n = len(nums)
    if slug == "lotofacil" and n >= 15:   return [5,5,5]
    if slug == "lotomania" and n >= 20:  return [5,5,5,5]
    if slug == "timemania" and n >= 10:  return [5,5]
    if slug == "dupla-sena" and n >= 12: return [6,6]
    return _rows_default_max7(n)

# ----------- Loteca: tabela 14 jogos -----------
def _parse_game_line(text):
    """Tenta separar Mandante, placar/1X2, Visitante e determinar vencedor."""
    t = re.sub(r"\s+", " ", str(text or "").strip())
    # Formato com placar: TimeA 2-1 TimeB ou 2x1 / 2:1
    m = re.match(r"^(.*?)[\s\-–—]{1,3}(\d+)\s*([xX\-–:])\s*(\d+)[\s\-–—]{1,3}(.*)$", t)
    if m:
        home, g1, sep, g2, away = [x.strip(" -–—") for x in m.groups()]
        try:
            a, b = int(g1), int(g2)
            if a > b: winner = "home"
            elif b > a: winner = "away"
            else: winner = "draw"
        except:
            winner = "draw" if sep.lower()=="x" else None
        placar = f"{g1}{sep}{g2}"
        return home, placar, away, winner
    # Formato 1X2: TimeA X TimeB
    m2 = re.match(r"^(.*?)[\s\-–—]{1,3}[xX]{1}[\s\-–—]{1,3}(.*)$", t)
    if m2:
        home, away = [x.strip(" -–—") for x in m2.groups()]
        return home, "X", away, "draw"
    # fallback: tudo no meio
    return "", t, "", None

def _render_loteca_table(img, draw, slug, loteria, concurso, data_br, lines, c1, c2):
    W, H = img.size
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

    # tabela
    y0 = top + box_h + 16
    header_h = 48
    row_h = 42
    gap = 10
    col_w = {
        "idx": 66,
        "home": 370,
        "res":  160,
        "away": 370
    }
    total_w = sum(col_w.values())
    start_x = pad + (W - pad*2 - total_w)//2

    # header row
    _shadow(img, (start_x, y0, start_x+total_w, y0+header_h), radius=10, blur=16, opacity=80)
    draw.rounded_rectangle((start_x, y0, start_x+total_w, y0+header_h),
                           radius=10, fill=(0,0,0,80))
    fh = _font(28, bold=True)
    draw.text((start_x+16, y0+10), "#", font=fh, fill=(255,255,255,230))
    draw.text((start_x+col_w["idx"]+16, y0+10), "Mandante", font=fh, fill=(255,255,255,230))
    draw.text((start_x+col_w["idx"]+col_w["home"]+16, y0+10), "Placar/1X2", font=fh, fill=(255,255,255,230))
    draw.text((start_x+col_w["idx"]+col_w["home"]+col_w["res"]+16, y0+10), "Visitante", font=fh, fill=(255,255,255,230))

    # linhas
    y = y0 + header_h + gap
    hi_bg = _hex_to_rgb(CORES["loteca"][0])
    for i in range(14):
        line = lines[i] if i < len(lines) else ""
        home, res, away, winner = _parse_game_line(line)

        # faixa da linha
        draw.rounded_rectangle((start_x, y, start_x+total_w, y+row_h),
                               radius=10, fill=(255,255,255,14))

        # áreas das colunas
        x_idx = start_x
        x_home = x_idx + col_w["idx"]
        x_res  = x_home + col_w["home"]
        x_away = x_res  + col_w["res"]

        # textos
        fidx  = _font(26, bold=True)
        fteam = _font(28, bold=True)
        fres  = _font(28, bold=True)

        # destaque
        def hi(rect):
            draw.rounded_rectangle(rect, radius=8, fill=hi_bg + (255,))
        def txt(x, yy, t, f, col=(255,255,255,245)):
            draw.text((x, yy), t, font=f, fill=col)

        # idx
        txt(x_idx+16, y+8, f"#{i+1}", fidx)

        # home / res / away (com possíveis destaques)
        if winner == "home":
            hi((x_home+8, y+6, x_res-8, y+row_h-6))
            txt(x_home+18, y+8, home or "-", fteam, (255,255,255,255))
            txt(x_res+18,  y+8, res  or "-", fres)
            txt(x_away+18, y+8, away or "-", fteam)
        elif winner == "away":
            hi((x_away+8, y+6, start_x+total_w-8, y+row_h-6))
            txt(x_home+18, y+8, home or "-", fteam)
            txt(x_res+18,  y+8, res  or "-", fres)
            txt(x_away+18, y+8, away or "-", fteam, (255,255,255,255))
        elif winner == "draw":
            hi((x_res+8, y+6, x_away-8, y+row_h-6))
            txt(x_home+18, y+8, home or "-", fteam)
            txt(x_res+18,  y+8, res  or "X", fres, (255,255,255,255))
            txt(x_away+18, y+8, away or "-", fteam)
        else:
            txt(x_home+18, y+8, home or "-", fteam)
            txt(x_res+18,  y+8, res  or "-", fres)
            txt(x_away+18, y+8, away or "-", fteam)

        y += row_h + gap

    # rodapé
    footer_h = 110
    _shadow(img, (0, H-footer_h-8, W, H), radius=0, blur=24, opacity=90)
    footer = Image.new("RGBA", (W, footer_h), _hex_to_rgb(CORES["loteca"][1])+(255,))
    img.alpha_composite(footer, (0, H-footer_h))
    brand = "PORTAL SIMONSPORTS"
    fb = _text_fit(draw, brand, W - pad*2, 64, bold=True, min_size=42)
    bw,bh = draw.textbbox((0,0), brand, font=fb)[2:]
    draw.text(((W-bw)/2, H-footer_h + (footer_h-bh)/2), brand, font=fb, fill=(255,255,255,255))

# --------- Demais renderizações ----------
def _render_dupla_sena(img, draw, slug, c1, pad, W, nums, extras, color_rgb):
    y = 470
    for title, arr in (("1º SORTEIO", nums[:6]), ("2º SORTEIO", nums[6:12] if len(nums)>6 else [])):
        if not arr: continue
        fb = _font(54, bold=True)
        tw,_ = draw.textbbox((0,0), title, font=fb)[2:]
        draw.text(((W-tw)/2, y-58), title, font=fb, fill=(255,255,255,240))
        r = 70; spacing = 24
        while len(arr)*(2*r)+(len(arr)-1)*spacing > (W - pad*2) and r > 46:
            r -= 2; spacing = max(16, spacing-1)
        total_w = len(arr)*(2*r) + (len(arr)-1)*spacing
        start_x = pad + (W - pad*2 - total_w)//2 + r
        cy = y
        for j, num in enumerate(arr):
            cx = start_x + j*(2*r + spacing)
            _ball(draw, img, cx, cy, r, color_rgb, num)
        y += 2*r + 110
    if extras:
        extra_text = " • ".join([e.upper() for e in extras])
        fextra = _text_fit(draw, extra_text, W - pad*2, 46, bold=True, min_size=28)
        tw,th = draw.textbbox((0,0), extra_text, font=fextra)[2:]
        px = pad + (W - pad*2 - tw)//2
        py = y - 20
        draw.text((px, py), extra_text, font=fextra, fill=(255,255,255,235))

# ---------------- principal ----------------
def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url):
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

    # painel concurso (não para Loteca, que usa tabela abaixo — mas mantemos para uniformidade)
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
        top = 210
    else:
        top = 210  # usado na tabela

    # ——— LOTECA ———
    if slug == "loteca":
        lines = _split_loteca_lines(numeros_str)
        _render_loteca_table(img, draw, slug, loteria, concurso, data_br, lines, c1, c2)
    else:
        # tokens numéricos + extras
        nums_all, extras = _split_tokens_numbers_and_extras(numeros_str)
        maxn = NUM_QTD.get(slug, 6)
        nums = nums_all[:maxn] if nums_all else []

        if slug == "dupla-sena":
            _render_dupla_sena(img, draw, slug, c1, pad, W, nums, extras, color_rgb)
        else:
            # layout (máx 7/linha + casos especiais)
            rows_cfg = _layout_rows(slug, nums if nums else ["?"])
            avail_w = W - pad*2
            total_rows = len(rows_cfg)
            vgap = 120
            r = 70
            spacing = 24
            qmax = max(rows_cfg) if rows_cfg else 1
            while qmax*(2*r)+(qmax-1)*spacing > avail_w and r > 46:
                r -= 2
                spacing = max(16, spacing-1)
            block_h = total_rows*(2*r) + (total_rows-1)*vgap
            start_y = 480 - block_h//2 + r
            centers_y = [start_y + i*(2*r + vgap) for i in range(total_rows)]
            idx = 0
            for ri, q in enumerate(rows_cfg):
                line = (nums or ["?"]*q)[idx:idx+q]; idx += q
                total_w = q*(2*r) + (q-1)*spacing
                start_x = pad + (avail_w - total_w)//2 + r
                cy = centers_y[ri]
                for j, num in enumerate(line):
                    cx = start_x + j*(2*r + spacing)
                    _ball(draw, img, cx, cy, r, color_rgb, num)

            # extras (dia de sorte mês / timemania time)
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

    # link “Ver resultado…”
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