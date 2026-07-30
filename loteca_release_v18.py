from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Dict, List, Sequence, Tuple

import loteca_columns_v18 as final
import loteca_video_v18 as base
from loteca_visual_aprovado_v18 import install_visual_aprovado
from lottery_result_v18 import LotecaGame
from voice_narration_v18 import SpeechSegment


FINAL_FULL_DURATION = 298.0
FINAL_FULL_GAME_SLOT = 15.0
_BASE_FINAL_FULL_SEGMENTS = final._full_segments
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


def _full_segments_natural(
    data: Dict[str, Any], games: Sequence[LotecaGame], pair: Tuple[str, str]
) -> List[SpeechSegment]:
    primary, secondary = pair
    contest = str(data.get("concurso") or "").strip()
    date = str(data.get("data") or "").strip()

    base_segments = _BASE_FINAL_FULL_SEGMENTS(data, games, pair)

    openings = [
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

    engagement_texts = iter(
        (
            "Aproveite e deixe nos comentários que tipo de sugestão você gostaria de ver aqui no canal.",
            "Comente também quais conteúdos você gostaria de acompanhar nas próximas publicações.",
            "Estamos na reta final. Deixe sugestões de vídeos e conteúdos para o canal.",
        )
    )
    closing_texts = iter(
        (
            "Para consultar este e outros resultados da Loteca, acesse portalsimonsports.com e abra a seção Loterias Caixa.",
            "Se este conteúdo foi útil, deixe o seu like, compartilhe e inscreva-se no canal.",
            "E conte nos comentários que tipo de sugestão você gostaria de ver nas próximas publicações.",
            "Portal Simon Sports, simplesmente o melhor.",
        )
    )
    closing_starts = iter((264.50, 275.00, 284.00, 292.00))

    adjusted: List[SpeechSegment] = []
    for segment in base_segments:
        if segment.role == "opening":
            continue
        if segment.role == "loteca_game":
            adjusted.append(replace(segment, text=_normalize_loteca_speech(segment.text)))
        elif segment.role == "engagement":
            adjusted.append(
                replace(
                    segment,
                    text=_normalize_loteca_speech(next(engagement_texts)),
                    rate="-4%",
                )
            )
        elif segment.role == "summary":
            adjusted.append(
                replace(
                    segment,
                    start=241.00,
                    text=_normalize_loteca_speech(segment.text),
                    rate="-3%",
                )
            )
        elif segment.role == "closing":
            adjusted.append(
                replace(
                    segment,
                    start=next(closing_starts),
                    text=_normalize_loteca_speech(next(closing_texts)),
                    rate="-4%",
                )
            )
        else:
            adjusted.append(replace(segment, text=_normalize_loteca_speech(segment.text)))

    return sorted(openings + adjusted, key=lambda item: item.start)


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
            "Loteca final com visual aprovado, pronúncia revisada, abertura natural e sugestões"
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
    "_normalize_loteca_speech",
    "_short_segments_natural",
    "gerar_pacote_loteca",
]
