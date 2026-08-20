from __future__ import annotations

"""Patch do vídeo diário V19: abertura com CTA de inscrição/notificações.

É importado pelo workflow antes da geração do pacote. Mantém o motor V19 intacto
mas amplia a cena inicial e injeta a locução aprovada sem sobrepor os resultados.
"""

import daily_video_v19 as daily

_ORIGINAL_SYNTHESIZE = daily.synthesize_custom_segments

# Dá espaço suficiente para a assinatura atual + chamada de inscrição.
daily.FULL_INTRO_DURATION = 15.0

CTA_TEXT = (
    "Inscreva-se no canal e ative o sino das notificações para receber em primeira mão "
    "as atualizações das Loterias Caixa assim que os resultados oficiais forem confirmados."
)


def _synthesize_with_cta(data, duration, segments, music_path, output_path, *, primary_voice=None, **kwargs):
    prepared = list(segments or [])
    has_opening = any(str(getattr(seg, "role", "") or "").lower() == "opening" for seg in prepared)
    already = any("ative o sino" in str(getattr(seg, "text", "") or "").lower() for seg in prepared)

    if has_opening and not already:
        voice = primary_voice or (prepared[0].voice if prepared else daily.select_single_voice(data))
        prepared.append(
            daily.SpeechSegment(
                5.1,
                voice,
                CTA_TEXT,
                1.0,
                daily.FULL_RATE,
                "subscribe_notifications",
            )
        )
        prepared.sort(key=lambda item: float(getattr(item, "start", 0.0)))

    return _ORIGINAL_SYNTHESIZE(
        data,
        duration,
        prepared,
        music_path,
        output_path,
        primary_voice=primary_voice,
        **kwargs,
    )


daily.synthesize_custom_segments = _synthesize_with_cta
