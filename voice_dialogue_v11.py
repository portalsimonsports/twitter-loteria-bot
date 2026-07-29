from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import edge_tts


VOICE_FRANCISCA = "pt-BR-FranciscaNeural"
VOICE_THALITA = "pt-BR-ThalitaMultilingualNeural"
VOICE_ANTONIO = "pt-BR-AntonioNeural"
VOICE_CYCLE = (VOICE_FRANCISCA, VOICE_ANTONIO, VOICE_THALITA)

VOICE_SETTINGS = {
    VOICE_FRANCISCA: {"rate": "-4%", "pitch": "+0Hz", "volume": "+0%"},
    VOICE_THALITA: {"rate": "-3%", "pitch": "+0Hz", "volume": "+0%"},
    VOICE_ANTONIO: {"rate": "-4%", "pitch": "-1Hz", "volume": "+0%"},
}


@dataclass(frozen=True)
class SpeechSegment:
    start: float
    voice: str
    text: str
    gain: float = 1.0


def _run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Falha no áudio narrado V11: {process.stderr[-6000:]}")


def _slug(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.translate(str.maketrans("áàãâéêíóôõúç", "aaaaeeiooouc"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def extract_numbers(data: Dict[str, Any]) -> List[str]:
    raw = data.get("numeros") or data.get("descricao") or data.get("Descrição") or ""
    if isinstance(raw, (list, tuple)):
        values = [str(item).strip() for item in raw if str(item).strip()]
    else:
        values = re.findall(r"\d{1,3}", str(raw))
    return values


def reveal_times_full(
    lottery: str,
    count: int,
    intro_duration: float = 25.0,
    result_duration: float = 71.0,
) -> List[float]:
    if count <= 0:
        return []
    key = _slug(lottery)
    if "dupla-sena" in key and count >= 12:
        base = [7.60 + index * 3.15 for index in range(6)] + [29.00 + index * 3.15 for index in range(6)]
        if count > 12:
            base.extend(47.0 + (index + 1) * 0.65 for index in range(count - 12))
        source_start = 7.0
        ratio = result_duration / 47.0
        return [intro_duration + max(0.0, value - source_start) * ratio for value in base[:count]]
    start = 7.60
    end = 40.0 if count <= 6 else 44.0 if count <= 10 else 46.0 if count <= 15 else 47.0
    if count == 1:
        return [intro_duration + max(0.0, start - 7.0) * (result_duration / 47.0)]
    interval = (end - start) / (count - 1)
    ratio = result_duration / 47.0
    return [intro_duration + max(0.0, (start + index * interval) - 7.0) * ratio for index in range(count)]


def reveal_times_short(lottery: str, count: int, intro_duration: float = 5.4, result_duration: float = 18.1) -> List[float]:
    if count <= 0:
        return []
    key = _slug(lottery)
    if "dupla-sena" in key and count >= 12:
        base = [7.60 + index * 3.15 for index in range(6)] + [29.00 + index * 3.15 for index in range(6)]
        if count > 12:
            base.extend(47.0 + (index + 1) * 0.65 for index in range(count - 12))
    else:
        start = 7.60
        end = 40.0 if count <= 6 else 44.0 if count <= 10 else 46.0 if count <= 15 else 47.0
        if count == 1:
            base = [start]
        else:
            interval = (end - start) / (count - 1)
            base = [start + index * interval for index in range(count)]
    source_start = 7.0
    ratio = result_duration / 47.0
    return [intro_duration + max(0.0, value - source_start) * ratio for value in base[:count]]


def _opening_segments(data: Dict[str, Any], first_reveal: float, compact: bool) -> List[SpeechSegment]:
    lottery = str(data.get("loteria") or data.get("produto") or "loteria").strip()
    contest = str(data.get("concurso") or "").strip()
    date_text = str(data.get("data") or "").strip()
    contest_text = f", concurso {contest}" if contest else ""
    date_part = f", realizado em {date_text}" if date_text else ""

    if compact:
        texts = [
            (VOICE_FRANCISCA, f"Portal SimonSports. Resultado da {lottery}{contest_text}."),
            (VOICE_ANTONIO, "Confira as dezenas e deixe o seu like."),
        ]
        starts = [0.20, 3.05]
        return [SpeechSegment(start, voice, text) for start, (voice, text) in zip(starts, texts)]

    texts = [
        (
            VOICE_FRANCISCA,
            f"Olá! Seja muito bem-vindo ao Portal SimonSports. Está começando o nosso boletim completo com o resultado oficial da {lottery}{contest_text}{date_part}.",
        ),
        (
            VOICE_ANTONIO,
            "Em instantes, vamos apresentar cada número sorteado, com calma e clareza, para você acompanhar e conferir o seu jogo.",
        ),
        (
            VOICE_THALITA,
            "Antes de começarmos, aproveite para deixar o seu like, inscrever-se no canal e ativar as notificações. Assim você recebe os próximos resultados publicados pelo SimonSports.",
        ),
    ]
    starts = [0.35, 7.45, 14.55]
    return [SpeechSegment(start, voice, text) for start, (voice, text) in zip(starts, texts)]


def _number_phrase(index: int, value: str, lottery: str, count: int) -> str:
    number = value.lstrip("0") or "zero"
    key = _slug(lottery)
    if "dupla-sena" in key and count >= 12:
        if index == 0:
            return f"Primeiro sorteio. A primeira dezena foi {number}."
        if index == 6:
            return f"Agora, o segundo sorteio. A primeira dezena foi {number}."
        position = index + 1 if index < 6 else index - 5
        return f"{position}ª dezena: {number}."
    if index == 0:
        return f"A primeira dezena sorteada foi {number}."
    if index == count - 1:
        return f"E a última dezena sorteada foi {number}."
    return f"Na sequência, {number}."


def _number_segments(numbers: List[str], lottery: str, reveals: List[float], compact: bool) -> List[SpeechSegment]:
    segments: List[SpeechSegment] = []
    for index, (number, reveal) in enumerate(zip(numbers, reveals)):
        voice = VOICE_CYCLE[index % len(VOICE_CYCLE)]
        if compact:
            text = (number.lstrip("0") or "zero") + "."
            start = max(5.15, reveal - 0.14)
        else:
            text = _number_phrase(index, number, lottery, len(numbers))
            start = max(0.0, reveal - 0.42)
        segments.append(SpeechSegment(start, voice, text, 1.03 if compact else 1.0))
    return segments


def _closing_segments(data: Dict[str, Any], duration: float, last_reveal: float, compact: bool) -> List[SpeechSegment]:
    lottery = str(data.get("loteria") or data.get("produto") or "loteria").strip()
    if compact:
        return [
            SpeechSegment(23.45, VOICE_THALITA, "Gostou? Deixe seu like e comente."),
            SpeechSegment(26.35, VOICE_ANTONIO, "Inscreva-se no SimonSports para receber os próximos resultados."),
        ]

    start = max(last_reveal + 4.0, duration - 24.0)
    return [
        SpeechSegment(start, VOICE_FRANCISCA, f"Esses foram os números sorteados da {lottery}. Confira novamente o resultado exibido na tela antes de finalizar a sua conferência."),
        SpeechSegment(start + 7.4, VOICE_ANTONIO, "Agora queremos saber de você: acertou alguma dezena? Escreva nos comentários e compartilhe este vídeo com quem também acompanha as loterias."),
        SpeechSegment(start + 15.3, VOICE_THALITA, "Deixe o seu like, inscreva-se no canal e ative as notificações. Portal SimonSports, simplesmente o melhor. Até o próximo resultado!"),
    ]


def build_segments(data: Dict[str, Any], duration: float, reveals: Iterable[float], compact: bool = False) -> List[SpeechSegment]:
    numbers = extract_numbers(data)
    reveal_list = list(reveals)
    lottery = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    first_reveal = reveal_list[0] if reveal_list else (5.4 if compact else 13.0)
    last_reveal = reveal_list[-1] if reveal_list else first_reveal
    return (
        _opening_segments(data, first_reveal, compact)
        + _number_segments(numbers, lottery, reveal_list, compact)
        + _closing_segments(data, duration, last_reveal, compact)
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


def synthesize_dialogue_mix(
    data: Dict[str, Any],
    duration: float,
    reveals: Iterable[float],
    music_path: Path,
    output_path: Path,
    *,
    compact: bool = False,
) -> Path:
    segments = build_segments(data, duration, reveals, compact=compact)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not segments:
        raise RuntimeError("A locução V11 não encontrou segmentos para sintetizar.")

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-vozes-v11-") as temporary:
        temp_dir = Path(temporary)
        try:
            clips = asyncio.run(_synthesize_all(segments, temp_dir))
        except Exception as exc:
            raise RuntimeError(
                "Não foi possível gerar as vozes neurais Francisca, Thalita e Antônio. "
                "A publicação foi interrompida para não usar voz robótica de contingência."
            ) from exc

        command: List[str] = ["ffmpeg", "-y", "-i", str(music_path)]
        for clip in clips:
            command.extend(["-i", str(clip)])

        filters: List[str] = ["[0:a]volume=0.16,highpass=f=45,lowpass=f=14500[music]"]
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
        f"[VOZES V11] Francisca + Antônio + Thalita | segmentos={len(segments)} | "
        f"modo={'Short' if compact else 'completo'}",
        flush=True,
    )
    return output_path


__all__ = [
    "VOICE_ANTONIO",
    "VOICE_FRANCISCA",
    "VOICE_THALITA",
    "build_segments",
    "extract_numbers",
    "reveal_times_full",
    "reveal_times_short",
    "synthesize_dialogue_mix",
]
