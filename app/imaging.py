# app/imaging.py — Portal SimonSports
# Rev: 2025-11-18e — Layout “bolinhas” + LOTECA (1X2) + rótulos especiais
# - Mantém visual aprovado (gradiente, logo, títulos, CTA)
# - Dupla Sena: rótulos "1º SORTEIO", "2º SORTEIO" acima de cada linha
# - Timemania / Dia de Sorte: rótulo "NÚMEROS" acima + linha extra abaixo (Time/Mês)
# - Mais Milionária: bloco "NÚMEROS" + bloco "TREVOS DA SORTE"
# - Loteca: tabela 14 linhas (# | Mandante × Visitante | 1X2), destaque #38761d

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import os
import re
import math

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
    "loteca":       (56, 118, 29),   # #38761d approx
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
# PARSE DE NÚMEROS (geral)
# ==========================

def parse_numeros(loteria_nome: str, numeros_str: str):
    """
    Retorna (lista_de_listas, extra_text).
    Cada sublista = uma linha de bolinhas.
    Suporta:
    - Lotofácil com 1 ou 2 sorteios (via "|", todos os números entram)
    - Dupla Sena com 1 ou mais sorteios (blocos de 6 por linha)
    - Timemania / Dia de Sorte: texto extra (Time/Mês) é retornado como 'extra'
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

    nome = (loteria_nome or "").lower()

    if "lotofacil" in nome:
        # Lotofácil: exibe TODOS os números em blocos de 5
        rows = [nums[i:i+5] for i in range(0, n, 5)]

    elif "lotomania" in nome:
        rows = [nums[i:i+5] for i in range(0, min(20, n), 5)]

    elif "timemania" in nome:
        # 7 números + time -> extra já foi capturado (Time do Coração)
        if n <= 7:
            rows = [nums]
        else:
            rows = [nums[:7], nums[7:]]

    elif "dupla" in nome:
        # Dupla Sena: TODOS os números em blocos de 6 (n sorteios)
        rows = [nums[i:i+6] for i in range(0, n, 6)]

    else:
        # regra geral: máx 8 por linha, 1–3 linhas
        if n <= 8:
            rows = [nums]
        elif n <= 16:
            rows = [nums[:math.ceil(n/2)], nums[math.ceil(n/2):]]
        else:
            terc = math.ceil(n / 3)
            rows = [nums[:terc], nums[terc:2*terc], nums[2*terc:]]

    rows = [r for r in rows if r]
    return rows, extra

# ==========================
# MAIS MILIONÁRIA — parser (números + trevos)
# ==========================

def parse_mais_milionaria(numeros_str: str):
    """
    Separa numeros principais (1–50) e Trevos da Sorte (1–6).
    Aceita formatos:
      - "01,02,03,04,05,06 | Trevos: 3,5"
      - "01 02 03 04 05 06 - trevos 3 5"
      - "01,02,03,04,05,06, 3,5"  (fallback: últimos 2 tokens 1..6 viram trevos)
    Retorna: (main:list[str], trevos:list[str])
    """
    s = (numeros_str or "").strip()

    # Procura explicitamente por "trevos"
    m = re.search(r"trevos?(?:\s+da\s+sorte)?\s*[:\-]?\s*(.+)$", s, flags=re.I)
    trevos_part = None
    if m:
        trevos_part = m.group(1)
        s_main = s[:m.start()].strip(",; |-")
    else:
        # fallback: se os 2 últimos tokens estiverem entre 1..6, assume que são trevos
        toks = [t.strip() for t in re.split(r"[,\s|;]+", s) if t.strip()]
        s_main = ",".join(toks)
        if len(toks) >= 8 and all(re.fullmatch(r"\d{1,2}", t) for t in toks[-2:]) \
           and all(1 <= int(t) <= 6 for t in toks[-2:]):
            trevos_part = ",".join(toks[-2:])
            s_main = ",".join(toks[:-2])

    # Números principais
    main = [p.zfill(2) for p in re.split(r"[,\s|;]+", s_main) if re.fullmatch(r"\d{1,2}", p)]
    main = main[:12]  # segurança; normalmente são 6

    # Trevos
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
# DESENHO DAS BOLINHAS (geral + especiais)
# ==========================

def desenhar_bolinhas(draw: ImageDraw.ImageDraw, loteria_nome: str,
                      numeros_str: str, area_box):
    """
    area_box = (x0,y0,x1,y1) onde a grade deve caber.

    Regras especiais:
      - Dupla Sena: rótulos '1º SORTEIO', '2º SORTEIO' acima de cada linha.
      - Timemania: rótulo 'NÚMEROS' acima; abaixo: 'TIME DO CORAÇÃO: <extra>'.
      - Dia de Sorte: rótulo 'NÚMEROS' acima; abaixo: 'MÊS DA SORTE: <extra>'.
      - Mais Milionária: bloco 'NÚMEROS' e, abaixo, bloco 'TREVOS DA SORTE'.
    """
    x0, y0, x1, y1 = area_box
    largura = x1 - x0
    altura  = y1 - y0

    nome_lc = (loteria_nome or "").lower()
    is_dupla = "dupla" in nome_lc
    is_time  = "timemania" in nome_lc
    is_dias  = ("dia-de-sorte" in nome_lc) or ("dia de sorte" in nome_lc)
    is_mm    = ("milion" in nome_lc)  # Mais Milionária

    # ======== MAIS MILIONÁRIA (números + trevos) ========
    if is_mm:
        nums, trevos = parse_mais_milionaria(numeros_str)
        if not nums:
            return

        # Layout: rótulo 'NÚMEROS' + linha de números; abaixo rótulo 'TREVOS DA SORTE' + linha menor
        max_cols = max(1, len(nums))
        r = 62 if max_cols <= 7 else (54 if max_cols <= 10 else 46)
        gap_x = 28 if r == 62 else (22 if r == 54 else 20)

        r_trevo = int(r * 0.80)
        gap_trevo_x = gap_x

        font_num   = FONT_SANS(46, bold=True)
        font_label = FONT_SANS(30, bold=True)

        label_h = 40
        gap_between_blocks = 40

        # Alturas dos blocos
        h_nums   = label_h + 2*r
        h_trevos = (label_h + 2*r_trevo) if trevos else 0

        total_h = h_nums + (gap_between_blocks if trevos else 0) + h_trevos
        start_y = y0 + max(0, (altura - total_h) // 2)

        # ---- Bloco NÚMEROS ----
        txt = "NÚMEROS"
        tw = draw.textlength(txt, font=font_label)
        draw.text(((x0+x1)/2 - tw/2, start_y), txt, font=font_label, fill=(245,245,245))

        cy = start_y + label_h + r
        cols = len(nums)
        total_w_row = cols * (2*r + gap_x) - gap_x
        start_x = x0 + (largura - total_w_row) // 2
        for cidx, token in enumerate(nums):
            cx = start_x + cidx * (2*r + gap_x) + r
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255,255,255))
            if token:
                txtn = str(token)
                tn = draw.textlength(txtn, font=font_num)
                bbox = font_num.getbbox(txtn)
                th = bbox[3] - bbox[1]
                draw.text((cx - tn/2, cy - th/2 - 2), txtn, font=font_num, fill=(20,20,20))

        # ---- Bloco TREVOS DA SORTE ----
        if trevos:
            base_y = cy + r + gap_between_blocks
            txt = "TREVOS DA SORTE"
            tw = draw.textlength(txt, font=font_label)
            draw.text(((x0+x1)/2 - tw/2, base_y), txt, font=font_label, fill=(245,245,245))

            cy2 = base_y + label_h + r_trevo
            cols = len(trevos)
            total_w_row = cols * (2*r_trevo + gap_trevo_x) - gap_trevo_x
            start_x = x0 + (largura - total_w_row) // 2
            trevo_color = (56, 118, 29)  # verde do projeto
            font_trevo  = FONT_SANS(40, bold=True)
            for cidx, token in enumerate(trevos):
                cx = start_x + cidx * (2*r_trevo + gap_trevo_x) + r_trevo
                draw.ellipse((cx - r_trevo, cy2 - r_trevo, cx + r_trevo, cy2 + r_trevo), fill=trevo_color)
                if token:
                    t = str(token)
                    tn = draw.textlength(t, font=font_trevo)
                    bbox = font_trevo.getbbox(t)
                    th = bbox[3] - bbox[1]
                    draw.text((cx - tn/2, cy2 - th/2 - 2), t, font=font_trevo, fill=(255,255,255))
        return

    # ======== Demais loterias (usa parse_numeros) ========
    rows, extra = parse_numeros(loteria_nome, numeros_str)
    if not rows:
        return

    labels = []
    if is_dupla and len(rows) > 1:
        labels = [f"{i+1}º SORTEIO" for i in range(len(rows))]
    elif is_time or is_dias:
        labels = ["NÚMEROS"]  # um rótulo único acima

    qtd_linhas = len(rows)
    max_cols   = max(len(r) for r in rows)

    if max_cols <= 5:
        r = 62; gap_x = 28
    elif max_cols <= 8:
        r = 54; gap_x = 22
    else:
        r = 46; gap_x = 20

    gap_y   = 0 if qtd_linhas == 1 else (40 if qtd_linhas == 2 else 30)
    label_h = 40 if labels else 0

    line_height = label_h + 2*r + gap_y
    total_h     = qtd_linhas * line_height - gap_y
    start_y     = y0 + max(0, (altura - total_h) // 2)

    circle_color = (255, 255, 255)
    text_color   = (20, 20, 20)
    font_num     = FONT_SANS(46, bold=True)
    font_label   = FONT_SANS(30, bold=True)
    cx_center    = (x0 + x1) / 2

    for ridx, row in enumerate(rows):
        row_top = start_y + ridx * line_height
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
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=circle_color)
            if token:
                txt = str(token)
                tw = draw.textlength(txt, font=font_num)
                bbox = font_num.getbbox(txt)
                th = bbox[3] - bbox[1]
                draw.text((cx - tw/2, cy - th/2 - 2), txt, font=font_num, fill=text_color)

    # Linha extra (abaixo) para Timemania e Dia de Sorte
    if extra:
        font_extra = FONT_SANS(38, bold=True)
        label = "TIME DO CORAÇÃO: " if is_time else ("MÊS DA SORTE: " if is_dias else "")
        txt = (label + extra.strip()) if label else extra.strip()
        tw  = draw.textlength(txt, font=font_extra)
        draw.text(((x0 + x1) / 2 - tw / 2, y1 + 10), txt, font=font_extra, fill=(255, 255, 255))

# ==========================
# LOTECA — PARSER & TABELA
# ==========================

# Ex.: "AMÉRICA/MG x FERROVIÁRIA/SP 2-1" ou "BAHIA x NÁUTICO 1" ou "CRB x AVAÍ X"
_RE_LOTECA = re.compile(
    r"^\s*(?:\d{1,2}[\.\)]\s*)?"
    r"(?P<mand>.+?)\s+[xX]\s+(?P<visit>.+?)"
    r"(?:\s+(?P<p1>\d+)\s*[-xX]\s*(?P<p2>\d+)|\s+(?P<rx>[12X]))?\s*$",
    re.UNICODE
)

def _parse_loteca(numeros_str: str):
    """
    Retorna lista de 14 dicts:
      {idx, mandante, visitante, resultado}  # resultado em {'1','X','2'} se possível
    Aceita JSON (lista de jogos) OU texto com '|' ou quebra de linha.
    """
    jogos = []
    s = (numeros_str or "").strip()

    # Tenta JSON primeiro (sem eval perigoso: apenas json-like simples)
    if s.startswith("[") or s.startswith("{"):
        try:
            import json
            data = json.loads(s)
            if isinstance(data, dict) and "jogos" in data:
                data = data["jogos"]
            if isinstance(data, list):
                for i, it in enumerate(data, 1):
                    mand = str(it.get("mandante", "")).strip()
                    visit = str(it.get("visitante", "")).strip()
                    res = str(it.get("resultado", "")).strip().upper()
                    pl = str(it.get("placar", "")).strip()
                    if not res and "-" in pl:
                        try:
                            a, b = [int(x) for x in pl.split("-", 1)]
                            res = "1" if a > b else ("2" if b > a else "X")
                        except:
                            pass
                    jogos.append({"idx": i, "mandante": mand, "visitante": visit, "resultado": res})
        except Exception:
            pass

    if not jogos:
        linhas = re.split(r"\n|\|", s)
        for i, ln in enumerate(linhas, 1):
            t = ln.strip()
            if not t:
                continue
            m = _RE_LOTECA.match(t)
            if not m:
                continue
            mand = m.group("mand").strip()
            visit = m.group("visit").strip()
            res = ""
            if m.group("rx"):
                res = m.group("rx").upper()
            elif m.group("p1") and m.group("p2"):
                try:
                    a, b = int(m.group("p1")), int(m.group("p2"))
                    res = "1" if a > b else ("2" if b > a else "X")
                except:
                    res = ""
            jogos.append({"idx": i, "mandante": mand, "visitante": visit, "resultado": res})

    # normaliza para 14
    jogos = jogos[:14]
    while len(jogos) < 14:
        jogos.append({"idx": len(jogos)+1, "mandante": "", "visitante": "", "resultado": ""})
    return jogos

def desenhar_loteca(draw: ImageDraw.ImageDraw, loteria_nome: str,
                    numeros_str: str, area_box):
    """
    Tabela 14 linhas: # | Mandante × Visitante | 1X2
    Destaque vencedor/empate com cor da Loteca (#38761d) e texto branco.
    """
    x0, y0, x1, y1 = area_box
    lot_color = cor_loteria("loteca")
    jogos = _parse_loteca(numeros_str)

    # colunas:  # | Mandante | × | Visitante | 1X2
    col_w = [0.10, 0.37, 0.06, 0.37, 0.10]
    xs = [x0]
    for p in col_w[:-1]:
        xs.append(xs[-1] + (x1 - x0) * p)
    xs.append(x1)

    header_h = 54
    row_h = (y1 - y0 - header_h) / 14

    # header
    draw.rounded_rectangle((x0, y0, x1, y0 + header_h), radius=16, fill=(28, 34, 62))
    f_head = FONT_SANS(24, bold=True)
    def _center(cx0, cx1): return cx0 + (cx1 - cx0) / 2
    draw.text((_center(xs[0], xs[1]), y0 + header_h/2 - 1), "#", font=f_head, fill=(235,235,245), anchor="mm")
    draw.text((_center(xs[1], xs[2]), y0 + header_h/2 - 1), "Mandante", font=f_head, fill=(235,235,245), anchor="mm")
    draw.text((_center(xs[2], xs[3]), y0 + header_h/2 - 1), "×", font=f_head, fill=(200,200,215), anchor="mm")
    draw.text((_center(xs[3], xs[4]), y0 + header_h/2 - 1), "Visitante", font=f_head, fill=(235,235,245), anchor="mm")
    draw.text((_center(xs[4], xs[5]), y0 + header_h/2 - 1), "1X2", font=f_head, fill=(235,235,245), anchor="mm")

    f_idx = FONT_SANS(22, bold=True)
    f_team = FONT_SANS(24, bold=True)
    f_res  = FONT_SANS(22, bold=True)

    # linhas
    for i in range(14):
        top = y0 + header_h + i * row_h
        bot = top + row_h - 4

        # listras suaves
        if i % 2 == 0:
            draw.rounded_rectangle((x0, top, x1, bot), radius=10, fill=(26, 32, 58))

        j = jogos[i]
        idx = j["idx"]
        mand = j["mandante"]
        vist = j["visitante"]
        res = (j["resultado"] or "").upper()

        # destaque
        if res == "1":
            draw.rounded_rectangle((xs[1]+6, top+6, xs[2]-6, bot-6), radius=10, fill=lot_color)
        elif res == "2":
            draw.rounded_rectangle((xs[3]+6, top+6, xs[4]-6, bot-6), radius=10, fill=lot_color)
        elif res == "X":
            draw.rounded_rectangle((xs[4]+6, top+6, xs[5]-6, bot-6), radius=10, fill=lot_color)

        # textos
        draw.text((_center(xs[0], xs[1]), (top+bot)/2), f"{idx:02d}", font=f_idx, fill=(235,235,245), anchor="mm")
        draw.text((_center(xs[1], xs[2]), (top+bot)/2),
                  mand or "-", font=f_team, fill=(255,255,255) if res=="1" else (230,232,240), anchor="mm")
        draw.text((_center(xs[2], xs[3]), (top+bot)/2), "×", font=f_team, fill=(200,200,215), anchor="mm")
        draw.text((_center(xs[3], xs[4]), (top+bot)/2),
                  vist or "-", font=f_team, fill=(255,255,255) if res=="2" else (230,232,240), anchor="mm")
        draw.text((_center(xs[4], xs[5]), (top+bot)/2),
                  (res or "-"), font=f_res, fill=(255,255,255) if res=="X" else (230,232,240), anchor="mm")

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
            url_clean,
            font=font_url,
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
    loteria_txt = (loteria or "").strip() or "Loteria"

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
    sub = f"Concurso {concurso}" if concurso else ""
    if sub:
        draw.text((M, M + 90), sub, font=font_sub, fill=(230, 230, 230))

    # terceira linha: data
    if data_br:
        font_date = FONT_SANS(34, bold=False)
        draw.text((M, M + 90 + 48), data_br, font=font_date, fill=(220, 220, 220))

# ==========================
# FUNÇÃO PRINCIPAL
# ==========================

def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url=""):
    """
    Gera imagem em BytesIO (PNG) no layout aprovado:
    - fundo na cor da loteria (gradiente)
    - logo no topo direito
    - título + concurso + data
    - grade de bolinhas com números (todas as loterias)
    - EXCEÇÃO: Loteca → tabela 14 linhas 1X2
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

    # área central
    area_top = M + 180
    area_bottom = H - 320
    area_box = (M, area_top, W - M, area_bottom)

    if "loteca" in loteria.lower():
        # Tabela 14 linhas (1X2)
        desenhar_loteca(draw, loteria, numeros_str, area_box)
    else:
        # Bolinhas (geral: Mega, Quina, Lotofácil, Dupla, Timemania, Dia de Sorte, Mais Milionária, etc.)
        desenhar_bolinhas(draw, loteria, numeros_str, area_box)

    # CTA & marca
    desenhar_cta(draw, url=url)

    # saída
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf