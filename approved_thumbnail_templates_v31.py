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

_LEGACY_INTRO = dv._intro_image
_LEGACY_SHORT = dv._result_short_image
_LEGACY_LIVE = yt.gerar_capa_live
_LEGACY_DAILY = yt.gerar_capa_diaria
_SPRITE: Image.Image | None = None


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
    """
    V33: NÃO amplia mais o sprite 160x90. A ampliação do sprite V31 era a causa
    das capas pixeladas/glitchadas no YouTube. A arte agora é renderizada
    diretamente em alta resolução pelo gerador vetorial aprovado V24 e só então
    redimensionada, preservando nitidez e legibilidade.
    """
    if not results:
        return None

    normalized: List[Dict[str, str]] = []
    for item in results:
        normalized.append({
            "loteria": _display_name(item.get("loteria")),
            "concurso": str(item.get("concurso") or "").strip(),
            "premio": str(item.get("premio") or "").strip(),
        })

    date = str(results[0].get("data") or "").strip()
    mode = "resultado"
    try:
        image = yt._draw_approved(date, normalized, prize_highlight=None, mode=mode)
    except Exception:
        return None

    if image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image.convert("RGB")

def _approved_intro(results: Sequence[Dict[str, Any]], size: Tuple[int, int]) -> Image.Image:
    approved = _render_horizontal(results, size)
    if approved is not None:
        return approved
    return _LEGACY_INTRO(results, size)


def _approved_short(data: Dict[str, Any]) -> Image.Image:
    slug = _slug(data.get("loteria"))
    if slug not in TILES:
        return _LEGACY_SHORT(data)

    size = (1080, 1920)
    approved = _render_horizontal([data], (1280, 720))
    if approved is None:
        raise RuntimeError(f"Não foi possível gerar o template aprovado para {slug}.")

    bg = approved.resize((3414, 1920), Image.Resampling.LANCZOS)
    left = (bg.width - size[0]) // 2
    bg = bg.crop((left, 0, left + size[0], size[1]))
    bg = bg.filter(ImageFilter.GaussianBlur(30))
    bg = ImageEnhance.Brightness(bg).enhance(0.34).convert("RGB")

    card_w = 1030
    card_h = round(card_w * 9 / 16)
    card = approved.resize((card_w, card_h), Image.Resampling.LANCZOS)
    x = (size[0] - card_w) // 2
    y = (size[1] - card_h) // 2

    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow, "RGBA")
    gd.rounded_rectangle((x - 15, y - 15, x + card_w + 15, y + card_h + 15), radius=30,
                         outline=(74, 190, 255, 190), width=12)
    glow = glow.filter(ImageFilter.GaussianBlur(16))
    bg.paste(glow, (0, 0), glow)
    bg.paste(card, (x, y))

    draw = ImageDraw.Draw(bg, "RGBA")
    draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=22, outline=(150, 225, 255, 230), width=4)
    brand = "PADRÃO OFICIAL • PORTAL SIMONSPORTS"
    font = _fit(draw, brand, 930, 34, 23)
    draw.text((size[0] // 2, y + card_h + 105), brand, font=font, fill=(215, 240, 255, 255), anchor="mm")
    return bg


def _safe_filename_date(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_-]+", "-", str(value or "hoje")).strip("-") or "hoje"


def gerar_capa_live(data: str, targets: Sequence[Tuple[str, str, str]], *, prize_highlight: Dict[str, str] | None = None) -> str:
    loterias = [{"loteria": display, "concurso": contest, "premio": "", "data": data} for _key, display, contest in targets]
    approved = _render_horizontal(loterias, (1280, 720))
    if approved is None:
        return _LEGACY_LIVE(data, targets, prize_highlight=prize_highlight)
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
        return _LEGACY_DAILY(data, loterias, video_id=video_id, prize_highlight=prize_highlight)
    yt.OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = yt.OUT_DIR / f"thumbnail_diaria_aprovada_v31_{_safe_filename_date(data)}_{video_id or 'novo'}.jpg"
    approved.save(path, "JPEG", quality=95, optimize=True)
    return str(path)


def install() -> None:
    dv._intro_image = _approved_intro
    dv._result_short_image = _approved_short
    yt.gerar_capa_live = gerar_capa_live
    yt.gerar_capa_diaria = gerar_capa_diaria


install()

__all__ = [
    "gerar_capa_live",
    "gerar_capa_diaria",
    "install",
]
