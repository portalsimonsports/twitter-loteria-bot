from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw

import loteca_video_v18 as base
from lottery_result_v18 import LotecaGame, team_name_without_code
from voice_narration_v18 import SpeechSegment


_BASE_INTRO_SCENE = base._intro_scene
_BASE_GAME_SCENE = base._game_scene
_BASE_SUMMARY_SCENE = base._summary_scene
_BASE_POSTER_SCENE = base._poster_scene

FINAL_SHORT_DURATION = 104.0
FINAL_SHORT_GAME_SLOT = 5.80


def result_label(game: LotecaGame) -> str:
    """Retorna exatamente o padrão de conferência usado na Loteca."""
    if game.home_score > game.away_score:
        return "COLUNA 1"
    if game.home_score == game.away_score:
        return "EMPATE"
    return "COLUNA 2"


def result_speech(game: LotecaGame) -> str:
    if game.home_score > game.away_score:
        return "Coluna 1"
    if game.home_score == game.away_score:
        return "Empate"
    return "Coluna 2"


def game_speech(game: LotecaGame) -> str:
    home = team_name_without_code(game.home).title()
    away = team_name_without_code(game.away).title()
    return (
        f"Jogo {game.index}. {home}, {game.home_score}. "
        f"{away}, {game.away_score}. {result_speech(game)}."
    )


def _intro_scene(data: Dict[str, Any], size: Tuple[int, int]) -> Image.Image:
    image = _BASE_INTRO_SCENE(data, size).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = size
    horizontal = width > height
    center = width // 2
    scale = base._scale(size)
    y = 825 if horizontal else 1140

    draw.rounded_rectangle(
        (center - 610 * scale, y - 58 * scale, center + 610 * scale, y + 58 * scale),
        radius=28 * scale,
        fill=(0, 18, 42, 235),
        outline=(160, 230, 255, 175),
        width=max(2, round(3 * scale)),
    )
    draw.text(
        (center, y),
        "COLUNA 1: MANDANTE  •  EMPATE  •  COLUNA 2: VISITANTE",
        font=base._font(round((29 if horizontal else 25) * scale), True),
        fill="white",
        anchor="mm",
    )
    return image.convert("RGB")


def _game_scene(data: Dict[str, Any], game: LotecaGame, size: Tuple[int, int]) -> Image.Image:
    image = _BASE_GAME_SCENE(data, game, size).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = size
    horizontal = width > height
    center = width // 2
    y0 = 265 if horizontal else 360
    result_y = y0 + (610 if horizontal else 930)

    # Remove o antigo texto "vitória do..."/"empate" e mantém somente
    # o padrão final de conferência: COLUNA 1, EMPATE ou COLUNA 2.
    draw.rounded_rectangle(
        (55, result_y - 88, width - 55, result_y + 178),
        radius=40,
        fill=(0, 20, 48, 255),
    )
    draw.rounded_rectangle(
        (90, result_y - 66, width - 90, result_y + 66),
        radius=34,
        fill=(0, 119, 193, 248),
        outline=(160, 230, 255),
        width=3,
    )
    label = result_label(game)
    label_font = base._fit_font(draw, label, width - 210, 58 if horizontal else 49, 28)
    draw.text((center, result_y), label, font=label_font, fill="white", anchor="mm")

    if game.day:
        draw.text(
            (center, result_y + 130),
            f"PARTIDA: {game.day.upper()}",
            font=base._font(23 if horizontal else 22, True),
            fill=(190, 236, 255),
            anchor="mm",
        )
    return image.convert("RGB")


def _summary_scene(
    data: Dict[str, Any], games: Sequence[LotecaGame], start: int, end: int
) -> Image.Image:
    image = _BASE_SUMMARY_SCENE(data, games, start, end).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    y = 350

    for game in games[start:end]:
        draw.rounded_rectangle(
            (70, y - 30, 1850, y + 38),
            radius=20,
            fill=(2, 30, 65, 255),
            outline=(130, 217, 255, 120),
            width=2,
        )
        line = (
            f"{game.index:02d}. {base._team(game.home)}  {game.home_score} x {game.away_score}  "
            f"{base._team(game.away)}  —  {result_label(game)}"
        )
        font = base._fit_font(draw, line, 1760, 29, 17)
        draw.text((960, y + 3), line, font=font, fill="white", anchor="mm")
        y += 82
    return image.convert("RGB")


def _poster_scene(data: Dict[str, Any], games: Sequence[LotecaGame]) -> Image.Image:
    image = _BASE_POSTER_SCENE(data, games).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")

    for index, game in enumerate(games[:14]):
        column = 0 if index < 7 else 1
        row = index if index < 7 else index - 7
        left = 65 + column * 930
        right = left + 860
        y = 305 + row * 92
        draw.rounded_rectangle(
            (left, y - 31, right, y + 38),
            radius=18,
            fill=(2, 30, 65, 255),
            outline=(130, 217, 255, 120),
            width=2,
        )
        line = (
            f"{game.index:02d}. {base._team(game.home)}  {game.home_score} x {game.away_score}  "
            f"{base._team(game.away)}  —  {result_label(game)}"
        )
        font = base._fit_font(draw, line, right - left - 36, 23, 14)
        draw.text(((left + right) / 2, y + 3), line, font=font, fill="white", anchor="mm")
    return image.convert("RGB")


