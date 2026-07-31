from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import loteca_columns_v18 as final
import loteca_video_v18 as base
from loteca_visual_aprovado_v18 import install_visual_aprovado
from lottery_result_v18 import LotecaGame
from voice_narration_v18 import SpeechSegment


# Ritmo aprovado para o vídeo completo:
# - resultado simples: bloco de 9 s (fala natural + cerca de 3 s de respiro);
# - resultado seguido de interação: bloco de 13 s, preservando a chamada sem
#   acelerar o apresentador nem invadir o próximo jogo.
FINAL_FULL_STANDARD_SLOT = 9.0
FINAL_FULL_INTERACTION_SLOT = 13.0
FINAL_FULL_GAME_SLOT = FINAL_FULL_STANDARD_SLOT  # compatibilidade
INTERACTION_AFTER_GAMES = (4, 8, 12)
FINAL_FULL_DURATION = 226.0
FULL_SPEECH_RATE = "-5%"
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


def _game_durations(count: int = 14) -> List[float]:
    return [
        FINAL_FULL_INTERACTION_SLOT if game_number in INTERACTION_AFTER_GAMES
        else FINAL_FULL_STANDARD_SLOT
        for game_number in range(1, count + 1)
    ]


def _game_starts(count: int = 14) -> List[float]:
    starts: List[float] = []
    current = base.FULL_GAME_START
    for duration in _game_durations(count):
        starts.append(current)
        current += duration
    return starts


def _game_start(index: int) -> float:
    starts = _game_starts(max(14, index + 1))
    return starts[index]


def _games_end(count: int = 14) -> float:
    return base.FULL_GAME_START + sum(_game_durations(count))


