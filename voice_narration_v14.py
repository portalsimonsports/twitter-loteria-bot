from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
import zlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

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
    VOICE_FRANCISCA: {"rate": "-2%", "pitch": "+0Hz", "volume": "+0%"},
    VOICE_THALITA: {"rate": "-1%", "pitch": "+0Hz", "volume": "+0%"},
    VOICE_ANTONIO: {"rate": "-2%", "pitch": "-1Hz", "volume": "+0%"},
}


@dataclass(frozen=True)
class SpeechSegment:
    start: float
    voice: str
    text: str
    gain: float = 1.0
    rate: str | None = None
    role: str = "speech"


def _run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Falha no áudio narrado V14: {process.stderr[-6000:]}")


def _slug(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.translate(str.maketrans("áàãâéêíóôõúç", "aaaaeeiooouc"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def extract_numbers(data: Dict[str, Any]) -> List[str]:
    raw = data.get("numeros") or data.get("descricao") or data.get("Descrição") or ""
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return re.findall(r"\d{1,5}", str(raw))


def select_voice(data: Dict[str, Any]) -> str:
    """Escolhe uma voz única por resultado e alterna nos concursos seguintes."""
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
    intro_duration: float = 45.0,
    result_duration: float = 78.0,
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
                f"Portal SimonSports. Resultado da {lottery}{contest_text}. Confira as dezenas sorteadas.",
                1.03,
                "+5%",
                "opening",
            )
        ]

    texts = [
        "Olá! Seja muito bem-vindo ao Portal SimonSports. Está começando mais uma edição do nosso boletim completo de resultados das Loterias da Caixa.",
        f"Nesta edição, você acompanha o resultado oficial da {lottery}{contest_text}{date_part}, apresentado de forma clara e organizada para facilitar a sua conferência.",
        "Em poucos instantes, as dezenas aparecerão na tela e serão anunciadas com pausas naturais. Depois, o resultado completo continuará disponível para uma segunda conferência.",
        "Aproveite este momento para deixar o seu like, inscrever-se no canal e ativar as notificações. Assim, você acompanha os próximos resultados publicados pelo SimonSports.",
    ]
    starts = (0.35, 10.80, 21.40, 32.10)
    return [
        SpeechSegment(start, voice, text, 1.0, None, "opening")
        for start, text in zip(starts, texts)
    ]


def _number_segments(
    numbers: List[str],
    lottery: str,
    reveals: List[float],
    voice: str,
    compact: bool,
) -> List[SpeechSegment]:
    if not numbers or not reveals:
        return []

    key = _slug(lottery)
    segments: List[SpeechSegment] = []
    lead = 1.80 if compact else 3.70
    number_rate = "+10%" if compact else "+2%"
    gap_gain = 1.04 if compact else 1.02

    if "dupla-sena" in key and len(numbers) >= 12 and len(reveals) >= 12:
        segments.append(
            SpeechSegment(
                max(0.0, reveals[0] - lead),
                voice,
                "Confira as dezenas sorteadas no primeiro sorteio.",
                1.0,
                "+3%" if compact else None,
                "numbers_intro",
            )
        )
        for number, reveal in zip(numbers[:6], reveals[:6]):
            segments.append(
                SpeechSegment(reveal, voice, f"{number.lstrip('0') or 'zero'}.", gap_gain, number_rate, "number")
            )
        segments.append(
            SpeechSegment(
                max(reveals[5] + 1.0, reveals[6] - lead),
                voice,
                "Agora, confira as dezenas sorteadas no segundo sorteio.",
                1.0,
                "+3%" if compact else None,
                "numbers_intro",
            )
        )
        for number, reveal in zip(numbers[6:], reveals[6:]):
            segments.append(
                SpeechSegment(reveal, voice, f"{number.lstrip('0') or 'zero'}.", gap_gain, number_rate, "number")
            )
    else:
        segments.append(
            SpeechSegment(
                max(0.0, reveals[0] - lead),
                voice,
                "Confira as dezenas sorteadas.",
                1.0,
                "+3%" if compact else None,
                "numbers_intro",
            )
        )
        for number, reveal in zip(numbers, reveals):
            segments.append(
                SpeechSegment(reveal, voice, f"{number.lstrip('0') or 'zero'}.", gap_gain, number_rate, "number")
            )

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
            SpeechSegment(
                24.15,
                voice,
                "Gostou do conteúdo? Deixe o seu like, comente e inscreva-se no SimonSports.",
                1.03,
                "+8%",
                "closing",
            )
        ]

    start = max(last_reveal + 4.0, duration - 42.0)
    texts = [
        f"Essas foram as dezenas sorteadas da {lottery}. O resultado completo permanece na tela para que você possa conferir novamente com tranquilidade.",
        "Agora queremos saber de você: acertou alguma dezena, chegou perto do prêmio ou utiliza o SimonSports apenas para acompanhar os resultados? Conte nos comentários.",
        "Compartilhe este vídeo com familiares e amigos que também acompanham as loterias. O seu like ajuda este conteúdo informativo a alcançar mais pessoas.",
        "Inscreva-se no canal, ative as notificações e acompanhe as próximas edições. Portal SimonSports, simplesmente o melhor. Obrigado pela audiência e até o próximo resultado!",
    ]
    starts = (start, start + 10.30, start + 20.60, start + 31.00)
    return [
        SpeechSegment(segment_start, voice, text, 1.0, None, "closing")
        for segment_start, text in zip(starts, texts)
    ]


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
    last_reveal = reveal_list[-1] if reveal_list else (23.0 if compact else 120.0)
    segments = (
        _opening_segments(data, selected_voice, compact)
        + _number_segments(numbers, lottery, reveal_list, selected_voice, compact)
        + _closing_segments(data, duration, last_reveal, selected_voice, compact)
    )
    return sorted(segments, key=lambda segment: segment.start)


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
        raise RuntimeError(f"Não foi possível medir a duração de {path.name}: {process.stderr[-1000:]}")
    return max(0.05, float(process.stdout.strip()))


