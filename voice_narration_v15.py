from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import edge_tts

from voice_narration_v14 import (
    VOICE_ANTONIO,
    VOICE_FRANCISCA,
    VOICE_SETTINGS,
    VOICE_THALITA,
    extract_numbers,
    reveal_times_full,
    reveal_times_short,
    select_voice,
    voice_label,
)


@dataclass(frozen=True)
class SpeechSegment:
    start: float
    voice: str
    text: str
    gain: float = 1.0
    rate: str | None = None
    role: str = "speech"


@dataclass(frozen=True)
class FittedSegment:
    segment: SpeechSegment
    clip: Path
    clip_duration: float
    available_duration: float
    speed: float


def _run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Falha no áudio narrado V15: {process.stderr[-7000:]}")


def _slug(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.translate(str.maketrans("áàãâéêíóôõúç", "aaaaeeiooouc"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _spoken_number(value: str) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if not digits:
        return str(value or "").strip()
    return digits.lstrip("0") or "zero"


def _opening_segment(data: Dict[str, Any], voice: str, compact: bool) -> SpeechSegment:
    lottery = str(data.get("loteria") or data.get("produto") or "loteria").strip()
    contest = str(data.get("concurso") or "").strip()
    date_text = str(data.get("data") or data.get("data_sorteio") or "").strip()
    contest_text = f", concurso {contest}" if contest else ""
    date_part = f", realizado em {date_text}" if date_text else ""

    if compact:
        text = f"Portal SimonSports. Resultado da {lottery}{contest_text}."
        return SpeechSegment(0.20, voice, text, 1.03, "+8%", "opening")

    text = (
        "Olá! Seja muito bem-vindo ao Portal SimonSports. Está começando mais uma edição "
        "do nosso boletim completo de resultados das Loterias da Caixa. "
        f"Nesta edição, você acompanha o resultado oficial da {lottery}{contest_text}{date_part}, "
        "apresentado de forma clara, organizada e confiável para facilitar a sua conferência. "
        "Acompanhe com atenção: as dezenas serão exibidas na tela e anunciadas uma a uma, "
        "sem pressa e sem informações sobrepostas. Ao final, o resultado completo permanecerá "
        "disponível para uma nova conferência. Aproveite para deixar o seu like, inscrever-se "
        "no canal e ativar as notificações para receber os próximos resultados do SimonSports."
    )
    return SpeechSegment(0.35, voice, text, 1.0, None, "opening")


def _number_segments(
    data: Dict[str, Any],
    numbers: List[str],
    reveals: List[float],
    voice: str,
    compact: bool,
) -> List[SpeechSegment]:
    if not numbers or not reveals:
        return []

    lottery = str(data.get("loteria") or data.get("produto") or "loteria").strip()
    key = _slug(lottery)
    lead = 1.65 if compact else 3.25
    number_rate = "+13%" if compact else "+3%"
    number_gain = 1.04 if compact else 1.02
    segments: List[SpeechSegment] = []

    if "dupla-sena" in key and len(numbers) >= 12 and len(reveals) >= 12:
        segments.append(
            SpeechSegment(
                max(0.0, reveals[0] - lead),
                voice,
                "Confira as dezenas sorteadas no primeiro sorteio.",
                1.0,
                "+8%" if compact else "+2%",
                "numbers_intro",
            )
        )
        for number, reveal in zip(numbers[:6], reveals[:6]):
            segments.append(
                SpeechSegment(reveal, voice, f"{_spoken_number(number)}.", number_gain, number_rate, "number")
            )

        segments.append(
            SpeechSegment(
                max(reveals[5] + 0.55, reveals[6] - lead),
                voice,
                "Agora, confira o segundo sorteio.",
                1.0,
                "+10%" if compact else "+3%",
                "numbers_intro",
            )
        )
        for number, reveal in zip(numbers[6:], reveals[6:]):
            segments.append(
                SpeechSegment(reveal, voice, f"{_spoken_number(number)}.", number_gain, number_rate, "number")
            )
        return segments

    segments.append(
        SpeechSegment(
            max(0.0, reveals[0] - lead),
            voice,
            "Confira agora as dezenas sorteadas.",
            1.0,
            "+8%" if compact else "+2%",
            "numbers_intro",
        )
    )
    for number, reveal in zip(numbers, reveals):
        segments.append(
            SpeechSegment(reveal, voice, f"{_spoken_number(number)}.", number_gain, number_rate, "number")
        )
    return segments


def _closing_segment(
    data: Dict[str, Any],
    duration: float,
    last_reveal: float,
    voice: str,
    compact: bool,
) -> SpeechSegment:
    lottery = str(data.get("loteria") or data.get("produto") or "loteria").strip()

    if compact:
        return SpeechSegment(
            24.05,
            voice,
            "Deixe o seu like, comente e inscreva-se no SimonSports.",
            1.03,
            "+15%",
            "closing",
        )

    start = max(last_reveal + 4.0, duration - 42.0)
    text = (
        f"Essas foram as dezenas sorteadas da {lottery}. O resultado completo permanece na tela "
        "para que você possa conferir novamente com tranquilidade. Agora queremos saber de você: "
        "acertou alguma dezena, chegou perto do prêmio ou utiliza o SimonSports para acompanhar "
        "os resultados? Conte nos comentários. Compartilhe este vídeo com familiares e amigos "
        "que também acompanham as loterias. O seu like ajuda este conteúdo informativo a alcançar "
        "mais pessoas. Inscreva-se no canal, ative as notificações e acompanhe as próximas edições. "
        "Portal SimonSports, simplesmente o melhor. Obrigado pela audiência e até o próximo resultado!"
    )
    return SpeechSegment(start, voice, text, 1.0, None, "closing")


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
    last_reveal = reveal_list[-1] if reveal_list else (23.0 if compact else duration - 46.0)
    segments = [
        _opening_segment(data, selected_voice, compact),
        *_number_segments(data, numbers, reveal_list, selected_voice, compact),
        _closing_segment(data, duration, last_reveal, selected_voice, compact),
    ]
    return sorted(segments, key=lambda item: item.start)


async def _synthesize_one(segment: SpeechSegment, output: Path) -> None:
    settings = VOICE_SETTINGS[segment.voice]
    communicator = edge_tts.Communicate(
        text=segment.text,
        voice=segment.voice,
        rate=segment.rate or settings["rate"],
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


def _clip_duration(path: Path) -> float:
    process = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.returncode != 0:
        raise RuntimeError(f"Não foi possível medir {path.name}: {process.stderr[-1200:]}")
    return max(0.05, float(process.stdout.strip()))


def _fit_segments(
    segments: List[SpeechSegment],
    clips: List[Path],
    duration: float,
    compact: bool,
) -> List[FittedSegment]:
    gap = 0.07 if compact else 0.22
    fitted: List[FittedSegment] = []

    for index, (segment, clip) in enumerate(zip(segments, clips)):
        clip_duration = _clip_duration(clip)
        next_start = segments[index + 1].start if index + 1 < len(segments) else duration
        available = max(0.12, next_start - segment.start - gap)
        speed = max(1.0, clip_duration / available)
        fitted.append(FittedSegment(segment, clip, clip_duration, available, speed))

    return fitted


def _atempo_chain(speed: float) -> str:
    factors: List[float] = []
    remaining = max(1.0, speed)
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    if remaining > 1.0005:
        factors.append(remaining)
    return ",".join(f"atempo={factor:.6f}" for factor in factors)


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
        raise RuntimeError("A locução V15 não encontrou conteúdo para sintetizar.")

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-voz-v15-") as temporary:
        temp_dir = Path(temporary)
        try:
            clips = asyncio.run(_synthesize_all(segments, temp_dir))
            fitted = _fit_segments(segments, clips, duration, compact)
        except Exception as exc:
            raise RuntimeError(
                f"Falha ao preparar a voz neural {voice_label(selected_voice)}: {exc}"
            ) from exc

        command: List[str] = ["ffmpeg", "-y", "-i", str(music_path)]
        for item in fitted:
            command.extend(["-i", str(item.clip)])

        filters: List[str] = ["[0:a]volume=0.10,highpass=f=45,lowpass=f=14500[music]"]
        labels = ["[music]"]

        for input_index, item in enumerate(fitted, start=1):
            delay_ms = max(0, round(item.segment.start * 1000))
            label = f"voice{input_index}"
            tempo = _atempo_chain(item.speed)
            tempo_filter = f",{tempo}" if tempo else ""
            filters.append(
                f"[{input_index}:a]atrim=start=0,asetpts=PTS-STARTPTS{tempo_filter},"
                f"aresample=48000,atrim=duration={item.available_duration:.3f},"
                f"volume={item.segment.gain:.3f},highpass=f=80,lowpass=f=15000,"
                f"adelay={delay_ms}|{delay_ms}[{label}]"
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

    max_speed = max((item.speed for item in fitted), default=1.0)
    print(
        f"[VOZ V15] {voice_label(selected_voice)} | sem sobreposição | "
        f"encaixe máximo={max_speed:.2f}x | modo={'Short' if compact else 'completo'}",
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
