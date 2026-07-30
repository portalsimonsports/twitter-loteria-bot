from __future__ import annotations

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


def _full_segments_natural(
    data: Dict[str, Any], games: Sequence[LotecaGame], pair: Tuple[str, str]
) -> List[SpeechSegment]:
    segments = _BASE_FINAL_FULL_SEGMENTS(data, games, pair)

    engagement_texts = iter(
        (
            "Aproveite e deixe nos comentários que tipo de sugestão você gostaria de ver aqui no canal.",
            "Comente também quais conteúdos você gostaria de acompanhar nas próximas publicações.",
            "Estamos na reta final. Deixe sugestões de vídeos e conteúdos para o canal.",
        )
    )
    closing_starts = iter((264.50, 275.00, 284.00, 292.50))

    adjusted: List[SpeechSegment] = []
    for segment in segments:
        if segment.role == "engagement":
            adjusted.append(
                replace(
                    segment,
                    text=next(engagement_texts),
                    rate="-4%",
                )
            )
        elif segment.role == "summary":
            adjusted.append(replace(segment, start=241.00, rate="-3%"))
        elif segment.role == "closing":
            adjusted.append(
                replace(segment, start=next(closing_starts), rate="-3%")
            )
        else:
            adjusted.append(segment)

    return sorted(adjusted, key=lambda item: item.start)


def gerar_pacote_loteca(data: Dict[str, Any]) -> Dict[str, str]:
    original_duration = base.FULL_DURATION
    original_slot = base.FULL_GAME_SLOT
    original_builder = final._full_segments

    install_visual_aprovado()
    base.FULL_DURATION = FINAL_FULL_DURATION
    base.FULL_GAME_SLOT = FINAL_FULL_GAME_SLOT
    final._full_segments = _full_segments_natural
    try:
        package = final.gerar_pacote_loteca(data)
        package["modo_apresentacao"] = (
            "Loteca final com alinhamento aprovado, destaques por resultado, locução natural e sugestões"
        )
        return package
    finally:
        base.FULL_DURATION = original_duration
        base.FULL_GAME_SLOT = original_slot
        final._full_segments = original_builder


__all__ = [
    "FINAL_FULL_DURATION",
    "FINAL_FULL_GAME_SLOT",
    "gerar_pacote_loteca",
]