def _full_segments_natural(
    data: Dict[str, Any], games: Sequence[LotecaGame], pair: Tuple[str, str]
) -> List[SpeechSegment]:
    primary, secondary = pair
    contest = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or "").strip()

    # Toda a abertura usa a mesma velocidade. Os textos foram encurtados para
    # caberem naturalmente antes do primeiro jogo, sem atempo automático.
    segments: List[SpeechSegment] = [
        SpeechSegment(
            0.35,
            primary,
            "Olá! Seja muito bem-vindo ao Portal Simon Sports, simplesmente o melhor.",
            1.0,
            FULL_SPEECH_RATE,
            "opening",
        ),
        SpeechSegment(
            7.40,
            secondary,
            _normalize_loteca_speech(
                "Hoje vamos conferir o resultado da Loteca"
                + (f", concurso {contest}" if contest else "")
                + (f", divulgado em {date}." if date else ".")
            ),
            1.0,
            FULL_SPEECH_RATE,
            "opening",
        ),
        SpeechSegment(
            15.00,
            primary,
            "Na Loteca, coluna um é mandante, empate é resultado igual e coluna dois é visitante.",
            1.0,
            FULL_SPEECH_RATE,
            "opening",
        ),
        SpeechSegment(
            23.00,
            secondary,
            _normalize_loteca_speech("Separe o comprovante. Vamos aos resultados dos jogos."),
            1.0,
            FULL_SPEECH_RATE,
            "opening",
        ),
    ]

    interactions = {
        4: "Primeira parte concluída. Gostou? Deixe seu like e conte nos comentários.",
        8: "Chegamos à metade. Compartilhe o vídeo e deixe sua sugestão para o canal.",
        12: "Estamos na reta final. Inscreva-se e acompanhe os próximos resultados.",
    }

    starts = _game_starts(len(games))
    for index, (game, start) in enumerate(zip(games, starts)):
        voice = primary if index % 2 == 0 else secondary
        segments.append(
            SpeechSegment(
                start + 0.35,
                voice,
                _normalize_loteca_speech(final.game_speech(game)),
                1.01,
                FULL_SPEECH_RATE,
                "loteca_game",
            )
        )

        interaction = interactions.get(index + 1)
        if interaction:
            other = secondary if voice == primary else primary
            segments.append(
                SpeechSegment(
                    start + 7.00,
                    other,
                    _normalize_loteca_speech(interaction),
                    1.0,
                    FULL_SPEECH_RATE,
                    "engagement",
                )
            )

    games_end = _games_end(len(games))
    closing_start = games_end + 24.0
    segments.extend(
        [
            SpeechSegment(
                games_end + 0.40,
                primary,
                "Os quatorze resultados já foram apresentados. Confira agora o primeiro resumo do concurso.",
                1.0,
                FULL_SPEECH_RATE,
                "summary",
            ),
            SpeechSegment(
                games_end + 12.40,
                secondary,
                "No segundo resumo, revise os demais jogos com calma. Se gostou, deixe o seu like.",
                1.0,
                FULL_SPEECH_RATE,
                "summary",
            ),
            SpeechSegment(
                closing_start + 0.50,
                primary,
                "Para consultar outros resultados da Loteca, acesse portalsimonsports.com e abra Loterias Caixa.",
                1.0,
                FULL_SPEECH_RATE,
                "closing",
            ),
            SpeechSegment(
                closing_start + 11.00,
                secondary,
                "Compartilhe, inscreva-se e conte nos comentários quais conteúdos você quer ver no canal.",
                1.0,
                FULL_SPEECH_RATE,
                "closing",
            ),
            SpeechSegment(
                closing_start + 24.00,
                primary,
                "Portal Simon Sports, simplesmente o melhor.",
                1.0,
                FULL_SPEECH_RATE,
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
    original_concat_writer = base._write_concat_video
    original_soundtrack_writer = base.write_soundtrack

    def write_concat_dynamic(images, audio, output, duration, temp):
        adjusted = list(images)
        output_name = Path(output).name
        if output_name.startswith("video_completo_loteca_"):
            durations = _game_durations(14)
            expected_minimum = 1 + len(durations) + 3
            if len(adjusted) < expected_minimum:
                raise RuntimeError(
                    f"Linha do tempo da Loteca incompleta: {len(adjusted)} cenas."
                )
            for index, scene_duration in enumerate(durations, start=1):
                image, _old_duration = adjusted[index]
                adjusted[index] = (image, scene_duration)
        return original_concat_writer(adjusted, audio, output, duration, temp)

    def write_soundtrack_dynamic(path, duration, lottery_name, contest, result_time, cta_time):
        if abs(float(duration) - FINAL_FULL_DURATION) < 0.01:
            games_end = _games_end(14)
            result_time = games_end
            cta_time = games_end + 24.0
        return original_soundtrack_writer(
            path, duration, lottery_name, contest, result_time, cta_time
        )

    install_visual_aprovado()
    base.FULL_DURATION = FINAL_FULL_DURATION
    base.FULL_GAME_SLOT = FINAL_FULL_STANDARD_SLOT
    base._write_concat_video = write_concat_dynamic
    base.write_soundtrack = write_soundtrack_dynamic
    final._full_segments = _full_segments_natural
    final._short_segments = _short_segments_natural
    try:
        package = final.gerar_pacote_loteca(data)
        package["modo_apresentacao"] = (
            "Loteca final com ritmo variável, voz constante, visual e pronúncia aprovados"
        )
        return package
    finally:
        base.FULL_DURATION = original_duration
        base.FULL_GAME_SLOT = original_slot
        base._write_concat_video = original_concat_writer
        base.write_soundtrack = original_soundtrack_writer
        final._full_segments = original_full_builder
        final._short_segments = original_short_builder


__all__ = [
    "FINAL_FULL_DURATION",
    "FINAL_FULL_GAME_SLOT",
    "FINAL_FULL_INTERACTION_SLOT",
    "FINAL_FULL_STANDARD_SLOT",
    "FULL_SPEECH_RATE",
    "INTERACTION_AFTER_GAMES",
    "_full_segments_natural",
    "_game_durations",
    "_game_start",
    "_game_starts",
    "_games_end",
    "_normalize_loteca_speech",
    "_short_segments_natural",
    "gerar_pacote_loteca",
]
