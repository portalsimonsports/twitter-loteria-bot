# app/imaging.py — Portal SimonSports
# Rev: 2025-11-21r — REVERT SAFE (Loteca sem 1X2, gols dos dois lados, vencedor com barra verde)

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io, os, re, math

W, H = 1080, 1080
M = 80
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
LOGOS_DIR  = os.path.join(ASSETS_DIR, "logos")
SHOW_CTA = False
BRAND_TEXT = "Portal SimonSports"

def _try_fonts(cands, size):
    for p in cands:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def FONT_SANS(size, bold=False):
    return _try_fonts(
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"] if bold else
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"], size)

def FONT_SERIF(size):
    return _try_fonts(
        ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"], size)

def hx(h): h=h.lstrip('#'); return (int(h[0:2],16),int(h[2:4],16),int(h[4:6],16))

CORES_LOTERIAS = {
    "mega-sena": hx("#009645"), "lotofacil": hx("#8c1a8a"), "lotofácil": hx("#8c1a8a"),
    "quina": hx("#003087"), "lotomania": hx("#f58c1f"), "timemania": hx("#ffdd00"),
    "dupla-sena": hx("#c41c3a"), "dupla sena": hx("#c41c3a"), "federal": hx("#00a0b0"),
    "loteca": hx("#ed1c24"), "dia-de-sorte": hx("#ffd800"), "dia de sorte": hx("#ffd800"),
    "super-sete": hx("#8cd13f"), "super sete": hx("#8cd13f"),
    "mais-milionaria": hx("#2b1166"), "mais milionaria": hx("#2b1166"),
    "+milionaria": hx("#2b1166"), "+milionária": hx("#2b1166"),
}
HIGHLIGHT = (56,118,29)  # #38761d
TEXT_LIGHT = (235,235,245)
DOURADO_TREVO = (255,211,0)

def _slug(s: str) -> str:
    s=(s or "").lower(); s=s.replace("ç","c")
    s=re.sub(r"[áàâãä]","a",s); s=re.sub(r"[éèêë]","e",s); s=re.sub(r"[íìîï]","i",s)
    s=re.sub(r"[óòôõö]","o",s); s=re.sub(r"[úùûü]","u",s)
    s=re.sub(r"[^a-z0-9\- ]+","",s); s=re.sub(r"\s+","-",s).strip("-"); return s

def cor_loteria(nome:str):
    if (nome or "").lower() in CORES_LOTERIAS: return CORES_LOTERIAS[nome.lower()]
    return CORES_LOTERIAS.get(_slug(nome or "loteria"), (30,30,30))

def _gradient_vertical(w,h,top,bottom):
    base=Image.new("RGB",(w,h),top); topimg=Image.new("RGB",(w,h),bottom)
    mask=Image.linear_gradient("L").resize((1,h)).resize((w,h))
    return Image.composite(topimg, base, mask)

def _vinheta(img, strength=220, blur=180):
    w,h=img.size; v=Image.new("L",(w,h),0); d=ImageDraw.Draw(v)
    d.ellipse([-200,-80,w+200,h+280], fill=strength); v=v.filter(ImageFilter.GaussianBlur(blur))
    return Image.composite(img, Image.new("RGB",(w,h),(0,0,0)), v)

def criar_fundo(loteria_nome:str):
    base=cor_loteria(loteria_nome)
    top=tuple(min(255,int(c*1.3)) for c in base)
    bottom=tuple(int(c*0.8) for c in base)
    return _vinheta(_gradient_vertical(W,H,top,bottom))

def load_logo(loteria_nome:str):
    slug=_slug(loteria_nome)
    for ext in ("png","jpg","jpeg"):
        p=os.path.join(LOGOS_DIR,f"{slug}.{ext}")
        if os.path.exists(p):
            try: return Image.open(p).convert("RGBA")
            except Exception: pass
    return None

def desenhar_logo(canvas:Image.Image, loteria_nome:str):
    logo=load_logo(loteria_nome); if not logo: return
    max_w,max_h=210,120; logo.thumbnail((max_w,max_h), Image.LANCZOS)
    x=W-M-logo.width; y=M; canvas.paste(logo,(x,y),logo)

def parse_mais_milionaria(numeros_str:str):
    s=(numeros_str or "").strip()
    if "+" in s:
        left,right=s.split("+",1)
        main=[t for t in re.split(r"[,\s;]+",left.strip()) if t]
        trev=[t for t in re.split(r"[,\s;]+",right.strip()) if t]
        mains=[]; trevos=[]
        for t in main:
            if re.fullmatch(r"\d{1,2}",t):
                v=int(t); 
                if 1<=v<=50: mains.append(f"{v:02d}")
            if len(mains)==6: break
        for t in trev:
            if re.fullmatch(r"\d{1,2}",t):
                v=int(t); 
                if 1<=v<=6: trevos.append(str(v))
            if len(trevos)==2: break
        return mains, trevos
    toks=[t.strip() for t in re.split(r"[,\s|;]+",s) if t.strip()]
    mains, trevos=[], []
    if len(toks)>=8 and all(re.fullmatch(r"\d{1,2}",t) for t in toks[-2:]):
        if all(1<=int(t)<=6 for t in toks[-2:]): trevos=[str(int(toks[-2])), str(int(toks[-1]))]; toks=toks[:-2]
    for t in toks:
        if re.fullmatch(r"\d{1,2}",t):
            v=int(t); 
            if 1<=v<=50: mains.append(f"{v:02d}")
        if len(mains)==6: break
    return mains, trevos

def parse_numeros(loteria_nome:str, numeros_str:str):
    s=(numeros_str or "").strip()
    extra=None
    m=re.search(r"(?:-|;)\s*([A-Za-zÀ-ÿ0-9/ \.\-]+)$", s)
    if m: extra=m.group(1).strip(); s=s[:m.start()].strip(",; -")
    s=s.replace("–","-"); s=re.sub(r"[;| ]+",",",s)
    parts=[p.strip() for p in s.split(",") if p.strip()]
    nums=[p.zfill(2) if re.fullmatch(r"\d+",p) else p for p in parts]
    n=len(nums); rows=[]; nome=(loteria_nome or "").lower()
    if "lotofacil" in nome: rows=[nums[i:i+5] for i in range(0,n,5)]
    elif "lotomania" in nome: rows=[nums[i:i+5] for i in range(0,min(20,n),5)]
    elif "timemania" in nome: rows=[nums] if n<=7 else [nums[:7], nums[7:]]
    elif "dupla" in nome: rows=[nums[i:i+6] for i in range(0,n,6)]
    else:
        if n<=8: rows=[nums]
        elif n<=16: mid=math.ceil(n/2); rows=[nums[:mid], nums[mid:]]
        else: terc=math.ceil(n/3); rows=[nums[:terc], nums[terc:2*terc], nums[2*terc:]]
    return [r for r in rows if r], extra

_SPLIT_X = re.compile(r"\s+[xX×]\s+")
def _strip_index_prefix(s: str) -> str: return re.sub(r"^\s*\d{1,2}[\.\)]?\s*", "", s or "")
def _extract_goals_and_name(token: str):
    s=(token or "").strip()
    s=re.sub(r"\s*\((?:Dom|Seg|Ter|Qua|Qui|Sex|Sáb|Sab|[A-Za-z\. ]+)\)\s*$","",s,flags=re.I)
    m=re.match(r"^\s*(\d+)\s+(.+)$",s); 
    if m: return m.group(2).strip(" -"), int(m.group(1))
    m=re.match(r"^(.+?)\s+(\d+)\s*$",s)
    if m: return m.group(1).strip(" -"), int(m.group(2))
    return s.strip(" -"), None
def _clean_team_name(s: str):
    s=re.sub(r"\s*\([^)]+\)\s*$","",s or ""); s=re.sub(r"^\s*\d+\s+","",s); s=re.sub(r"\s+\d+\s*$","",s); return s.strip(" -")

def _parse_loteca(numeros_str: str):
    jogos=[]; s=(numeros_str or "").strip()
    if s.startswith("[") or s.startswith("{"):
        try:
            data=json.loads(s)
            if isinstance(data,dict) and "jogos" in data: data=data["jogos"]
            if isinstance(data,list):
                for i,it in enumerate(data,1):
                    mand,_g1=_extract_goals_and_name(str(it.get("mandante","")).strip())
                    vist,_g2=_extract_goals_and_name(str(it.get("visitante","")).strip())
                    g1=it.get("g1",_g1); g2=it.get("g2",_g2)
                    res=str(it.get("resultado","")).upper().strip()
                    if g1 is not None and g2 is not None:
                        try: a,b=int(g1),int(g2); res="1" if a>b else ("2" if b>a else "X")
                        except: pass
                    jogos.append({"idx":i,"mandante":_clean_team_name(mand),"visitante":_clean_team_name(vist),
                                 "g1":None if g1 is None else int(g1),"g2":None if g2 is None else int(g2),"resultado":res})
        except Exception: pass
    if not jogos:
        linhas=re.split(r"\n|\|", s)
        for i,ln in enumerate(linhas,1):
            t=_strip_index_prefix(ln.strip())
            if not t: continue
            parts=_SPLIT_X.split(t)
            if len(parts)!=2: continue
            left,right=parts[0],parts[1]
            mand,g1=_extract_goals_and_name(left)
            vist,g2=_extract_goals_and_name(right)
            res=""
            if (g1 is not None) and (g2 is not None):
                try: a,b=int(g1),int(g2); res="1" if a>b else ("2" if b>a else "X")
                except: pass
            jogos.append({"idx":i,"mandante":_clean_team_name(mand),"visitante":_clean_team_name(vist),
                          "g1":None if g1 is None else int(g1),"g2":None if g2 is None else int(g2),"resultado":res})
    jogos=jogos[:14]
    while len(jogos)<14: jogos.append({"idx":len(jogos)+1,"mandante":"","visitante":"","g1":None,"g2":None,"resultado":""})
    return jogos

def desenhar_loteca(draw: ImageDraw.ImageDraw, loteria_nome: str, numeros_str: str, area_box):
    x0,y0,x1,y1 = area_box
    jogos=_parse_loteca(numeros_str)

    # Sem coluna 1X2 (apenas: # | G | Mandante | × | Visitante | G)
    col_w = [0.07, 0.06, 0.41, 0.04, 0.36, 0.06]  # soma 1.0
    xs=[x0]; 
    for p in col_w: xs.append(xs[-1] + (x1-x0)*p)

    header_h=60; row_h=(y1-y0-header_h)/14
    draw.rounded_rectangle((x0,y0,x1,y0+header_h), radius=16, fill=(28,34,62))
    f_head=FONT_SANS(26, bold=True)
    def _c(a,b): return a+(b-a)/2
    headers=["#","G","Mandante","×","Visitante","G"]
    for i,ht in enumerate(headers):
        draw.text((_c(xs[i],xs[i+1]), y0+header_h/2-1), ht, font=f_head, fill=TEXT_LIGHT, anchor="mm")

    f_idx=FONT_SANS(24, bold=True); f_team=FONT_SANS(24, bold=True)
    f_goals=FONT_SANS(26, bold=True)

    for i in range(14):
        top=y0+header_h+i*row_h; bot=top+row_h-4
        if i%2==0: draw.rounded_rectangle((x0,top,x1,bot), radius=10, fill=(26,32,58))
        j=jogos[i]; idx=j["idx"]; mand=j["mandante"]; vist=j["visitante"]; g1=j["g1"]; g2=j["g2"]; res=(j["resultado"] or "").upper()

        # Destaque vencedor
        if res=="1":
            draw.rounded_rectangle((xs[1]+6, top+6, xs[2]-6, bot-6), radius=10, fill=HIGHLIGHT)  # G mandante
            draw.rounded_rectangle((xs[2]+6, top+6, xs[3]-6, bot-6), radius=10, fill=HIGHLIGHT)  # nome mandante
        elif res=="2":
            draw.rounded_rectangle((xs[4]+6, top+6, xs[5]-6, bot-6), radius=10, fill=HIGHLIGHT)  # nome visitante
            draw.rounded_rectangle((xs[5]+6, top+6, xs[6]-6, bot-6), radius=10, fill=HIGHLIGHT)  # G visitante

        # Conteúdo
        draw.text((_c(xs[0],xs[1]), (top+bot)/2), f"{idx:02d}", font=f_idx,  fill=TEXT_LIGHT, anchor="mm")
        draw.text((_c(xs[1],xs[2]), (top+bot)/2), "-" if g1 is None else str(g1),
                  font=f_goals, fill=(255,255,255) if res=="1" else (230,232,240), anchor="mm")
        draw.text((_c(xs[2],xs[3]), (top+bot)/2), mand or "-", font=f_team,
                  fill=(255,255,255) if res=="1" else (230,232,240), anchor="mm")
        draw.text((_c(xs[3],xs[4]), (top+bot)/2), "×", font=f_team, fill=(200,200,215), anchor="mm")
        draw.text((_c(xs[4],xs[5]), (top+bot)/2), vist or "-", font=f_team,
                  fill=(255,255,255) if res=="2" else (230,232,240), anchor="mm")
        draw.text((_c(xs[5],xs[6]), (top+bot)/2), "-" if g2 is None else str(g2),
                  font=f_goals, fill=(255,255,255) if res=="2" else (230,232,240), anchor="mm")

def desenhar_bolinhas(draw: ImageDraw.ImageDraw, loteria_nome:str, numeros_str:str, area_box):
    x0,y0,x1,y1 = area_box
    nome_lc=(loteria_nome or "").lower()
    if "milion" in nome_lc:
        nums,trevos=parse_mais_milionaria(numeros_str)
        if not nums: return
        max_cols=max(1,len(nums))
        r = 62 if max_cols<=7 else (54 if max_cols<=10 else 46)
        gap_x=28 if r==62 else (22 if r==54 else 20)
        r_t=int(r*0.80); font_num=FONT_SANS(46, bold=True); font_label=FONT_SANS(30, bold=True)
        label_h=40; gap_between=40
        total_h=(label_h+2*r)+(gap_between if trevos else 0)+(label_h+2*r_t if trevos else 0)
        start_y=y0+max(0,(y1-y0-total_h)//2)
        txt="NÚMEROS"; tw=draw.textlength(txt,font=font_label)
        draw.text(((x0+x1)/2 - tw/2, start_y), txt, font=font_label, fill=(245,245,245))
        cy=start_y+label_h+r; cols=len(nums); total_w=cols*(2*r+gap_x)-gap_x; start_x=x0+(x1-x0-total_w)//2
        for i,tok in enumerate(nums):
            cx=start_x+i*(2*r+gap_x)+r
            draw.ellipse((cx-r,cy-r,cx+r,cy+r), fill=(255,255,255))
            t=str(tok); tn=draw.textlength(t,font=font_num); th=font_num.getbbox(t)[3]-font_num.getbbox(t)[1]
            draw.text((cx-tn/2, cy-th/2-2), t, font=font_num, fill=(20,20,20))
        if trevos:
            base_y=cy+r+gap_between; txt="TREVOS DA SORTE"; tw=draw.textlength(txt,font=font_label)
            draw.text(((x0+x1)/2 - tw/2, base_y), txt, font=font_label, fill=(245,245,245))
            cy2=base_y+label_h+r_t; cols=len(trevos); total_w=cols*(2*r_t+gap_x)-gap_x; start_x=x0+(x1-x0-total_w)//2
            font_t=FONT_SANS(40, bold=True)
            for i,tok in enumerate(trevos):
                cx=start_x+i*(2*r_t+gap_x)+r_t
                draw.ellipse((cx-r_t,cy2-r_t,cx+r_t,cy2+r_t), fill=DOURADO_TREVO)
                t=str(tok); tn=draw.textlength(t,font=font_t); th=font_t.getbbox(t)[3]-font_t.getbbox(t)[1]
                draw.text((cx-tn/2, cy2-th/2-2), t, font=font_t, fill=(60,60,60))
        return

    rows, extra = parse_numeros(loteria_nome, numeros_str)
    if not rows: return
    labels=[]; nome_lc=(loteria_nome or "").lower()
    if "dupla" in nome_lc and len(rows)>1: labels=[f"{i+1}º SORTEIO" for i in range(len(rows))]
    elif "timemania" in nome_lc or "dia-de-sorte" in nome_lc or "dia de sorte" in nome_lc: labels=["NÚMEROS"]

    qtd=len(rows); max_cols=max(len(r) for r in rows)
    if max_cols<=5: r, gap_x = 62,28
    elif max_cols<=8: r,gap_x=54,22
    else: r,gap_x=46,20
    gap_y=0 if qtd==1 else (40 if qtd==2 else 30); label_h=40 if labels else 0
    line_h=label_h+2*r+gap_y; total_h=qtd*line_h-gap_y; start_y=area_box[1]+max(0, (area_box[3]-area_box[1]-total_h)//2)
    font_num=FONT_SANS(46, bold=True); font_label=FONT_SANS(30, bold=True)
    for ridx,row in enumerate(rows):
        row_top=start_y+ridx*line_h
        if labels:
            txt=labels[ridx] if len(labels)>1 else labels[0]
            tw=draw.textlength(txt,font=font_label)
            draw.text(((area_box[0]+area_box[2])/2 - tw/2, row_top), txt, font=font_label, fill=(245,245,245))
        cy=row_top+label_h+r; cols=len(row); total_w=cols*(2*r+gap_x)-gap_x; start_x=area_box[0]+(area_box[2]-area_box[0]-total_w)//2
        for cidx,token in enumerate(row):
            cx=start_x+cidx*(2*r+gap_x)+r
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(255,255,255))
            if token:
                t=str(token); tw=draw.textlength(t,font=font_num); th=font_num.getbbox(t)[3]-font_num.getbbox(t)[1]
                draw.text((cx - tw/2, cy - th/2 - 2), t, font=font_num, fill=(20,20,20))

def desenhar_cta(draw: ImageDraw.ImageDraw, url: str = ""):
    btn_w,btn_h=760,96; bx=(W-btn_w)//2; by=H-260
    draw.rounded_rectangle((bx,by,bx+btn_w,by+btn_h), radius=28, fill=(255,215,0), outline=(0,0,0), width=2)
    txt="VER RESULTADO COMPLETO"; font_btn=FONT_SANS(44, bold=True); tw=draw.textlength(txt,font=font_btn)
    draw.text((W/2 - tw/2, by + (btn_h-48)/2), txt, font=font_btn, fill=(0,0,0))
    if url:
        url_clean=url.replace("https://","").replace("http://",""); font_url=FONT_SANS(32); tw=draw.textlength(url_clean,font=font_url)
        draw.text((W/2 - tw/2, by + btn_h + 18), url_clean, font=font_url, fill=(245,245,245))

def desenhar_marca(draw: ImageDraw.ImageDraw):
    font_marca=FONT_SANS(30, bold=True); tw=draw.textlength(BRAND_TEXT,font=font_marca)
    draw.text((W/2 - tw/2, H-72), BRAND_TEXT, font=font_marca, fill=(255,255,255,220))

def desenhar_titulo(draw: ImageDraw.ImageDraw, loteria:str, concurso:str, data_br:str):
    loteria_txt=(loteria or "").strip() or "Loteria"
    font_title=FONT_SERIF(88); draw.text((M,M), loteria_txt, font=font_title, fill=(255,255,255))
    font_sub=FONT_SANS(40, bold=True)
    if concurso: draw.text((M, M+90), f"Concurso {concurso}", font=font_sub, fill=(230,230,230))
    if data_br:  draw.text((M, M+90+48), data_br, font=FONT_SANS(34), fill=(220,220,220))

def gerar_imagem_loteria(loteria, concurso, data_br, numeros_str, url=""):
    loteria=str(loteria or "").strip(); concurso=str(concurso or "").strip()
    data_br=str(data_br or "").strip(); numeros_s=str(numeros_str or "").strip(); url=str(url or "").strip()
    img=criar_fundo(loteria); draw=ImageDraw.Draw(img)
    desenhar_titulo(draw, loteria, concurso, data_br); desenhar_logo(img, loteria)
    area_top=M+180; area_bottom=H-320; area_box=(M,area_top,W-M,area_bottom)
    if "loteca" in loteria.lower(): desenhar_loteca(draw, loteria, numeros_s, area_box)
    else: desenhar_bolinhas(draw, loteria, numeros_s, area_box)
    if SHOW_CTA: desenhar_cta(draw, url=url)
    desenhar_marca(draw)
    buf=io.BytesIO(); img.save(buf, format="PNG", optimize=True); buf.seek(0); return buf