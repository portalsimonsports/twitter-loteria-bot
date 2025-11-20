# app/imaging.py — Portal SimonSports
# Rev: 2025-11-19c — Loteca: usa placar oficial nos campos G×G + rodapé "Portal SimonSports"
# - Coleta gols prefixados/sufixados aos nomes (ex.: "2 PONTE..." / "JUVENTUDE 1 (Sáb)")
# - Remove os números dos nomes e preenche G1/G2
# - Destaque vencedor (time+placar) ou "X" no empate
# - Rodapé fixo "Portal SimonSports"
# - Mantém:
#     • Dupla Sena: "1º/2º SORTEIO" acima dos números
#     • Timemania/Dia de Sorte: linha extra (Time/Mês)
#     • Mais Milionária: "NÚMEROS" + "TREVOS DA SORTE"

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import os
import re
import math

# ==========================
# CONFIG GERAL
# ==========================

W, H = 1080, 1080
M = 80

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
LOGOS_DIR  = os.path.join(ASSETS_DIR, "logos")

SHOW_CTA = False                   # CTA desativado por padrão (pedido)
BRAND_TEXT = "Portal SimonSports"  # rodapé

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
# CORES
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
    "loteca":       (56, 118, 29),   # ≈ #38761d
}

HIGHLIGHT   = (56, 118, 29)  # destaque vencedor/empate Loteca
TEXT_LIGHT  = (235, 235, 245)

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
    if (nome or "").lower() in CORES_LOTERIAS:
        return CORES_LOTERIAS[nome.lower()]
    return CORES_LOTERIAS.get(_slug(nome or "loteria"), (30, 30, 30))

# ==========================
# FUNDO
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
    for ext in ("png", "jpg", "jpeg"):
        p = os.path.join(LOGOS_DIR, f"{slug}.{ext}")
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
# PARSE GERAL (bolinhas)
# ==========================

def parse_numeros(loteria_nome: str, numeros_str: str):
    s = (numeros_str or "").strip()

    extra = None
    m = re.search(r"(?:-|;)\s*([A-Za-zÀ-ÿ0-9/ \.\-]+)$", s)
    if m:
        extra = m.group(1).strip()
        s = s[:m.start()].strip(",; -")

    s = s.replace("–", "-")
    s = re.sub(r"[;| ]+", ",", s)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    nums = [p.zfill(2) if re.fullmatch(r"\d+", p) else p for p in parts]

    n = len(nums); rows = []
    nome = (loteria_nome or "").lower()

    if "lotofacil" in nome:
        rows = [nums[i:i+5] for i in range(0, n, 5)]
    elif "lotomania" in nome:
        rows = [nums[i:i+5] for i in range(0, min(20, n), 5)]
    elif "timemania" in nome:
        rows = [nums] if n <= 7 else [nums[:7], nums[7:]]
    elif "dupla" in nome:
        rows = [nums[i:i+6] for i in range(0, n, 6)]
    else:
        if n <= 8:
            rows = [nums]
        elif n <= 16:
            mid = math.ceil(n/2)
            rows = [nums[:mid], nums[mid:]]
        else:
            terc = math.ceil(n/3)
            rows = [nums[:terc], nums[terc:2*terc], nums[2*terc:]]

    rows = [r for r in rows if r]
    return rows, extra

# ==========================
# MAIS MILIONÁRIA — parser
# ==========================

def parse_mais_milionaria(numeros_str: str):
    s = (numeros_str or "").strip()
    m = re.search(r"trevos?(?:\s+da\s+sorte)?\s*[:\-]?\s*(.+)$", s, flags=re.I)
    trevos_part = None
    if m:
        trevos_part = m.group(1)
        s_main = s[:m.start()].strip(",; |-")
    else:
        toks = [t.strip() for t in re.split(r"[,\s|;]+", s) if t.strip()]
        s_main = ",".join(toks)
        if len(toks) >= 8 and all(re.fullmatch(r"\d{1,2}", t) for t in toks[-2:]) \
           and all(1 <= int(t) <= 6 for t in toks[-2:]):
            trevos_part = ",".join(toks[-2:])
            s_main = ",".join(toks[:-2])

    main = [p.zfill(2) for p in re.split(r"[,\s|;]+", s_main) if re.fullmatch(r"\d{1,2}", p)]
    main = main[:12]

    trevos = []
    if trevos_part:
        for t in re.split(r"[,\s|;]+", trevos_part):
            t = t.strip()
            if re.fullmatch(r"\d{1,2}", t):
                v = int(t)
                if 1 <= v <= 6:
                    trevos.append(str(v))
        trevos = trevos[:2]

    return main, trevos

# ==========================
# DESENHO — bolinhas (geral)
# ==========================

def desenhar_bolinhas(draw: ImageDraw.ImageDraw, loteria_nome: str,
                      numeros_str: str, area_box):
    x0, y0, x1, y1 = area_box
    largura = x1 - x0
    altura  = y1 - y0

    nome_lc = (loteria_nome or "").lower()
    is_dupla = "dupla" in nome_lc
    is_time  = "timemania" in nome_lc
    is_dias  = ("dia-de-sorte" in nome_lc) or ("dia de sorte" in nome_lc)
    is_mm    = ("milion" in nome_lc)

    # ===== Mais Milionária =====
    if is_mm:
        nums, trevos = parse_mais_milionaria(numeros_str)
        if not nums: return

        max_cols = max(1, len(nums))
        r = 62 if max_cols <= 7 else (54 if max_cols <= 10 else 46)
        gap_x = 28 if r == 62 else (22 if r == 54 else 20)
        r_trevo = int(r * 0.80)
        font_num   = FONT_SANS(46, bold=True)
        font_label = FONT_SANS(30, bold=True)

        label_h = 40
        gap_between = 40
        total_h = (label_h + 2*r) + (gap_between if trevos else 0) + (label_h + 2*r_trevo if trevos else 0)
        start_y = y0 + max(0, (altura - total_h) // 2)

        # NÚMEROS
        txt = "NÚMEROS"
        tw = draw.textlength(txt, font=font_label)
        draw.text(((x0+x1)/2 - tw/2, start_y), txt, font=font_label, fill=(245,245,245))
        cy = start_y + label_h + r
        cols = len(nums)
        total_w_row = cols * (2*r + gap_x) - gap_x
        start_x = x0 + (largura - total_w_row) // 2
        for i, token in enumerate(nums):
            cx = start_x + i * (2*r + gap_x) + r
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(255,255,255))
            t = str(token); tn = draw.textlength(t, font=font_num)
            th = FONT_SANS(46, True).getbbox(t)[3] - FONT_SANS(46, True).getbbox(t)[1]
            draw.text((cx - tn/2, cy - th/2 - 2), t, font=font_num, fill=(20,20,20))

        if trevos:
            base_y = cy + r + gap_between
            txt = "TREVOS DA SORTE"
            tw = draw.textlength(txt, font=font_label)
            draw.text(((x0+x1)/2 - tw/2, base_y), txt, font=font_label, fill=(245,245,245))
            cy2 = base_y + label_h + r_trevo
            cols = len(trevos)
            total_w_row = cols * (2*r_trevo + gap_x) - gap_x
            start_x = x0 + (largura - total_w_row) // 2
            font_trevo = FONT_SANS(40, bold=True)
            for i, token in enumerate(trevos):
                cx = start_x + i * (2*r_trevo + gap_x) + r_trevo
                draw.ellipse((cx-r_trevo, cy2-r_trevo, cx+r_trevo, cy2+r_trevo), fill=HIGHLIGHT)
                t = str(token); tn = draw.textlength(t, font=font_trevo)
                th = font_trevo.getbbox(t)[3] - font_trevo.getbbox(t)[1]
                draw.text((cx - tn/2, cy2 - th/2 - 2), t, font=font_trevo, fill=(255,255,255))
        return

    # ===== Demais =====
    rows, extra = parse_numeros(loteria_nome, numeros_str)
    if not rows: return

    labels = []
    if is_dupla and len(rows) > 1:
        labels = [f"{i+1}º SORTEIO" for i in range(len(rows))]
    elif is_time or is_dias:
        labels = ["NÚMEROS"]

    qtd_linhas = len(rows); max_cols = max(len(r) for r in rows)
    if max_cols <= 5: r, gap_x = 62, 28
    elif max_cols <= 8: r, gap_x = 54, 22
    else: r, gap_x = 46, 20

    gap_y = 0 if qtd_linhas == 1 else (40 if qtd_linhas == 2 else 30)
    label_h = 40 if labels else 0
    line_h = label_h + 2*r + gap_y
    total_h = qtd_linhas * line_h - gap_y
    start_y = y0 + max(0, (altura - total_h) // 2)

    circle_color = (255, 255, 255)
    text_color   = (20, 20, 20)
    font_num     = FONT_SANS(46, bold=True)
    font_label   = FONT_SANS(30, bold=True)
    cx_center    = (x0 + x1) / 2

    for ridx, row in enumerate(rows):
        row_top = start_y + ridx * line_h
        if labels:
            txt = labels[ridx] if len(labels) > 1 else labels[0]
            tw  = draw.textlength(txt, font=font_label)
            draw.text((cx_center - tw/2, row_top), txt, font=font_label, fill=(245,245,245))
        cy = row_top + label_h + r

        cols = len(row)
        total_w_row = cols * (2*r + gap_x) - gap_x
        start_x = x0 + (largura - total_w_row) // 2

        for cidx, token in enumerate(row):
            cx = start_x + cidx * (2*r + gap_x) + r
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=circle_color)
            if token:
                txt = str(token)
                tw = draw.textlength(txt, font=font_num)
                th = font_num.getbbox(txt)[3] - font_num.getbbox(txt)[1]
                draw.text((cx - tw/2, cy - th/2 - 2), txt, font=font_num, fill=text_color)

    if extra:
        font_extra = FONT_SANS(38, bold=True)
        label = "TIME DO CORAÇÃO: " if is_time else ("MÊS DA SORTE: " if is_dias else "")
        txt = (label + extra.strip()) if label else extra.strip()
        tw  = draw.textlength(txt, font=font_extra)
        draw.text(((x0 + x1) / 2 - tw / 2, y1 + 10), txt, font=font_extra, fill=(255, 255, 255))

# ==========================
# LOTECA — parser + tabela
# ==========================

# Divide linha em mandante × visitante (aceita 'x', 'X' ou '×')
_SPLIT_X = re.compile(r"\s+[xX×]\s+")

def _strip_index_prefix(s: str) -> str:
    return re.sub(r"^\s*\d{1,2}[\.\)]?\s*", "", s or "")

def _extract_goals_and_name(token: str):
    """
    Recebe um lado (ex.: '2 PONTE PRETA/SP', 'GUARANI/SP 0 (Sáb)') e retorna:
      (nome_limpo, gols or None)
    """
    s = (token or "").strip()
    # remove anotações finais (dia/abreviações) mantendo possível número antes delas
    s = re.sub(r"\s*\((?:Dom|Seg|Ter|Qua|Qui|Sex|Sáb|Sab|[A-Za-z\. ]+)\)\s*$", "", s, flags=re.I)

    # prefixo numérico → gols
    m = re.match(r"^\s*(\d+)\s+(.+)$", s)
    if m:
        return m.group(2).strip(" -"), int(m.group(1))

    # sufixo numérico → gols
    m = re.match(r"^(.+?)\s+(\d+)\s*$", s)
    if m:
        return m.group(1).strip(" -"), int(m.group(2))

    # nenhum número
    return s.strip(" -"), None

def _clean_team_name(s: str) -> str:
    # garante remoção de qualquer "(...)" final remanescente
    s = re.sub(r"\s*\([^)]+\)\s*$", "", s or "")
    # remove possíveis números soltos
    s = re.sub(r"^\s*\d+\s+", "", s)
    s = re.sub(r"\s+\d+\s*$", "", s)
    return s.strip(" -")

