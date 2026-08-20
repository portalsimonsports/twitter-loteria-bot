from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

import daily_queue_v19 as queue
from youtube_auth import get_access_token
from youtube_upload import upload_thumbnail

WIDTH = 1280
HEIGHT = 720
OUT_DIR = Path("output")


def _font(size: int, bold: bool = False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _fit(draw, text, max_width, start, minimum=18, bold=True):
    for size in range(start, minimum - 1, -2):
        f = _font(size, bold)
        if draw.textbbox((0, 0), text, font=f)[2] <= max_width:
            return f
    return _font(minimum, bold)


def _money_value(value: str) -> float:
    text = re.sub(r"[^0-9,.-]", "", str(value or ""))
    if not text:
        return 0.0
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return 0.0


def _money_text(value: str) -> str:
    amount = _money_value(value)
    if amount <= 0:
        return str(value or "").strip()
    return "R$ " + f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _largest(loterias: Sequence[Dict[str, str]], explicit: Dict[str, str] | None = None) -> Dict[str, str]:
    if explicit and _money_value(explicit.get("premio", "")) > 0:
        return {"loteria": str(explicit.get("loteria") or "").strip(), "premio": _money_text(explicit.get("premio", "")), "concurso": str(explicit.get("concurso") or "").strip()}
    best, best_value = {}, 0.0
    for item in loterias:
        amount = _money_value(item.get("premio", ""))
        if amount > best_value:
            best_value = amount
            best = {"loteria": str(item.get("loteria") or "").strip(), "premio": _money_text(item.get("premio", "")), "concurso": str(item.get("concurso") or "").strip()}
    return best


def _draw_approved(data: str, loterias: List[Dict[str, str]], *, prize_highlight=None, mode="alerta") -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), (5, 22, 39))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, WIDTH, 70), fill=(0, 105, 170))
    draw.rectangle((0, 650, WIDTH, 720), fill=(0, 42, 68))
    draw.text((34, 18), "PORTAL SIMONSPORTS", font=_font(26, True), fill="white")
    draw.text((1000, 20), "LOTERIAS CAIXA", font=_font(21, True), fill=(255, 205, 0))

    focus = _largest(loterias, prize_highlight)
    if not focus and loterias:
        focus = dict(loterias[0])

    focus_name = str(focus.get("loteria") or "LOTERIAS DE HOJE").upper()
    focus_contest = str(focus.get("concurso") or "")
    focus_prize = str(focus.get("premio") or "")

    draw.text((42, 102), focus_name, font=_fit(draw, focus_name, 760, 74, 40, True), fill="white")
    if focus_contest:
        draw.rounded_rectangle((44, 187, 350, 236), radius=14, fill=(0, 105, 170))
        draw.text((64, 198), f"CONCURSO {focus_contest}", font=_font(24, True), fill="white")

    main_label = "SORTEIO DE HOJE" if mode == "alerta" else "RESULTADO DE HOJE"
    draw.text((42, 263), main_label, font=_fit(draw, main_label, 720, 66, 36, True), fill=(255, 205, 0))

    if focus_prize:
        draw.text((42, 345), "MAIOR PRÊMIO DO DIA", font=_font(27, True), fill=(171, 225, 255))
        draw.rounded_rectangle((42, 383, 830, 480), radius=22, fill=(255, 205, 0))
        draw.text((70, 404), focus_prize, font=_fit(draw, focus_prize, 730, 54, 30, True), fill=(8, 27, 44))

    draw.rounded_rectangle((920, 104, 1235, 184), radius=20, fill=(255, 205, 0))
    df = _fit(draw, data, 265, 34, 24, True)
    box = draw.textbbox((0, 0), data, font=df)
    draw.text((1078 - (box[2] - box[0]) / 2, 127), data, font=df, fill=(8, 27, 44))

    others = []
    focus_key = focus_name.casefold()
    for item in loterias:
        name = str(item.get("loteria") or "").strip()
        if name and name.casefold() != focus_key:
            others.append(name.upper())
    if others:
        line = " + ".join(others[:5])
        draw.text((42, 533), line, font=_fit(draw, line, 1160, 31, 20, True), fill="white")

    footer = "INSCREVA-SE • ATIVE O SINO • RECEBA AS ATUALIZAÇÕES EM PRIMEIRA MÃO" if mode == "alerta" else "RESULTADOS OFICIAIS • CAIXA LOTERIAS • SIMONSPORTS"
    draw.text((WIDTH / 2, 684), footer, font=_fit(draw, footer, 1190, 25, 17, True), fill="white", anchor="mm")
    return img


def gerar_capa_live(data: str, targets: Sequence[Tuple[str, str, str]], *, prize_highlight: Dict[str, str] | None = None) -> str:
    loterias = [{"loteria": display, "concurso": contest, "premio": ""} for _key, display, contest in targets]
    image = _draw_approved(data, loterias, prize_highlight=prize_highlight, mode="alerta")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"thumbnail_live_{data.replace('/', '-')}.jpg"
    image.save(path, "JPEG", quality=94, optimize=True)
    return str(path)


def gerar_capa_diaria(data: str, loterias: List[Dict[str, str]], *, video_id: str = "", prize_highlight: Dict[str, str] | None = None) -> str:
    image = _draw_approved(data, loterias, prize_highlight=prize_highlight, mode="resultado")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"thumbnail_diaria_{data.replace('/', '-')}_{video_id or 'novo'}.jpg"
    image.save(path, "JPEG", quality=94, optimize=True)
    return str(path)


def _extract_video_id(text: str) -> str:
    m = re.search(r"youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})", str(text or ""))
    return m.group(1) if m else ""


def reparar_ultima_capa_publicada() -> int:
    cfg = queue.carregar_config(); client = queue._google_client(); cofre_cache, cofre_get = queue._load_cofre(client, cfg)
    ws = client.open_by_key(cfg.google_sheet_id).worksheet(cfg.sheet_tab); values = ws.get_all_values()
    if not values: return 0
    headers = list(values[0]); daily_idx = queue._find_col(headers, [os.getenv("PUBLICADO_YT_DIARIO_COL", queue.DAILY_COLUMN_DEFAULT)])
    if daily_idx is None: return 0
    video_id = ""
    for row in reversed(values[1:]):
        video_id = _extract_video_id(row[daily_idx] if daily_idx < len(row) else "")
        if video_id: break
    if not video_id: return 0
    loterias=[]; data=""; seen=set()
    for row in values[1:]:
        marker=row[daily_idx] if daily_idx < len(row) else ""
        if _extract_video_id(marker)!=video_id: continue
        try: item=queue._row_data(row,headers)
        except Exception: continue
        nome=str(item.get("loteria") or "").strip(); concurso=str(item.get("concurso") or "").strip(); premio=str(item.get("premio") or item.get("premiacao") or item.get("prêmio") or "").strip()
        key=(nome.casefold(),concurso)
        if not nome or key in seen: continue
        seen.add(key); loterias.append({"loteria":nome,"concurso":concurso,"premio":premio}); data=data or str(item.get("data") or "").strip()
    if not loterias: return 0
    thumb=gerar_capa_diaria(data,loterias,video_id=video_id)
    accounts=sorted({str(account).strip() for network,account,key in (cofre_cache.get("creds_rc",{}) or {}).keys() if str(network).strip().upper()=="YOUTUBE" and str(key).strip().upper()=="REFRESH_TOKEN" and account})
    updated=0
    for account in accounts:
        cid=cofre_get("YOUTUBE","CLIENT_ID",conta=account,default=""); sec=cofre_get("YOUTUBE","CLIENT_SECRET",conta=account,default=""); ref=cofre_get("YOUTUBE","REFRESH_TOKEN",conta=account,default="")
        if not (cid and sec and ref): continue
        try: upload_thumbnail(get_access_token(cid,sec,ref),video_id,thumb); updated+=1
        except Exception as exc: print(f"[THUMB] {account}: {exc}",flush=True)
    return updated


if __name__ == "__main__": reparar_ultima_capa_publicada()
