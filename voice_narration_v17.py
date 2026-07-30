from __future__ import annotations

import re
import zlib
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import voice_narration_v15 as v15


VOICE_FRANCISCA = v15.VOICE_FRANCISCA
VOICE_THALITA_MULTILINGUAL = v15.VOICE_THALITA
VOICE_ANTONIO = v15.VOICE_ANTONIO
VOICE_THALITA_NEURAL = "pt-BR-ThalitaNeural"

v15.VOICE_SETTINGS.setdefault(
    VOICE_THALITA_NEURAL,
    {"rate": "-1%", "pitch": "+0Hz", "volume": "+0%"},
)

# Nomes públicos exibidos nos vídeos, capas e chamadas.
# Os identificadores técnicos das vozes permanecem distintos internamente.
VOICE_LABELS = {
    VOICE_FRANCISCA: "Francisca",
    VOICE_THALITA_MULTILINGUAL: "Thalita",
    VOICE_ANTONIO: "Antônio",
    VOICE_THALITA_NEURAL: "Thalita",
}

TECHNICAL_VOICE_LABELS = {
    VOICE_FRANCISCA: "Francisca Neural",
    VOICE_THALITA_MULTILINGUAL: "Thalita Multilingual Neural",
    VOICE_ANTONIO: "Antônio Neural",
    VOICE_THALITA_NEURAL: "Thalita Neural",
}

ALL_VOICES: Tuple[str, ...] = (
    VOICE_FRANCISCA,
    VOICE_THALITA_MULTILINGUAL,
    VOICE_ANTONIO,
    VOICE_THALITA_NEURAL,
)

PAIR_CYCLE: Tuple[Tuple[str, str], ...] = (
    (VOICE_FRANCISCA, VOICE_ANTONIO),
    (VOICE_THALITA_MULTILINGUAL, VOICE_ANTONIO),
    (VOICE_FRANCISCA, VOICE_THALITA_NEURAL),
    (VOICE_ANTONIO, VOICE_THALITA_NEURAL),
    (VOICE_FRANCISCA, VOICE_THALITA_MULTILINGUAL),
)

extract_numbers = v15.extract_numbers
reveal_times_full = v15.reveal_times_full
reveal_times_short = v15.reveal_times_short
SpeechSegment = v15.SpeechSegment
_BASE_SYNTHESIZE = v15.synthesize_narration_mix


def voice_label(voice: str) -> str:
    """Nome público curto usado no vídeo."""
    return VOICE_LABELS.get(voice, v15.voice_label(voice).split()[0])


def technical_voice_label(voice: str) -> str:
    """Nome técnico reservado a logs e diagnóstico."""
    return TECHNICAL_VOICE_LABELS.get(voice, str(voice or "Voz"))


def _seed(data: Dict[str, Any]) -> int:
    contest = re.sub(r"\D+", "", str(data.get("concurso") or ""))
    if contest:
        return int(contest)
    raw = "|".join(
        str(data.get(key) or "").strip()
        for key in ("loteria", "produto", "data", "data_sorteio")
    )
    return zlib.crc32(raw.encode("utf-8"))


def select_single_voice(data: Dict[str, Any]) -> str:
    return ALL_VOICES[_seed(data) % len(ALL_VOICES)]


def select_presenter_pair(data: Dict[str, Any]) -> Tuple[str, str]:
    return PAIR_CYCLE[_seed(data) % len(PAIR_CYCLE)]


def pair_label(pair: Sequence[str]) -> str:
    """Rótulo público com apenas os primeiros nomes."""
    return " e ".join(voice_label(voice) for voice in pair)


def technical_pair_label(pair: Sequence[str]) -> str:
    return " e ".join(technical_voice_label(voice) for voice in pair)


