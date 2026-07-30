from __future__ import annotations

from typing import Any, Dict, Sequence, Tuple

from PIL import Image, ImageDraw

import loteca_columns_v18 as final
import loteca_video_v18 as base
from lottery_result_v18 import LotecaGame


_ORIGINAL_SUMMARY_SCENE = final._summary_scene
_ORIGINAL_POSTER_SCENE = final._poster_scene

WHITE = (255, 255, 255)
MUTED = (190, 236, 255)
DRAW_GRAY = (128, 136, 148)
DRAW_GRAY_BORDER = (180, 188, 198)
HOME_BLUE = (42, 184, 236)
HOME_BLUE_BADGE = (0, 119, 193)
HOME_BLUE_BORDER = (83, 203, 247)
AWAY_GREEN = (126, 211, 67)
AWAY_GREEN_BADGE = (76, 168, 43)
AWAY_GREEN_BORDER = (151, 231, 94)
ROW_FILL = (2, 30, 65, 255)
ROW_OUTLINE = (130, 217, 255, 120)


def _outcome(game: LotecaGame) -> str:
    if game.home_score > game.away_score:
        return "home"
    if game.home_score < game.away_score:
        return "away"
    return "draw"


def _badge_style(game: LotecaGame):
    outcome = _outcome(game)
    if outcome == "home":
        return HOME_BLUE_BADGE, HOME_BLUE_BORDER
    if outcome == "away":
        return AWAY_GREEN_BADGE, AWAY_GREEN_BORDER
    return DRAW_GRAY, DRAW_GRAY_BORDER


def _team_color(game: LotecaGame, side: str):
    outcome = _outcome(game)
    if outcome == "home" and side == "home":
        return HOME_BLUE
    if outcome == "away" and side == "away":
        return AWAY_GREEN
    return WHITE


def _score_color(game: LotecaGame, side: str):
    return _team_color(game, side)


def _draw_summary_row(
    draw: ImageDraw.ImageDraw,
    game: LotecaGame,
    y: int,
    *,
    left: int = 70,
    right: int = 1850,
) -> None:
    draw.rounded_rectangle(
        (left, y - 31, right, y + 39),
        radius=20,
        fill=ROW_FILL,
        outline=ROW_OUTLINE,
        width=2,
    )

    number_x = left + 125
    divider_x = left + 165
    home_x = left + 215
    score_home_x = left + 835
    score_x_x = left + 875
    score_away_x = left + 915
    away_x = left + 1015
    badge_left = right - 255
    badge_right = right - 20

    number_font = base._font(28, True)
    team_home = base._team(game.home)
    team_away = base._team(game.away)
    home_font = base._fit_font(draw, team_home, score_home_x - home_x - 55, 28, 17)
    away_font = base._fit_font(draw, team_away, badge_left - away_x - 35, 28, 17)
    score_font = base._font(29, True)

    draw.text((number_x, y + 3), f"{game.index:02d}.", font=number_font, fill=WHITE, anchor="rm")
    draw.line((divider_x, y - 25, divider_x, y + 33), fill=(105, 198, 235, 150), width=2)
    draw.text((home_x, y + 3), team_home, font=home_font, fill=_team_color(game, "home"), anchor="lm")

    draw.text((score_home_x, y + 3), str(game.home_score), font=score_font, fill=_score_color(game, "home"), anchor="rm")
    draw.text(
        (score_x_x, y + 3),
        "x",
        font=score_font,
        fill=DRAW_GRAY if _outcome(game) == "draw" else WHITE,
        anchor="mm",
    )
    draw.text((score_away_x, y + 3), str(game.away_score), font=score_font, fill=_score_color(game, "away"), anchor="lm")

    draw.text((away_x, y + 3), team_away, font=away_font, fill=_team_color(game, "away"), anchor="lm")

    badge_fill, badge_outline = _badge_style(game)
    draw.rounded_rectangle(
        (badge_left, y - 24, badge_right, y + 30),
        radius=15,
        fill=badge_fill,
        outline=badge_outline,
        width=2,
    )
    badge_font = base._fit_font(draw, final.result_label(game), badge_right - badge_left - 22, 23, 16)
    draw.text(
        ((badge_left + badge_right) / 2, y + 3),
        final.result_label(game),
        font=badge_font,
        fill=WHITE,
        anchor="mm",
    )


def summary_scene_aprovado(
    data: Dict[str, Any], games: Sequence[LotecaGame], start: int, end: int
) -> Image.Image:
    image = _ORIGINAL_SUMMARY_SCENE(data, games, start, end).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    y = 350
    for game in games[start:end]:
        _draw_summary_row(draw, game, y)
        y += 82
    return image.convert("RGB")


def _draw_poster_row(
    draw: ImageDraw.ImageDraw,
    game: LotecaGame,
    y: int,
    left: int,
    right: int,
) -> None:
    draw.rounded_rectangle(
        (left, y - 31, right, y + 38),
        radius=18,
        fill=ROW_FILL,
        outline=ROW_OUTLINE,
        width=2,
    )

    number_x = left + 50
    home_x = left + 72
    score_home_x = left + 360
    score_x_x = left + 388
    score_away_x = left + 416
    away_x = left + 450
    badge_left = right - 148
    badge_right = right - 12

    home = base._team(game.home)
    away = base._team(game.away)
    number_font = base._font(19, True)
    home_font = base._fit_font(draw, home, score_home_x - home_x - 25, 19, 12)
    away_font = base._fit_font(draw, away, badge_left - away_x - 18, 19, 12)
    score_font = base._font(20, True)

    draw.text((number_x, y + 3), f"{game.index:02d}.", font=number_font, fill=WHITE, anchor="rm")
    draw.text((home_x, y + 3), home, font=home_font, fill=_team_color(game, "home"), anchor="lm")
    draw.text((score_home_x, y + 3), str(game.home_score), font=score_font, fill=_score_color(game, "home"), anchor="rm")
    draw.text(
        (score_x_x, y + 3),
        "x",
        font=score_font,
        fill=DRAW_GRAY if _outcome(game) == "draw" else WHITE,
        anchor="mm",
    )
    draw.text((score_away_x, y + 3), str(game.away_score), font=score_font, fill=_score_color(game, "away"), anchor="lm")
    draw.text((away_x, y + 3), away, font=away_font, fill=_team_color(game, "away"), anchor="lm")

    badge_fill, badge_outline = _badge_style(game)
    draw.rounded_rectangle(
        (badge_left, y - 23, badge_right, y + 29),
        radius=14,
        fill=badge_fill,
        outline=badge_outline,
        width=2,
    )
    badge_font = base._fit_font(draw, final.result_label(game), badge_right - badge_left - 16, 16, 11)
    draw.text(
        ((badge_left + badge_right) / 2, y + 3),
        final.result_label(game),
        font=badge_font,
        fill=WHITE,
        anchor="mm",
    )


def poster_scene_aprovado(data: Dict[str, Any], games: Sequence[LotecaGame]) -> Image.Image:
    image = _ORIGINAL_POSTER_SCENE(data, games).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    for index, game in enumerate(games[:14]):
        column = 0 if index < 7 else 1
        row = index if index < 7 else index - 7
        left = 65 + column * 930
        right = left + 860
        y = 305 + row * 92
        _draw_poster_row(draw, game, y, left, right)
    return image.convert("RGB")


def install_visual_aprovado() -> None:
    final._summary_scene = summary_scene_aprovado
    final._poster_scene = poster_scene_aprovado


__all__ = [
    "install_visual_aprovado",
    "poster_scene_aprovado",
    "summary_scene_aprovado",
]