def _full_segments(
    data: Dict[str, Any], games: Sequence[LotecaGame], pair: Tuple[str, str]
) -> List[SpeechSegment]:
    primary, secondary = pair
    contest = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or "").strip()

    segments: List[SpeechSegment] = [
        SpeechSegment(
            0.35,
            primary,
            "Olá! Seja muito bem-vindo ao Portal SimonSports. Hoje a nossa conferência é especial: vamos acompanhar, jogo a jogo, o resultado completo da Loteca.",
            1.0,
            None,
            "opening",
        ),
        SpeechSegment(
            9.20,
            secondary,
            f"Este é o concurso {contest}"
            + (f", com resultados divulgados em {date}. " if date else ". ")
            + "Na Loteca, coluna um representa o mandante, empate representa o resultado igual e coluna dois representa o visitante.",
            1.0,
            None,
            "opening",
        ),
        SpeechSegment(
            20.20,
            primary,
            "Separe o seu comprovante e acompanhe com a gente. Em cada jogo, vamos informar o placar e, logo depois, Coluna 1, Empate ou Coluna 2.",
            1.0,
            None,
            "opening",
        ),
    ]

    interactions = {
        4: (
            "Até aqui, seguimos com a conferência da Loteca. Aproveite para deixar nos comentários "
            "que tipo de sugestão você gostaria de ver aqui no canal."
        ),
        8: (
            "Seguimos com os próximos jogos. Se você acompanha os resultados por aqui, aproveite para "
            "comentar quais conteúdos gostaria de ver nas próximas publicações."
        ),
        12: (
            "Estamos chegando à reta final da conferência. A sua participação é importante: deixe nos "
            "comentários sugestões de vídeos e conteúdos para o canal."
        ),
    }

    for index, game in enumerate(games):
        start = base.FULL_GAME_START + index * base.FULL_GAME_SLOT
        voice = primary if index % 2 == 0 else secondary
        segments.append(
            SpeechSegment(start + 0.80, voice, game_speech(game), 1.01, "-5%", "loteca_game")
        )
        game_number = index + 1
        if game_number in interactions:
            other = secondary if voice == primary else primary
            segments.append(
                SpeechSegment(start + 8.55, other, interactions[game_number], 1.0, "-2%", "engagement")
            )

    segments.extend(
        [
            SpeechSegment(
                213.50,
                primary,
                "Os quatorze resultados já foram apresentados. Na tela, você confere agora o resumo completo do concurso, com o placar e a indicação correspondente de cada jogo.",
                1.0,
                "-2%",
                "summary",
            ),
            SpeechSegment(
                230.00,
                secondary,
                "Para consultar este e outros resultados da Loteca, acesse portalsimonsports.com e abra a seção Loterias Caixa.",
                1.0,
                "-2%",
                "closing",
            ),
            SpeechSegment(
                243.00,
                primary,
                "Se este conteúdo foi útil, deixe o seu like, compartilhe e inscreva-se no canal.",
                1.0,
                "-2%",
                "closing",
            ),
            SpeechSegment(
                252.50,
                secondary,
                "E conte nos comentários que tipo de sugestão você gostaria de ver nas próximas publicações.",
                1.0,
                "-2%",
                "closing",
            ),
            SpeechSegment(
                264.00,
                primary,
                "SimonSports, simplesmente o melhor. Até o próximo resultado!",
                1.0,
                "-2%",
                "closing",
            ),
        ]
    )
    return sorted(segments, key=lambda item: item.start)


def _short_segments(
    data: Dict[str, Any], games: Sequence[LotecaGame], voice: str
) -> List[SpeechSegment]:
    contest = str(data.get("concurso") or "").strip()
    segments: List[SpeechSegment] = [
        SpeechSegment(
            0.20,
            voice,
            f"Portal SimonSports. Resultado da Loteca, concurso {contest}. Confira os quatorze jogos.",
            1.01,
            "-2%",
            "opening",
        )
    ]

    for index, game in enumerate(games):
        start = base.SHORT_GAME_START + index * base.SHORT_GAME_SLOT
        segments.append(
            SpeechSegment(start, voice, game_speech(game), 1.02, "-2%", "loteca_game")
        )

    segments.extend(
        [
            SpeechSegment(
                91.00,
                voice,
                "Confira o resultado completo no canal e deixe nos comentários sugestões de conteúdos para as próximas publicações.",
                1.01,
                "-2%",
                "closing",
            ),
            SpeechSegment(
                99.00,
                voice,
                "Portal SimonSports. Inscreva-se e acompanhe os próximos resultados.",
                1.01,
                "-2%",
                "closing",
            ),
        ]
    )
    return sorted(segments, key=lambda item: item.start)


def gerar_pacote_loteca(data: Dict[str, Any]) -> Dict[str, str]:
    originals = {
        "_intro_scene": base._intro_scene,
        "_game_scene": base._game_scene,
        "_summary_scene": base._summary_scene,
        "_poster_scene": base._poster_scene,
        "_full_segments": base._full_segments,
        "_short_segments": base._short_segments,
        "SHORT_DURATION": base.SHORT_DURATION,
        "SHORT_GAME_SLOT": base.SHORT_GAME_SLOT,
    }

    base._intro_scene = _intro_scene
    base._game_scene = _game_scene
    base._summary_scene = _summary_scene
    base._poster_scene = _poster_scene
    base._full_segments = _full_segments
    base._short_segments = _short_segments
    base.SHORT_DURATION = FINAL_SHORT_DURATION
    base.SHORT_GAME_SLOT = FINAL_SHORT_GAME_SLOT

    try:
        package = base.gerar_pacote_loteca(data)
        package["modo_apresentacao"] = (
            "Loteca final: Coluna 1, Empate e Coluna 2, com dois apresentadores"
        )
        return package
    finally:
        for name, value in originals.items():
            setattr(base, name, value)


__all__ = [
    "FINAL_SHORT_DURATION",
    "FINAL_SHORT_GAME_SLOT",
    "game_speech",
    "gerar_pacote_loteca",
    "result_label",
    "result_speech",
]