def _slug(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.translate(str.maketrans("áàãâéêíóôõúç", "aaaaeeiooouc"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _spoken_number(value: str) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if not digits:
        return str(value or "").strip()
    return digits.lstrip("0") or "zero"


def _visual_offset(reveals: List[float], compact: bool) -> float:
    positive_gaps = [b - a for a, b in zip(reveals, reveals[1:]) if b > a]
    smallest_gap = min(positive_gaps) if positive_gaps else (1.0 if compact else 3.2)
    if compact:
        return min(0.62, max(0.38, smallest_gap * 0.62))
    return min(2.35, max(1.15, smallest_gap * 0.62))


def _opening_segments(data: Dict[str, Any], primary: str, secondary: str | None, compact: bool) -> List[SpeechSegment]:
    lottery = str(data.get("loteria") or data.get("produto") or "loteria").strip()
    contest = str(data.get("concurso") or "").strip()
    date_text = str(data.get("data") or data.get("data_sorteio") or "").strip()
    contest_text = f", concurso {contest}" if contest else ""
    date_part = f", sorteado em {date_text}" if date_text else ""

    if compact:
        return [SpeechSegment(0.20, primary, f"Portal SimonSports. Resultado da {lottery}{contest_text}.", 1.03, "+8%", "opening")]

    second = secondary or primary
    return [
        SpeechSegment(0.35, primary, "Olá! Seja muito bem-vindo ao Portal SimonSports. Está começando mais uma edição do nosso boletim de resultados das Loterias da Caixa.", 1.0, None, "opening"),
        SpeechSegment(9.60, second, f"E nesta edição, nós vamos conferir juntos o resultado oficial da {lottery}{contest_text}{date_part}.", 1.0, None, "opening"),
        SpeechSegment(18.80, primary, "Chegou a hora de descobrir se a sorte esteve ao seu lado. Tenha o seu comprovante em mãos e acompanhe cada dezena.", 1.0, None, "opening"),
        SpeechSegment(28.10, second, "Enquanto você se prepara, deixe o seu like, inscreva-se no canal e ative as notificações para acompanhar os próximos resultados.", 1.0, None, "opening"),
        SpeechSegment(39.00, primary, "Tudo pronto? Então vamos ao resultado.", 1.02, "+2%", "opening"),
    ]


def _number_segments(data: Dict[str, Any], numbers: List[str], reveals: List[float], primary: str, secondary: str | None, compact: bool) -> List[SpeechSegment]:
    if not numbers or not reveals:
        return []

    lottery = str(data.get("loteria") or data.get("produto") or "loteria").strip()
    key = _slug(lottery)
    second = secondary or primary
    offset = _visual_offset(reveals, compact)
    number_starts = [value + offset for value in reveals]
    lead = 1.55 if compact else 3.00
    intro_rate = "+8%" if compact else "+2%"
    number_rate = "+13%" if compact else "+3%"
    number_gain = 1.04 if compact else 1.02
    segments: List[SpeechSegment] = []

    if "dupla-sena" in key and len(numbers) >= 12 and len(number_starts) >= 12:
        first_voice = primary
        second_voice = second
        segments.append(SpeechSegment(max(0.0, number_starts[0] - lead), first_voice, "Confira agora as dezenas do primeiro sorteio.", 1.0, intro_rate, "numbers_intro"))
        for number, start in zip(numbers[:6], number_starts[:6]):
            segments.append(SpeechSegment(start, first_voice, f"{_spoken_number(number)}.", number_gain, number_rate, "number"))

        if secondary and not compact:
            interaction_start = number_starts[5] + 1.00
            segments.append(SpeechSegment(interaction_start, second_voice, "E até aqui, como está a sua conferência? Alguma dezena já apareceu no seu jogo?", 1.0, "+7%", "engagement"))
            second_intro_start = max(interaction_start + 4.20, number_starts[6] - lead)
        else:
            second_intro_start = max(number_starts[5] + 0.55, number_starts[6] - lead)

        segments.append(SpeechSegment(second_intro_start, second_voice, "E agora, confira as dezenas do segundo sorteio.", 1.0, intro_rate, "numbers_intro"))
        for number, start in zip(numbers[6:], number_starts[6:]):
            segments.append(SpeechSegment(start, second_voice, f"{_spoken_number(number)}.", number_gain, number_rate, "number"))
        return segments

    numbers_voice = second if secondary else primary
    segments.append(SpeechSegment(max(0.0, number_starts[0] - lead), numbers_voice, "Confira agora as dezenas sorteadas.", 1.0, intro_rate, "numbers_intro"))

    interaction_after = -1
    interaction_start = 0.0
    if secondary and not compact and 6 <= len(number_starts) <= 10:
        candidate = (len(number_starts) - 1) // 2
        if candidate + 1 < len(number_starts):
            gap = number_starts[candidate + 1] - number_starts[candidate]
            if gap >= 5.80:
                interaction_after = candidate
                interaction_start = number_starts[candidate] + 0.90

    for index, (number, start) in enumerate(zip(numbers, number_starts)):
        segments.append(SpeechSegment(start, numbers_voice, f"{_spoken_number(number)}.", number_gain, number_rate, "number"))
        if index == interaction_after:
            segments.append(SpeechSegment(interaction_start, primary, "E aí, como está a sua conferência até aqui? Alguma dezena já apareceu no seu jogo?", 1.0, "+8%", "engagement"))
    return segments


def _closing_segments(data: Dict[str, Any], duration: float, last_number_start: float, primary: str, secondary: str | None, compact: bool) -> List[SpeechSegment]:
    lottery = str(data.get("loteria") or data.get("produto") or "loteria").strip()
    if compact:
        return [SpeechSegment(24.05, primary, "Deixe o seu like, comente e inscreva-se no SimonSports.", 1.03, "+15%", "closing")]

    second = secondary or primary
    start = max(last_number_start + 4.0, duration - 42.0)
    return [
        SpeechSegment(start, primary, f"Resultado conferido. Essas foram as dezenas sorteadas da {lottery}.", 1.0, None, "closing"),
        SpeechSegment(start + 6.20, second, "E aí, alguma dezena apareceu no seu jogo? Conte nos comentários como foi a sua conferência.", 1.0, None, "closing"),
        SpeechSegment(start + 13.20, primary, f"Para consultar outros resultados da {lottery}, acesse portalsimonsports.com e abra a seção Loterias Caixa.", 1.0, "+2%", "closing"),
        SpeechSegment(start + 22.80, second, "Compartilhe este vídeo com familiares e amigos que também acompanham as loterias. O seu like ajuda o canal a alcançar mais pessoas.", 1.0, None, "closing"),
        SpeechSegment(start + 32.00, primary, "Inscreva-se, ative as notificações e acompanhe as próximas edições aqui no Portal SimonSports.", 1.0, None, "closing"),
        SpeechSegment(start + 38.20, second, "SimonSports, simplesmente o melhor. Obrigado pela audiência e até o próximo resultado!", 1.0, "+3%", "closing"),
    ]


def build_segments(data: Dict[str, Any], duration: float, reveals: Iterable[float], *, compact: bool, primary_voice: str, secondary_voice: str | None = None) -> List[SpeechSegment]:
    reveal_list = list(reveals)
    numbers = extract_numbers(data)
    offset = _visual_offset(reveal_list, compact)
    last_number_start = (reveal_list[-1] + offset) if reveal_list else (23.0 if compact else duration - 46.0)
    segments = [
        *_opening_segments(data, primary_voice, secondary_voice, compact),
        *_number_segments(data, numbers, reveal_list, primary_voice, secondary_voice, compact),
        *_closing_segments(data, duration, last_number_start, primary_voice, secondary_voice, compact),
    ]
    return sorted(segments, key=lambda item: item.start)


def _synthesize_with_builder(data: Dict[str, Any], duration: float, reveals: Iterable[float], music_path, output_path, *, compact: bool, primary_voice: str, secondary_voice: str | None):
    reveal_list = list(reveals)
    original_builder = v15.build_segments

    def custom_builder(_data, _duration, _reveals, compact=False, voice=None):
        return build_segments(_data, _duration, list(_reveals), compact=compact, primary_voice=primary_voice, secondary_voice=secondary_voice)

    v15.build_segments = custom_builder
    try:
        return _BASE_SYNTHESIZE(data, duration, reveal_list, music_path, output_path, compact=compact, voice=primary_voice)
    finally:
        v15.build_segments = original_builder


def synthesize_single_mix(data: Dict[str, Any], duration: float, reveals: Iterable[float], music_path, output_path, *, compact: bool, voice: str | None = None):
    selected = voice or select_single_voice(data)
    return _synthesize_with_builder(data, duration, reveals, music_path, output_path, compact=compact, primary_voice=selected, secondary_voice=None)


def synthesize_dialogue_mix(data: Dict[str, Any], duration: float, reveals: Iterable[float], music_path, output_path, *, pair: Tuple[str, str] | None = None):
    primary, secondary = pair or select_presenter_pair(data)
    return _synthesize_with_builder(data, duration, reveals, music_path, output_path, compact=False, primary_voice=primary, secondary_voice=secondary)


__all__ = [
    "ALL_VOICES",
    "VOICE_ANTONIO",
    "VOICE_FRANCISCA",
    "VOICE_THALITA_MULTILINGUAL",
    "VOICE_THALITA_NEURAL",
    "build_segments",
    "extract_numbers",
    "pair_label",
    "reveal_times_full",
    "reveal_times_short",
    "select_presenter_pair",
    "select_single_voice",
    "synthesize_dialogue_mix",
    "synthesize_single_mix",
    "technical_pair_label",
    "technical_voice_label",
    "voice_label",
]
