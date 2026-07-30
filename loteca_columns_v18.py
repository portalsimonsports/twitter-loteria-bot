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
_BASE_FULL_SEGMENTS = base._full_segments
_BASE_SHORT_SEGMENTS = base._short_segments


def column_code(game: LotecaGame) -> str:
    if game.home_score > game.away_score:
        return "1"
    if game.home_score == game.away_score:
        return "X"
    return "2"


def column_meaning(game: LotecaGame) -> str:
    code = column_code(game)
    return {"1": "MANDANTE", "X": "EMPATE", "2": "VISITANTE"}[code]


def game_speech(game: LotecaGame, *, compact: bool = False) -> str:
    home = team_name_without_code(game.home).title()
    away = team_name_without_code(game.away).title()
    if compact:
        return (
            f"Jogo {game.index}. {home}, {game.home_score}. "
            f"{away}, {game.away_score}. Coluna {column_code(game)}."
        )
    return (
        f"Jogo {game.index}. {home}, {game.home_score}. "
        f"{away}, {game.away_score}. Resultado na coluna {column_code(game)}."
    )


def _intro_scene(data: Dict[str, Any], size: Tuple[int, int]) -> Image.Image:
    image = _BASE_INTRO_SCENE(data, size).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = size
    horizontal = width > height
    center = width // 2
    y = 825 if horizontal else 1140
    scale = base._scale(size)
    draw.rounded_rectangle(
        (center - 610 * scale, y - 55 * scale, center + 610 * scale, y + 55 * scale),
        radius=28 * scale,
        fill=(0, 18, 42, 225),
        outline=(160, 230, 255, 165),
        width=max(2, round(3 * scale)),
    )
    draw.text(
        (center, y),
        "COLUNA 1: MANDANTE  •  COLUNA X: EMPATE  •  COLUNA 2: VISITANTE",
        font=base._font(round((28 if horizontal else 25) * scale), True),
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

    # Apaga a classificação anterior baseada em vitória/empate e preserva o placar.
    draw.rounded_rectangle(
        (55, result_y - 82, width - 55, result_y + 175),
        radius=40,
        fill=(0, 20, 48, 255),
    )
    draw.rounded_rectangle(
        (90, result_y - 62, width - 90, result_y + 62),
        radius=34,
        fill=(0, 119, 193, 245),
        outline=(160, 230, 255),
        width=3,
    )
    label = f"RESULTADO LOTECA: COLUNA {column_code(game)}"
    label_font = base._fit_font(draw, label, width - 210, 47 if horizontal else 41, 25)
    draw.text((center, result_y), label, font=label_font, fill="white", anchor="mm")
    draw.text(
        (center, result_y + 105),
        column_meaning(game),
        font=base._font(27 if horizontal else 25, True),
        fill=(255, 224, 105),
        anchor="mm",
    )
    if game.day:
        draw.text(
            (center, result_y + 150),
            f"PARTIDA: {game.day.upper()}",
            font=base._font(22, True),
            fill=(190, 236, 255),
            anchor="mm",
        )
    return image.convert("RGB")


def _summary_scene(
    data: Dict[str, Any], games: Sequence[LotecaGame], start: int, end: int
) -> Image.Image:
    image = _BASE_SUMMARY_SCENE(data, games, start, end).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    # Recria as linhas para acrescentar a coluna oficial ao lado do placar.
    y = 350
    for game in games[start:end]:
        draw.rounded_rectangle(
            (70, y - 30, 1850, y + 38),
            radius=20,
            fill=(2, 30, 65, 255),
            outline=(130, 217, 255, 115),
            width=2,
        )
        line = (
            f"{game.index:02d}. {base._team(game.home)}  {game.home_score} x {game.away_score}  "
            f"{base._team(game.away)}  •  COLUNA {column_code(game)}"
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
            outline=(130, 217, 255, 115),
            width=2,
        )
        line = (
            f"{game.index:02d}. {base._team(game.home)}  {game.home_score} x {game.away_score}  "
            f"{base._team(game.away)}  •  {column_code(game)}"
        )
        font = base._fit_font(draw, line, right - left - 40, 24, 15)
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
            + "Na Loteca, a coluna um corresponde ao mandante, a coluna X ao empate e a coluna dois ao visitante.",
            1.0,
            None,
            "opening",
        ),
        SpeechSegment(
            20.20,
            primary,
            "Separe o seu comprovante e acompanhe com a gente. Em cada jogo, vamos informar o placar e a coluna correspondente.",
            1.0,
            None,
            "opening",
        ),
    ]
    interactions = {
        4: "Quatro jogos conferidos. Quantas colunas você acertou até aqui? Algum resultado surpreendeu?",
        8: "Chegamos à metade do concurso. Como está a sua conferência? Já apareceu alguma zebra?",
        12: "Entramos na reta final. Faltam dois jogos. Conte nos comentários como está o seu desempenho.",
    }
    for index, game in enumerate(games):
        start = base.FULL_GAME_START + index * base.FULL_GAME_SLOT
        voice = primary if index % 2 == 0 else secondary
        segments.append(
            SpeechSegment(start + 0.80, voice, game_speech(game), 1.02, "-2%", "loteca_game")
        )
        game_number = index + 1
        if game_number in interactions:
            other = secondary if voice == primary else primary
            segments.append(
                SpeechSegment(start + 8.70, other, interactions[game_number], 1.0, None, "engagement")
            )
    segments.extend(
        [
            SpeechSegment(
                213.50,
                primary,
                "As quatorze colunas já foram apresentadas. Na tela, você confere agora o resumo completo do concurso.",
                1.0,
                None,
                "summary",
            ),
            SpeechSegment(
                228.00,
                secondary,
                "Revise com calma as suas marcações. Quantas colunas você acertou? Teve algum resultado que, na sua opinião, foi uma verdadeira zebra?",
                1.0,
                None,
                "closing",
            ),
            SpeechSegment(
                241.50,
                primary,
                "Para consultar este e outros resultados da Loteca, acesse portalsimonsports.com e abra a seção Loterias Caixa.",
                1.0,
                None,
                "closing",
            ),
            SpeechSegment(
                254.00,
                secondary,
                "Deixe o seu like, compartilhe este vídeo e inscreva-se no canal para acompanhar os próximos concursos.",
                1.0,
                None,
                "closing",
            ),
            SpeechSegment(
                264.00,
                primary,
                "SimonSports, simplesmente o melhor. Até o próximo resultado!",
                1.0,
                None,
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
            f"Portal SimonSports. Resultado da Loteca, concurso {contest}. Confira os quatorze jogos e as colunas oficiais.",
            1.02,
            "+3%",
            "opening",
        )
    ]
    for index, game in enumerate(games):
        start = base.SHORT_GAME_START + index * base.SHORT_GAME_SLOT
        segments.append(
            SpeechSegment(start, voice, game_speech(game, compact=True), 1.03, "+3%", "loteca_game")
        )
    segments.extend(
        [
            SpeechSegment(
                76.00,
                voice,
                "Confira o resultado completo no canal e conte nos comentários quantas colunas você acertou.",
                1.02,
                "+3%",
                "closing",
            ),
            SpeechSegment(
                85.00,
                voice,
                "Portal SimonSports. Inscreva-se e acompanhe os próximos resultados.",
                1.02,
                "+3%",
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
    }
    base._intro_scene = _intro_scene
    base._game_scene = _game_scene
    base._summary_scene = _summary_scene
    base._poster_scene = _poster_scene
    base._full_segments = _full_segments
    base._short_segments = _short_segments
    try:
        package = base.gerar_pacote_loteca(data)
        package["modo_apresentacao"] = "Loteca por colunas 1, X e 2 com dois apresentadores"
        return package
    finally:
        for name, value in originals.items():
            setattr(base, name, value)


__all__ = ["column_code", "game_speech", "gerar_pacote_loteca"]
