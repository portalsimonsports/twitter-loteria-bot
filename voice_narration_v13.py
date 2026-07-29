from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import edge_tts


VOICE_FRANCISCA = "pt-BR-FranciscaNeural"
VOICE_THALITA = "pt-BR-ThalitaMultilingualNeural"
VOICE_ANTONIO = "pt-BR-AntonioNeural"
VOICE_CYCLE = (VOICE_FRANCISCA, VOICE_THALITA, VOICE_ANTONIO)

VOICE_LABELS = {
    VOICE_FRANCISCA: "Francisca",
    VOICE_THALITA: "Thalita",
    VOICE_ANTONIO: "Antônio",
}

VOICE_SETTINGS = {
    VOICE_FRANCISCA: {"rate": "-4%", "pitch": "+0Hz", "volume": "+0%"},
    VOICE_THALITA: {"rate": "-3%", "pitch": "+0Hz", "volume": "+0%"},
    VOICE_ANTONIO: {"rate": "-4%", "pitch": "-1Hz", "volume": "+0%"},
}

ORDINALS = (
    "primeira", "segunda", "terceira", "quarta", "quinta", "sexta", "sétima",
    "oitava", "nona", "décima", "décima primeira", "décima segunda",
    "décima terceira", "décima quarta", "décima quinta", "décima sexta",
    "décima sétima", "décima oitava", "décima nona", "vigésima",
)


@dataclass(frozen=True)
class SpeechSegment:
    start: float
    voice: str
    text: str
    gain: float = 1.0


def _run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Falha no áudio narrado V13: {process.stderr[-6000:]}")


