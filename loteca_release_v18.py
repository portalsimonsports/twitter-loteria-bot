from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Dict, List, Sequence, Tuple

import loteca_columns_v18 as final
import loteca_video_v18 as base
from loteca_visual_aprovado_v18 import install_visual_aprovado
from lottery_result_v18 import LotecaGame
from voice_narration_v18 import SpeechSegment


# Cada resultado fica nove segundos na tela. Como a leitura de cada jogo ocupa
# aproximadamente cinco a seis segundos, restam perto de três segundos antes
# da entrada do próximo resultado, sem acelerar excessivamente os locutores.
FINAL_FULL_GAME_SLOT = 9.0
FINAL_FULL_DURATION = 214.0
_BASE_FINAL_SHORT_SEGMENTS = final._short_segments


def _normalize_loteca_speech(text: str) -> str:
    """Ajustes fonéticos usados somente no áudio, nunca no texto exibido."""
    value = str(text or "")
    value = value.replace("SimonSports", "Simon Sports")
    value = re.sub(r"\bJogos\b", "Jôgos", value)
    value = re.sub(r"\bjogos\b", "jôgos", value)
    value = re.sub(r"\bJogo\b", "Jôgo", value)
    value = re.sub(r"\bjogo\b", "jôgo", value)
    value = re.sub(r"\bFranca\b", "França", value)
    return value


def _game_start(index: int) -> float:
    return base.FULL_GAME_START + index * FINAL_FULL_GAME_SLOT


def _full_segments_natural(
    data: Dict[str, Any], games: Sequence[LotecaGame], pair: Tuple[str, str]
) -> List[SpeechSegment]:
    primary, secondary = pair
    contest = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or "").strip()

    segments: List[SpeechSegment] = [
        SpeechSegment(
            0.35,
            primary,
            "Olá! Seja muito bem-vindo ao Portal Simon Sports, simplesmente o melhor.",
            1.0,
            "-10%",
            "opening",
        ),
        SpeechSegment(
            7.00,
            secondary,
            _normalize_loteca_speech(
                "Hoje vamos acompanhar o resultado completo da Loteca"
                + (f", concurso {contest}" if contest else "")
                + (f", com resultados divulgados em {date}." if date else ".")
            ),
            1.0,
            "-9%",
            "opening",
        ),
        SpeechSegment(
            14.20,
            primary,
            "Na Loteca, coluna um representa o mandante, empate representa resultado igual e coluna dois representa o visitante.",
            1.0,
            "-9%",
            "opening",
        ),
        SpeechSegment(
            25.10,
            secondary,
            _normalize_loteca_speech("Separe o seu comprovante. Vamos aos resultados dos jôgos."),
            1.0,
            "-8%",
            "opening",
        ),
    ]

    short_interactions = {
        4: "Que conteúdo você gostaria de ver aqui? Conte nos comentários.",
        8: "Sua sugestão ajuda o canal. Escreva nos comentários.",
        12: "Estamos na reta final. Deixe sua sugestão para o canal.",
    }

    for index, game in enumerate(games):
        start = _game_start(index)
        voice = primary if index % 2 == 0 else secondary
        segments.append(
            SpeechSegment(
                start + 0.35,
                voice,
                _normalize_loteca_speech(final.game_speech(game)),
                1.01,
                "-3%",
                "loteca_game",
            )
        )

        interaction = short_interactions.get(index + 1)
        if interaction:
            other = secondary if voice == primary else primary
            segments.append(
                SpeechSegment(
                    start + 5.75,
                    other,
                    _normalize_loteca_speech(interaction),
                    1.0,
                    "+2%",
                    "engagement",
                )
            )

    games_end = base.FULL_GAME_START + len(games) * FINAL_FULL_GAME_SLOT
    segments.extend(
        [
            SpeechSegment(
                games_end + 0.40,
                primary,
                "Os quatorze resultados já foram apresentados. Na tela, você confere agora o resumo completo do concurso.",
                1.0,
                "-3%",
                "summary",
            ),
            SpeechSegment(
                games_end + 13.00,
                secondary,
                "Para consultar este e outros resultados da Loteca, acesse portalsimonsports.com e abra a seção Loterias Caixa.",
                1.0,
                "-3%",
                "closing",
            ),
            SpeechSegment(
                games_end + 25.00,
                primary,
                "Se este conteúdo foi útil, deixe o seu like, compartilhe e inscreva-se no canal.",
                1.0,
                "-3%",
                "closing",
            ),
            SpeechSegment(
                games_end + 34.50,
                secondary,
                "E conte nos comentários que tipo de sugestão você gostaria de ver nas próximas publicações.",
                1.0,
                "-3%",
                "closing",
            ),
            SpeechSegment(
                games_end + 48.00,
                primary,
                "Portal Simon Sports, simplesmente o melhor.",
                1.0,
                "-4%",
                "closing",
            ),
        ]
    )

    return sorted(segments, key=lambda item: item.start)


def _short_segments_natural(
    data: Dict[str, Any], games: Sequence[LotecaGame], voice: str
) -> List[SpeechSegment]:
    segments = _BASE_FINAL_SHORT_SEGMENTS(data, games, voice)
    adjusted: List[SpeechSegment] = []
    closing_index = 0

    for segment in segments:
        text = _normalize_loteca_speech(segment.text)
        if segment.role == "opening":
            adjusted.append(replace(segment, text=text, rate="-5%"))
        elif segment.role == "loteca_game":
            adjusted.append(replace(segment, text=text, rate="-3%"))
        elif segment.role == "closing":
            closing_index += 1
            if closing_index == 2:
                adjusted.append(
                    replace(
                        segment,
                        text="Portal Simon Sports, simplesmente o melhor.",
                        rate="-4%",
                    )
                )
            else:
                adjusted.append(replace(segment, text=text, rate="-3%"))
        else:
            adjusted.append(replace(segment, text=text))

    return sorted(adjusted, key=lambda item: item.start)


def gerar_pacote_loteca(data: Dict[str, Any]) -> Dict[str, str]:
    original_duration = base.FULL_DURATION
    original_slot = base.FULL_GAME_SLOT
    original_full_builder = final._full_segments
    original_short_builder = final._short_segments

    install_visual_aprovado()
    base.FULL_DURATION = FINAL_FULL_DURATION
    base.FULL_GAME_SLOT = FINAL_FULL_GAME_SLOT
    final._full_segments = _full_segments_natural
    final._short_segments = _short_segments_natural
    try:
        package = final.gerar_pacote_loteca(data)
        package["modo_apresentacao"] = (
            "Loteca final com visual aprovado, intervalo reduzido, pronúncia revisada e sugestões"
        )
        return package
    finally:
        base.FULL_DURATION = original_duration
        base.FULL_GAME_SLOT = original_slot
        final._full_segments = original_full_builder
        final._short_segments = original_short_builder


__all__ = [
    "FINAL_FULL_DURATION",
    "FINAL_FULL_GAME_SLOT",
    "_full_segments_natural",
    "_game_start",
    "_normalize_loteca_speech",
    "_short_segments_natural",
    "gerar_pacote_loteca",
]