def _parse_loteca(numeros_str: str):
    """
    Retorna lista de 14 dicts: {idx, mandante, visitante, g1, g2, resultado}
    - Lê JSON (lista) OU texto (quebras de linha/pipe).
    - Extrai gols colados aos nomes (prefixo/sufixo).
    """
    jogos = []
    s = (numeros_str or "").strip()

    # JSON?
    if s.startswith("[") or s.startswith("{"):
        try:
            import json
            data = json.loads(s)
            if isinstance(data, dict) and "jogos" in data:
                data = data["jogos"]
            if isinstance(data, list):
                for i, it in enumerate(data, 1):
                    mand_raw = str(it.get("mandante", "")).strip()
                    vist_raw = str(it.get("visitante", "")).strip()
                    mand, g1x = _extract_goals_and_name(mand_raw)
                    vist, g2x = _extract_goals_and_name(vist_raw)
                    g1 = it.get("g1", g1x)
                    g2 = it.get("g2", g2x)
                    res = str(it.get("resultado", "")).upper().strip()
                    if g1 is not None and g2 is not None:
                        try:
                            a, b = int(g1), int(g2)
                            res = "1" if a > b else ("2" if b > a else "X")
                        except: pass
                    jogos.append({"idx": i, "mandante": _clean_team_name(mand),
                                 "visitante": _clean_team_name(vist),
                                 "g1": None if g1 is None else int(g1),
                                 "g2": None if g2 is None else int(g2),
                                 "resultado": res})
        except Exception:
            pass

    # Texto
    if not jogos:
        linhas = re.split(r"\n|\|", s)
        for i, ln in enumerate(linhas, 1):
            t = _strip_index_prefix(ln.strip())
            if not t:
                continue
            parts = _SPLIT_X.split(t)
            if len(parts) != 2:
                continue
            left, right = parts[0], parts[1]
            mand, g1 = _extract_goals_and_name(left)
            vist, g2 = _extract_goals_and_name(right)
            res = ""
            if (g1 is not None) and (g2 is not None):
                try:
                    a, b = int(g1), int(g2)
                    res = "1" if a > b else ("2" if b > a else "X")
                except: pass
            jogos.append({"idx": i, "mandante": _clean_team_name(mand),
                         "visitante": _clean_team_name(vist),
                         "g1": None if g1 is None else int(g1),
                         "g2": None if g2 is None else int(g2),
                         "resultado": res})

    jogos = jogos[:14]
    while len(jogos) < 14:
        jogos.append({"idx": len(jogos)+1, "mandante": "", "visitante": "", "g1": None, "g2": None, "resultado": ""})
    return jogos

def desenhar_loteca(draw: ImageDraw.ImageDraw, loteria_nome: str,
                    numeros_str: str, area_box):
    """
    Layout:
      # | G | Mandante | × | Visitante | G | 1X2
    - G1/G2 vêm dos números colados aos nomes (prefixo/sufixo) ou dos campos g1/g2 (JSON)
    - Destaque vencedor (G + time); empate destaca o 'X'
    """
    x0, y0, x1, y1 = area_box
    jogos = _parse_loteca(numeros_str)

    col_w = [0.07, 0.06, 0.36, 0.04, 0.36, 0.06, 0.11]
    xs = [x0]
    for p in col_w:
        xs.append(xs[-1] + (x1 - x0) * p)

    header_h = 60
    row_h = (y1 - y0 - header_h) / 14

    # cabeçalho
    draw.rounded_rectangle((x0, y0, x1, y0 + header_h), radius=16, fill=(28, 34, 62))
    f_head = FONT_SANS(26, bold=True)
    def _center(a, b): return a + (b - a) / 2
    headers = ["#", "G", "Mandante", "×", "Visitante", "G", "1X2"]
    for i, htxt in enumerate(headers):
        draw.text((_center(xs[i], xs[i+1]), y0 + header_h/2 - 1), htxt,
                  font=f_head, fill=TEXT_LIGHT, anchor="mm")

    f_idx   = FONT_SANS(24, bold=True)
    f_team  = FONT_SANS(24, bold=True)
    f_goals = FONT_SANS(26, bold=True)
    f_res   = FONT_SANS(24, bold=True)

    for i in range(14):
        top = y0 + header_h + i * row_h
        bot = top + row_h - 4
        if i % 2 == 0:
            draw.rounded_rectangle((x0, top, x1, bot), radius=10, fill=(26, 32, 58))

        j = jogos[i]
        idx  = j["idx"]
        mand = j["mandante"]; vist = j["visitante"]
        g1   = j["g1"];       g2   = j["g2"]
        res  = (j["resultado"] or "").upper()

        # destaque
        if res == "1":
            draw.rounded_rectangle((xs[1]+6, top+6, xs[2]-6, bot-6), radius=10, fill=HIGHLIGHT)
            draw.rounded_rectangle((xs[2]+6, top+6, xs[3]-6, bot-6), radius=10, fill=HIGHLIGHT)
        elif res == "2":
            draw.rounded_rectangle((xs[4]+6, top+6, xs[5]-6, bot-6), radius=10, fill=HIGHLIGHT)
            draw.rounded_rectangle((xs[5]+6, top+6, xs[6]-6, bot-6), radius=10, fill=HIGHLIGHT)
        elif res == "X":
            draw.rounded_rectangle((xs[6]+6, top+6, xs[7]-6, bot-6), radius=10, fill=HIGHLIGHT)

        # render
        draw.text((_center(xs[0], xs[1]), (top+bot)/2), f"{idx:02d}", font=f_idx,  fill=TEXT_LIGHT, anchor="mm")
        draw.text((_center(xs[1], xs[2]), (top+bot)/2), "-" if g1 is None else str(g1),
                  font=f_goals, fill=(255,255,255) if res=="1" else (230,232,240), anchor="mm")
        draw.text((_center(xs[2], xs[3]), (top+bot)/2), mand or "-",
                  font=f_team,  fill=(255,255,255) if res=="1" else (230,232,240), anchor="mm")
        draw.text((_center(xs[3], xs[4]), (top+bot)/2), "×", font=f_team, fill=(200,200,215), anchor="mm")
        draw.text((_center(xs[4], xs[5]), (top+bot)/2), vist or "-",
                  font=f_team,  fill=(255,255,255) if res=="2" else (230,232,240), anchor="mm")
        draw.text((_center(xs[5], xs[6]), (top+bot)/2), "-" if g2 is None else str(g2),
                  font=f_goals, fill=(255,255,255) if res=="2" else (230,232,240), anchor="mm")
        draw.text((_center(xs[6], xs[7]), (top+bot)/2), (res or "-"),
                  font=f_res,   fill=(255,255,255) if res in ("1","2","X") else (230,232,240), anchor="mm")