def _slug(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.translate(str.maketrans("áàãâéêíóôõúç", "aaaaeeiooouc"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def extract_numbers(data: Dict[str, Any]) -> List[str]:
    raw = data.get("numeros") or data.get("descricao") or data.get("Descrição") or ""
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return re.findall(r"\d{1,3}", str(raw))


def select_voice(data: Dict[str, Any]) -> str:
    """Escolhe uma única voz por resultado e alterna nos concursos seguintes."""
    contest = str(data.get("concurso") or "").strip()
    digits = re.sub(r"\D+", "", contest)
    if digits:
        index = int(digits) % len(VOICE_CYCLE)
    else:
        seed = "|".join(
            str(data.get(key) or "").strip()
            for key in ("loteria", "produto", "data", "data_sorteio")
        )
        index = zlib.crc32(seed.encode("utf-8")) % len(VOICE_CYCLE)
    return VOICE_CYCLE[index]


def voice_label(voice: str) -> str:
    return VOICE_LABELS.get(voice, voice)


def reveal_times_full(
    lottery: str,
    count: int,
    intro_duration: float = 38.0,
    result_duration: float = 76.0,
) -> List[float]:
    if count <= 0:
        return []
    key = _slug(lottery)
    if "dupla-sena" in key and count >= 12:
        source = [7.60 + index * 3.15 for index in range(6)]
        source += [29.00 + index * 3.15 for index in range(6)]
        if count > 12:
            source.extend(47.0 + (index + 1) * 0.65 for index in range(count - 12))
    else:
        start = 7.60
        end = 40.0 if count <= 6 else 44.0 if count <= 10 else 46.0 if count <= 15 else 47.0
        if count == 1:
            source = [start]
        else:
            interval = (end - start) / (count - 1)
            source = [start + index * interval for index in range(count)]
    ratio = result_duration / 47.0
    return [intro_duration + max(0.0, value - 7.0) * ratio for value in source[:count]]


def reveal_times_short(
    lottery: str,
    count: int,
    intro_duration: float = 5.4,
    result_duration: float = 18.1,
) -> List[float]:
    if count <= 0:
        return []
    key = _slug(lottery)
    if "dupla-sena" in key and count >= 12:
        source = [7.60 + index * 3.15 for index in range(6)]
        source += [29.00 + index * 3.15 for index in range(6)]
        if count > 12:
            source.extend(47.0 + (index + 1) * 0.65 for index in range(count - 12))
    else:
        start = 7.60
        end = 40.0 if count <= 6 else 44.0 if count <= 10 else 46.0 if count <= 15 else 47.0
        if count == 1:
            source = [start]
        else:
            interval = (end - start) / (count - 1)
            source = [start + index * interval for index in range(count)]
    ratio = result_duration / 47.0
    return [intro_duration + max(0.0, value - 7.0) * ratio for value in source[:count]]


def _opening_segments(data: Dict[str, Any], voice: str, compact: bool) -> List[SpeechSegment]:
    lottery = str(data.get("loteria") or data.get("produto") or "loteria").strip()
    contest = str(data.get("concurso") or "").strip()
    date_text = str(data.get("data") or data.get("data_sorteio") or "").strip()
    contest_text = f", concurso {contest}" if contest else ""
    date_part = f", realizado em {date_text}" if date_text else ""

    if compact:
        return [
            SpeechSegment(
                0.20,
                voice,
                f"Portal SimonSports. Resultado da {lottery}{contest_text}. Confira agora.",
                1.03,
            )
        ]

    texts = [
        "Olá! Seja muito bem-vindo ao Portal SimonSports. Está começando mais uma edição do nosso boletim completo de resultados das Loterias da Caixa.",
        f"Hoje vamos apresentar o resultado oficial da {lottery}{contest_text}{date_part}, com todos os números exibidos na tela para facilitar a sua conferência.",
        "Acompanhe até o final, porque depois da leitura das dezenas nós repetiremos o resultado completo e deixaremos as principais informações desta edição.",
        "Antes de começar, deixe o seu like, inscreva-se no canal e ative as notificações. Esse apoio ajuda o SimonSports a continuar publicando resultados rápidos, organizados e confiáveis.",
    ]
    starts = (0.35, 9.50, 19.10, 28.55)
    return [SpeechSegment(start, voice, text) for start, text in zip(starts, texts)]


def _ordinal(index: int) -> str:
    if 0 <= index < len(ORDINALS):
        return ORDINALS[index]
    return f"número {index + 1}"


def _number_phrase(index: int, value: str, lottery: str, count: int) -> str:
    number = value.lstrip("0") or "zero"
    key = _slug(lottery)

    if "dupla-sena" in key and count >= 12:
        if index == 0:
            return f"Primeiro sorteio. Primeira dezena: {number}."
        if index == 6:
            return f"Segundo sorteio. Primeira dezena: {number}."
        local_index = index if index < 6 else index - 6
        return f"{_ordinal(local_index).capitalize()} dezena: {number}."

    if index == 0:
        return f"Primeira dezena sorteada: {number}."
    if index == count - 1:
        return f"Última dezena sorteada: {number}."
    return f"{_ordinal(index).capitalize()} dezena: {number}."


def _number_segments(
    numbers: List[str],
    lottery: str,
    reveals: List[float],
    voice: str,
    compact: bool,
) -> List[SpeechSegment]:
    segments: List[SpeechSegment] = []
    for index, (number, reveal) in enumerate(zip(numbers, reveals)):
        if compact:
            text = (number.lstrip("0") or "zero") + "."
            start = max(5.15, reveal - 0.14)
        else:
            text = _number_phrase(index, number, lottery, len(numbers))
            start = max(0.0, reveal - 0.42)
        segments.append(SpeechSegment(start, voice, text, 1.03 if compact else 1.0))
    return segments


def _closing_segments(
    data: Dict[str, Any],
    duration: float,
    last_reveal: float,
    voice: str,
    compact: bool,
) -> List[SpeechSegment]:
    lottery = str(data.get("loteria") or data.get("produto") or "loteria").strip()

    if compact:
        return [
            SpeechSegment(24.10, voice, "Gostou? Deixe seu like e comente.", 1.03),
            SpeechSegment(27.05, voice, "Inscreva-se no SimonSports.", 1.03),
        ]

    start = max(last_reveal + 4.0, duration - 36.0)
    texts = [
        f"Esses foram os números sorteados da {lottery}. O resultado completo permanece na tela para que você possa fazer uma nova conferência com tranquilidade.",
        "Conte para a gente nos comentários: você acertou alguma dezena, chegou perto do prêmio ou está acompanhando apenas para consultar o resultado?",
        "Compartilhe este vídeo com familiares e amigos que também acompanham as loterias. E não se esqueça de deixar o seu like, porque ele ajuda o conteúdo a alcançar mais pessoas.",
        "Inscreva-se no canal, ative as notificações e acompanhe as próximas edições. Portal SimonSports, simplesmente o melhor. Obrigado pela audiência e até o próximo resultado!",
    ]
    starts = (start, start + 9.0, start + 18.0, start + 27.0)
    return [SpeechSegment(segment_start, voice, text) for segment_start, text in zip(starts, texts)]


def build_segments(
    data: Dict[str, Any],
    duration: float,
    reveals: Iterable[float],
    compact: bool = False,
    voice: str | None = None,
) -> List[SpeechSegment]:
    selected_voice = voice or select_voice(data)
    numbers = extract_numbers(data)
    reveal_list = list(reveals)
    lottery = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    first_reveal = reveal_list[0] if reveal_list else (5.4 if compact else 38.0)
    last_reveal = reveal_list[-1] if reveal_list else first_reveal
    return (
        _opening_segments(data, selected_voice, compact)
        + _number_segments(numbers, lottery, reveal_list, selected_voice, compact)
        + _closing_segments(data, duration, last_reveal, selected_voice, compact)
    )


async def _synthesize_one(segment: SpeechSegment, output: Path) -> None:
    settings = VOICE_SETTINGS[segment.voice]
    communicator = edge_tts.Communicate(
        text=segment.text,
        voice=segment.voice,
        rate=settings["rate"],
        pitch=settings["pitch"],
        volume=settings["volume"],
    )
    await communicator.save(str(output))


async def _synthesize_all(segments: List[SpeechSegment], directory: Path) -> List[Path]:
    outputs: List[Path] = []
    for index, segment in enumerate(segments):
        output = directory / f"fala_{index:02d}.mp3"
        await _synthesize_one(segment, output)
        outputs.append(output)
    return outputs


def synthesize_narration_mix(
    data: Dict[str, Any],
    duration: float,
    reveals: Iterable[float],
    music_path: Path,
    output_path: Path,
    *,
    compact: bool = False,
    voice: str | None = None,
) -> Path:
    selected_voice = voice or select_voice(data)
    segments = build_segments(data, duration, reveals, compact=compact, voice=selected_voice)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not segments:
        raise RuntimeError("A locução V13 não encontrou segmentos para sintetizar.")

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-voz-v13-") as temporary:
        temp_dir = Path(temporary)
        try:
            clips = asyncio.run(_synthesize_all(segments, temp_dir))
        except Exception as exc:
            raise RuntimeError(
                f"Não foi possível gerar a voz neural {voice_label(selected_voice)}. "
                "A publicação foi interrompida para não usar voz robótica de contingência."
            ) from exc

        command: List[str] = ["ffmpeg", "-y", "-i", str(music_path)]
        for clip in clips:
            command.extend(["-i", str(clip)])

        filters: List[str] = ["[0:a]volume=0.14,highpass=f=45,lowpass=f=14500[music]"]
        labels = ["[music]"]
        for index, (segment, _clip) in enumerate(zip(segments, clips), start=1):
            delay_ms = max(0, round(segment.start * 1000))
            label = f"voice{index}"
            filters.append(
                f"[{index}:a]adelay={delay_ms}|{delay_ms},volume={segment.gain:.3f},"
                f"highpass=f=80,lowpass=f=15000[{label}]"
            )
            labels.append(f"[{label}]")

        filters.append(
            "".join(labels)
            + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0,"
              "alimiter=limit=0.94,loudnorm=I=-15.5:TP=-1.2:LRA=9,"
            + f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[aout]"
        )
        command.extend([
            "-filter_complex", ";".join(filters),
            "-map", "[aout]",
            "-c:a", "pcm_s16le",
            "-ar", "48000",
            "-ac", "2",
            "-t", f"{duration:.3f}",
            str(output_path),
        ])
        _run(command)

    print(
        f"[VOZ V13] {voice_label(selected_voice)} | segmentos={len(segments)} | "
        f"modo={'Short' if compact else 'completo'}",
        flush=True,
    )
    return output_path


__all__ = [
    "VOICE_ANTONIO",
    "VOICE_FRANCISCA",
    "VOICE_THALITA",
    "extract_numbers",
    "reveal_times_full",
    "reveal_times_short",
    "select_voice",
    "synthesize_narration_mix",
    "voice_label",
]