def _resolve_non_overlapping_schedule(
    segments: List[SpeechSegment],
    clips: List[Path],
    duration: float,
    compact: bool,
) -> Tuple[List[SpeechSegment], List[float]]:
    """Reposiciona cada fala após o término real da anterior.

    A duração é medida depois da síntese, portanto nenhuma voz começa enquanto a
    fala anterior ainda está tocando. Esse controle elimina a sobreposição que
    reduzia a qualidade da locução.
    """
    clip_durations = [_clip_duration(path) for path in clips]
    gap = 0.10 if compact else 0.42
    cursor = 0.0
    resolved: List[SpeechSegment] = []

    for segment, clip_duration in zip(segments, clip_durations):
        start = max(segment.start, cursor)
        end = start + clip_duration
        if end > duration - 0.08:
            raise RuntimeError(
                f"A locução {voice_label(segment.voice)} ultrapassaria a duração do vídeo "
                f"({end:.2f}s de {duration:.2f}s). Ajuste de segurança interrompeu a geração."
            )
        resolved.append(replace(segment, start=start))
        cursor = end + gap

    return resolved, clip_durations


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
        raise RuntimeError("A locução V14 não encontrou segmentos para sintetizar.")

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-voz-v14-") as temporary:
        temp_dir = Path(temporary)
        try:
            clips = asyncio.run(_synthesize_all(segments, temp_dir))
            segments, clip_durations = _resolve_non_overlapping_schedule(
                segments,
                clips,
                duration,
                compact,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Não foi possível gerar a voz neural {voice_label(selected_voice)} sem sobreposição. "
                "A publicação foi interrompida para preservar a qualidade do vídeo."
            ) from exc

        command: List[str] = ["ffmpeg", "-y", "-i", str(music_path)]
        for clip in clips:
            command.extend(["-i", str(clip)])

        filters: List[str] = ["[0:a]volume=0.105,highpass=f=45,lowpass=f=14500[music]"]
        labels = ["[music]"]
        for index, (segment, _clip, clip_duration) in enumerate(
            zip(segments, clips, clip_durations),
            start=1,
        ):
            delay_ms = max(0, round(segment.start * 1000))
            label = f"voice{index}"
            filters.append(
                f"[{index}:a]atrim=duration={clip_duration:.3f},asetpts=PTS-STARTPTS,"
                f"adelay={delay_ms}|{delay_ms},volume={segment.gain:.3f},"
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
        f"[VOZ V14] {voice_label(selected_voice)} | segmentos={len(segments)} | "
        f"sem sobreposição | modo={'Short' if compact else 'completo'}",
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