# ==========================
# CTA / MARCA
# ==========================

def desenhar_cta(draw: ImageDraw.ImageDraw, url: str = ""):
    btn_w, btn_h = 760, 96
    bx = (W - btn_w) // 2
    by = H - 260
    draw.rounded_rectangle((bx, by, bx + btn_w, by + btn_h),
                           radius=28, fill=(255, 215, 0), outline=(0, 0, 0), width=2)
    txt = "VER RESULTADO COMPLETO"
    font_btn = FONT_SANS(44, bold=True)
    tw = draw.textlength(txt, font=font_btn)
    draw.text((W / 2 - tw / 2, by + (btn_h - 48) / 2),
              txt, font=font_btn, fill=(0, 0, 0))
    if url:
        url_clean = url.replace("https://", "").replace("http://", "")
        font_url = FONT_SANS(32)
        tw = draw.textlength(url_clean, font=font_url)
        draw.text((W / 2 - tw / 2, by + btn_h + 18),
                  url_clean, font=font_url, fill=(245, 245, 245))

def desenhar_marca(draw: ImageDraw.ImageDraw):
    font_marca = FONT_SANS(30, bold=True)
    tw = draw.textlength(BRAND_TEXT, font=font_marca)
    draw.text((W / 2 - tw / 2, H - 72),
              BRAND_TEXT, font=font_marca, fill=(255, 255, 255, 220))

# ==========================
# TÍTULOS
# ==========================

def desenhar_titulo(draw: ImageDraw.ImageDraw, loteria: str,
                    concurso: str, data_br: str):
    loteria_txt = (loteria or "").strip() or "Loteria"
    font_title = FONT_SERIF(88)
    draw.text((M, M), loteria_txt, font=font_title, fill=(255, 255, 255))

    font_sub = FONT_SANS(40, bold=True)
    if concurso:
        draw.text((M, M + 90), f"Concurso {concurso}", font=font_sub, fill=(230, 230, 230))

    if data_br:
        font_date = FONT_SANS(34)
        draw.text((M, M + 90 + 48), data_br, font=font_date, fill=(220, 220, 220))

# ==========================
# PRINCIPAL
# ==========================

def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url=""):
    loteria   = str(loteria or "").strip()
    concurso  = str(concurso or "").strip()
    data_br   = str(data_br or "").strip()
    numeros_s = str(numeros_str or "").strip()
    url       = str(url or "").strip()

    img = criar_fundo(loteria)
    draw = ImageDraw.Draw(img)

    desenhar_titulo(draw, loteria, concurso, data_br)
    desenhar_logo(img, loteria)

    area_top = M + 180
    area_bottom = H - 320
    area_box = (M, area_top, W - M, area_bottom)

    if "loteca" in loteria.lower():
        desenhar_loteca(draw, loteria, numeros_s, area_box)
    else:
        desenhar_bolinhas(draw, loteria, numeros_s, area_box)

    if SHOW_CTA:
        desenhar_cta(draw, url=url)

    # SEMPRE escrever a marca no rodapé
    desenhar_marca(draw)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf