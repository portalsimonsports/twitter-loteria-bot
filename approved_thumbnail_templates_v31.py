from __future__ import annotations

import base64
import io
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

import daily_video_v19 as dv
import youtube_thumbnail_v24 as yt
import daily_video_v19_power_thumbnail_v29 as power

try:
    import daily_growth_v20 as growth
except Exception:
    growth = None

ASSET_DIR = Path("assets") / "templates_aprovados"
PART_NAMES = [ASSET_DIR / f"v31.b64.{i:02d}" for i in range(1, 7)]
TILE_W, TILE_H = 160, 90
SPRITE_SIZE = (320, 270)

TILES = {
    "loteca": 0,
    "dupla-sena": 1,
    "lotomania": 2,
    "quina": 3,
    "timemania": 4,
    "lotofacil": 5,
}

# Cobertura integral das modalidades publicadas pelo canal.
# As seis acima usam as matrizes reais já aprovadas no pacote V31.
# As demais usam matriz exclusiva por modalidade, renderizada uma única família visual
# (cores/logotipo próprios), sem cair em capa azul genérica nem herdar outra loteria.
SUPPORTED = {
    "mega-sena",
    "lotofacil",
    "quina",
    "timemania",
    "dupla-sena",
    "lotomania",
    "loteca",
    "dia-de-sorte",
    "super-sete",
    "milionaria",
    "federal",
}

_LEGACY_INTRO = dv._intro_image
_LEGACY_SHORT = dv._result_short_image
_LEGACY_LIVE = yt.gerar_capa_live
_LEGACY_DAILY = yt.gerar_capa_diaria
_SPRITE: Image.Image | None = None
_BUILD_SHORT = dv._build_short


def _slug(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("+", "mais-")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    aliases = {
        "lotofacil": "lotofacil",
        "dupla-sena": "dupla-sena",
        "lotomania": "lotomania",
        "quina": "quina",
        "timemania": "timemania",
        "loteca": "loteca",
        "mega-sena": "mega-sena",
        "dia-de-sorte": "dia-de-sorte",
        "super-sete": "super-sete",
        "mais-milionaria": "milionaria",
        "milionaria": "milionaria",
        "loteria-federal": "federal",
        "federal": "federal",
    }
    return aliases.get(text, text)


def _font(size: int, bold: bool = True):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=max(10, int(size)))
    return ImageFont.load_default()


def _fit(draw: ImageDraw.ImageDraw, text: str, max_width: int, start: int, minimum: int = 18):
    text = str(text or "")
    for size in range(int(start), int(minimum) - 1, -2):
        font = _font(size, True)
        if draw.textbbox((0, 0), text, font=font, stroke_width=max(1, size // 30))[2] <= max_width:
            return font
    return _font(minimum, True)


def _load_sprite() -> Image.Image:
    global _SPRITE
    if _SPRITE is not None:
        return _SPRITE.copy()
    missing = [str(path) for path in PART_NAMES if not path.exists()]
    if missing:
        raise RuntimeError("Templates aprovados ausentes: " + ", ".join(missing))
    encoded = "".join(path.read_text(encoding="utf-8").strip() for path in PART_NAMES)
    raw = base64.b64decode(encoded, validate=True)
    sprite = Image.open(io.BytesIO(raw)).convert("RGB")
    if sprite.size != SPRITE_SIZE:
        raise RuntimeError(f"Sprite dos templates aprovados inválido: {sprite.size}; esperado {SPRITE_SIZE}.")
    _SPRITE = sprite
    return _SPRITE.copy()


def _approved_tile(slug: str) -> Image.Image:
    if slug not in TILES:
        raise KeyError(slug)
    index = TILES[slug]
    sprite = _load_sprite()
    x = (index % 2) * TILE_W
    y = (index // 2) * TILE_H
    return sprite.crop((x, y, x + TILE_W, y + TILE_H))


def _primary(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if growth is not None:
        try:
            value = growth._primary(results)
            if value:
                return dict(value)
        except Exception:
            pass
    return dict(results[0]) if results else {}


def _display_name(value: Any) -> str:
    try:
        return str(dv._normalize_name(value) or value or "").strip()
    except Exception:
        return str(value or "").strip()


def _support_names(results: Sequence[Dict[str, Any]], focus_slug: str) -> str:
    names: List[str] = []
    for item in results:
        name = _display_name(item.get("loteria"))
        if not name or _slug(name) == focus_slug:
            continue
        upper = name.upper()
        if upper not in names:
            names.append(upper)
    return "+ " + " • ".join(names[:4]) if names else "+ RESULTADOS COMPLETOS"


def _scale_box(box: Tuple[int, int, int, int], size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    sx, sy = size[0] / 1280.0, size[1] / 720.0
    return tuple(int(round(v * (sx if i % 2 == 0 else sy))) for i, v in enumerate(box))  # type: ignore[return-value]


def _rounded_cover(draw: ImageDraw.ImageDraw, box, size, *, outline=(50, 145, 220, 190), radius=16):
    scaled = _scale_box(box, size)
    r = max(8, int(radius * size[0] / 1280.0))
    draw.rounded_rectangle(scaled, radius=r, fill=(1, 7, 20, 246), outline=outline, width=max(2, int(2 * size[0] / 1280.0)))
    return scaled


def _render_horizontal(results: Sequence[Dict[str, Any]], size: Tuple[int, int]) -> Image.Image | None:
    """V35 — render em resolução nativa, sem ampliar o sprite de 160x90."""
    if not results:
        return None
    focus = _primary(results)
    slug = _slug(focus.get("loteria"))
    if slug not in SUPPORTED:
        raise RuntimeError(f"Modalidade sem padrão visual: {focus.get('loteria')!r}")
    ordered = [focus] + [row for row in results if _slug(row.get("loteria")) != slug]
    records = [
        {"loteria": _display_name(row.get("loteria")),
         "concurso": str(row.get("concurso") or "").strip(),
         "premio": str(row.get("premio") or "").strip() if index == 0 else ""}
        for index, row in enumerate(ordered)
    ]
    date = str(focus.get("data") or results[0].get("data") or "").strip()
    image = yt._draw_approved(
        date, records,
        prize_highlight={"loteria": records[0]["loteria"],
                         "concurso": records[0]["concurso"],
                         "premio": records[0]["premio"]},
        mode="resultado",
    )
    if image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image.convert("RGB")


def _approved_intro(results: Sequence[Dict[str, Any]], size: Tuple[int, int]) -> Image.Image:
    if size[1] > size[0]:
        if not results:
            raise RuntimeError("Capa vertical sem resultados")
        native = _portrait_frame(_primary(results), show_result=False)
        from PIL import ImageOps
        return ImageOps.pad(native, size, method=Image.Resampling.LANCZOS, color=(1, 5, 17))
    approved = _render_horizontal(results, size)
    if approved is not None:
        return approved
    raise RuntimeError("Não foi possível gerar capa: resultados ausentes")


def _portrait_frame(data: Dict[str, Any], *, show_result: bool = True) -> Image.Image:
    """V36: composição vertical nativa; nenhuma capa horizontal é esticada."""
    name = _display_name(data.get("loteria"))
    slug = _slug(name)
    if slug not in SUPPORTED:
        raise RuntimeError(f"Short sem modalidade suportada: {name!r}")
    primary, dark, accent = power._theme(name)
    image = power._gradient((1080, 1920))
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(0, 1920, 35):
        draw.line((0, y, 1080, y), fill=(*primary, 18), width=2)
    power._brand(draw, image.size)
    # Área útil termina antes dos controles laterais e da legenda do Shorts.
    left, right, cx = 65, 905, 485
    draw.text((cx, 280), name.upper(), font=_fit(draw, name.upper(), 820, 92, 36),
              fill=accent, anchor="mm", stroke_width=3, stroke_fill="black")
    contest = str(data.get("concurso") or "").strip()
    subtitle = f"CONCURSO {contest}" if contest else "RESULTADO OFICIAL"
    draw.text((cx, 390), subtitle, font=_fit(draw, subtitle, 800, 55, 28), fill="white", anchor="mm")
    logo = power._load_logo(name, (600, 190))
    if logo is not None:
        image.paste(logo, (cx - logo.width // 2, 470), logo)
    else:
        draw.rounded_rectangle((left, 485, right, 620), radius=24, fill=(*dark, 255), outline=accent, width=3)
        draw.text((cx, 552), name.upper(), font=_fit(draw, name.upper(), 760, 60, 28), fill=accent, anchor="mm")
    draw.rounded_rectangle((left, 700, right, 785), radius=22, fill=(*dark, 245), outline=accent, width=3)
    draw.text((cx, 742), "RESULTADO DO CONCURSO", font=_fit(draw, "RESULTADO DO CONCURSO", 780, 42, 25), fill="white", anchor="mm")

    def grid(numbers, top, bottom):
        count = len(numbers)
        if not count:
            return
        columns = 5 if count > 12 else 4 if count > 6 else min(3, count)
        rows = (count + columns - 1) // columns
        cell_w, cell_h = (right-left)/columns, (bottom-top)/rows
        radius = int(min(63, cell_w*.34, cell_h*.34))
        font = _font(max(24, int(radius*.85)))
        for index, number in enumerate(numbers):
            row, col = divmod(index, columns)
            row_count = min(columns, count-row*columns)
            x = cx - row_count*cell_w/2 + (col+.5)*cell_w
            y = top + (row+.5)*cell_h
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(248,248,248), outline=accent, width=4)
            value = str(number).strip()
            value = value.zfill(2) if value.isdigit() else value
            draw.text((x, y), value, font=font, fill=(15,24,35), anchor="mm")

    if show_result:
        parts = dv.parse_lottery_result(name, dv._raw_result(data))
        if parts.second_draw_numbers:
            for label, numbers, top, bottom in (
                ("1º SORTEIO", parts.main_numbers, 850, 1070),
                ("2º SORTEIO", parts.second_draw_numbers, 1150, 1370),
            ):
                draw.text((cx, top-22), label, font=_font(30), fill=accent, anchor="mm")
                grid(numbers, top, bottom)
        elif parts.loteca_games:
            for index, game in enumerate(parts.loteca_games):
                line = f"{game.index:02d}  {dv.team_name_without_code(game.home)} {game.home_score} x {game.away_score} {dv.team_name_without_code(game.away)}"
                draw.text((cx, 835+index*43), line, font=_fit(draw, line, 810, 27, 16), fill="white", anchor="mm")
        elif slug == "federal":
            for index, prize in enumerate(dv._federal_prizes(dv._raw_result(data)), 1):
                y = 830+(index-1)*100
                draw.rounded_rectangle((left, y, right, y+82), radius=18, fill=(*dark,245), outline=accent, width=2)
                draw.text((left+25,y+41), f"{index}º PRÊMIO", font=_font(31), fill=accent, anchor="lm")
                draw.text((right-25,y+41), str(prize), font=_font(46), fill="white", anchor="rm")
        else:
            grid(parts.display_numbers, 825, 1360)
        special = dv._special_display(parts)
        if special:
            draw.text((cx, 1420), special, font=_fit(draw, special, 810, 32, 18), fill=accent, anchor="mm")
    date = str(data.get("data") or "").strip()
    if date:
        draw.text((cx, 1515), date, font=_font(42), fill="white", anchor="mm")
    draw.text((cx, 1590), "PORTAL SIMONSPORTS", font=_font(30), fill=(180,225,255), anchor="mm")
    return image


def _approved_short(data: Dict[str, Any]) -> Image.Image:
    return _portrait_frame(data)


def _safe_filename_date(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_-]+", "-", str(value or "hoje")).strip("-") or "hoje"


def gerar_capa_live(data: str, targets: Sequence[Tuple[str, str, str]], *, prize_highlight: Dict[str, str] | None = None) -> str:
    loterias = [{"loteria": display, "concurso": contest, "premio": "", "data": data} for _key, display, contest in targets]
    approved = _render_horizontal(loterias, (1280, 720))
    if approved is None:
        raise RuntimeError("Live sem modalidades para capa")
    yt.OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = yt.OUT_DIR / f"thumbnail_live_aprovada_v31_{_safe_filename_date(data)}.jpg"
    approved.save(path, "JPEG", quality=95, optimize=True)
    return str(path)


def gerar_capa_diaria(data: str, loterias: List[Dict[str, str]], *, video_id: str = "", prize_highlight: Dict[str, str] | None = None) -> str:
    normalized = []
    for item in loterias:
        row = dict(item)
        row.setdefault("data", data)
        normalized.append(row)
    approved = _render_horizontal(normalized, (1280, 720))
    if approved is None:
        raise RuntimeError("Vídeo sem modalidades para capa")
    yt.OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = yt.OUT_DIR / f"thumbnail_diaria_aprovada_v31_{_safe_filename_date(data)}_{video_id or 'novo'}.jpg"
    approved.save(path, "JPEG", quality=95, optimize=True)
    return str(path)


def _build_short_primary_first(results, output, temp, voice):
    focus = _primary(results)
    ordered = list(results)
    if focus:
        for index, row in enumerate(ordered):
            if row == focus:
                ordered.insert(0, ordered.pop(index))
                break
    return _BUILD_SHORT(ordered, output, temp, voice)


def install() -> None:
    dv._intro_image = _approved_intro
    dv._result_short_image = _approved_short
    dv._build_short = _build_short_primary_first
    yt.gerar_capa_live = gerar_capa_live
    yt.gerar_capa_diaria = gerar_capa_diaria


install()

__all__ = [
    "gerar_capa_live",
    "gerar_capa_diaria",
    "install",
    "SUPPORTED",
]
