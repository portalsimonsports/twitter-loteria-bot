from __future__ import annotations

import asyncio
import hashlib
import math
import os
import shutil
import subprocess
import wave
from array import array
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

RATE = 44100
MOTIF = ((0.00, 0), (0.22, 4), (0.44, 7), (0.66, 12))


def variation_for(loteria: str, concurso: str) -> int:
    digits = "".join(c for c in str(concurso or "") if c.isdigit())
    if digits:
        return int(digits) % 4
    return hashlib.sha256(f"{loteria}|{concurso}".encode()).digest()[0] % 4


def _midi(note: float) -> float:
    return 440.0 * 2.0 ** ((note - 69.0) / 12.0)


def _pulse(phase: float, decay: float) -> float:
    phase %= 1.0
    return math.exp(-phase * decay) * min(1.0, phase * 34.0)


def _bell(t: float, start: float, note: float, amp: float) -> float:
    dt = t - start
    if not 0.0 <= dt < 1.15:
        return 0.0
    f = _midi(note)
    env = (1.0 - math.exp(-dt * 48.0)) * math.exp(-dt * 4.8)
    return amp * env * (
        math.sin(2 * math.pi * f * dt)
        + 0.48 * math.sin(2 * math.pi * f * 2.01 * dt + 0.18)
        + 0.22 * math.sin(2 * math.pi * f * 3.02 * dt + 0.43)
    )


def _signature(t: float, start: float) -> Tuple[float, float]:
    left = right = 0.0
    for index, (offset, interval) in enumerate(MOTIF):
        value = _bell(t, start + offset, 72 + interval, 0.135 if index == 3 else 0.105)
        pan = -0.34 + index * 0.23
        left += value * (1.0 - pan * 0.42)
        right += value * (1.0 + pan * 0.42)
    dt = t - start
    if 0.0 <= dt < 0.75:
        impact = (
            math.sin(2 * math.pi * 58 * dt) + 0.34 * math.sin(2 * math.pi * 116 * dt)
        ) * 0.075 * math.exp(-dt * 7.5)
        left += impact
        right += impact
    return left, right


def write_soundtrack(
    path: str | Path,
    duration: float,
    loteria: str,
    concurso: str,
    result_time: float,
    cta_time: float,
) -> int:
    variation = variation_for(loteria, concurso)
    styles = (
        (118.0, 43, 0.017, 0.082, 0.052, 0.011, 0.028),
        (110.0, 46, 0.025, 0.070, 0.036, 0.007, 0.022),
        (126.0, 48, 0.014, 0.078, 0.062, 0.014, 0.030),
        (122.0, 41, 0.020, 0.087, 0.044, 0.010, 0.034),
    )
    progressions = (
        ((0, (0, 3, 7)), (-4, (0, 4, 7)), (3, (0, 4, 7)), (-2, (0, 4, 7))),
        ((0, (0, 4, 7)), (5, (0, 3, 7)), (-3, (0, 4, 7)), (2, (0, 3, 7))),
        ((0, (0, 3, 7)), (3, (0, 4, 7)), (-2, (0, 4, 7)), (5, (0, 3, 7))),
        ((0, (0, 4, 7)), (-5, (0, 3, 7)), (2, (0, 4, 7)), (-3, (0, 4, 7))),
    )
    bpm, root_base, pad_amp, bass_amp, arp_amp, hat_amp, snare_amp = styles[variation]
    beat = 60.0 / bpm
    bar = beat * 4.0
    pcm = array("h")

    for sample in range(max(1, int(duration * RATE))):
        t = sample / RATE
        fade = min(1.0, t / 0.55) * min(1.0, max(0.0, duration - t) / 1.10)
        beat_index = int(t / beat)
        beat_phase = (t / beat) % 1.0
        half_phase = (t / (beat / 2.0)) % 1.0
        quarter_phase = (t / (beat / 4.0)) % 1.0
        shift, intervals = progressions[variation][int(t / bar) % 4]
        root = root_base + shift
        notes = [root + interval for interval in intervals]
        energy = 0.78 + 0.22 * min(1.0, t / max(1.0, result_time)) + (0.12 if t >= result_time else 0.0)

        left_pad = right_pad = 0.0
        for index, note in enumerate(notes):
            f = _midi(note + 12)
            phase = index * 0.47 + variation * 0.12
            tone = math.sin(2 * math.pi * f * t + phase) + 0.31 * math.sin(2 * math.pi * f * 2 * t + phase * 1.6)
            if variation == 1:
                tone += 0.18 * math.sin(2 * math.pi * f * 0.5 * t + phase)
            pan = -0.46 + index * 0.46
            left_pad += tone * (1.0 - pan * 0.35)
            right_pad += tone * (1.0 + pan * 0.35)
        lfo = 0.82 + 0.18 * math.sin(2 * math.pi * (0.08 + variation * 0.01) * t)
        left_pad *= pad_amp * lfo
        right_pad *= pad_amp * lfo

        bass_f = _midi(root - 12)
        bass = (
            math.sin(2 * math.pi * bass_f * t) + 0.26 * math.sin(2 * math.pi * bass_f * 2 * t)
        ) * bass_amp * _pulse(beat_phase, 4.2 if variation == 1 else 5.2)

        kick_phase = beat_phase
        kick = math.sin(2 * math.pi * (56 - 22 * min(1.0, kick_phase * 4)) * kick_phase * beat)
        kick *= 0.18 * math.exp(-kick_phase * 18)

        subdivision = beat / (4.0 if variation == 2 else 2.0)
        step = int(t / subdivision)
        arp_note = notes[step % len(notes)] + (12 if step % 4 in (2, 3) else 0)
        arp_f = _midi(arp_note + 12)
        arp_phase = (t / subdivision) % 1.0
        arp = (
            math.sin(2 * math.pi * arp_f * t) + 0.22 * math.sin(2 * math.pi * arp_f * 2 * t)
        ) * arp_amp * _pulse(arp_phase, 9.0 if variation == 2 else 7.8)
        arp_pan = -0.42 if step % 2 == 0 else 0.42

        hat_f = 6800 + variation * 520
        noise = (
            math.sin(2 * math.pi * hat_f * t)
            + 0.52 * math.sin(2 * math.pi * (hat_f + 1730) * t + 0.7)
            + 0.31 * math.sin(2 * math.pi * (hat_f + 3510) * t + 1.4)
        )
        hat = noise * hat_amp * _pulse(quarter_phase if variation == 2 else half_phase, 24)

        snare = 0.0
        if beat_index % 4 in ((3,) if variation == 1 else (1, 3)):
            snare_noise = (
                math.sin(2 * math.pi * 1780 * t)
                + 0.70 * math.sin(2 * math.pi * 2460 * t + 0.8)
                + 0.42 * math.sin(2 * math.pi * 3380 * t + 1.5)
            )
            snare = snare_noise * snare_amp * math.exp(-beat_phase * 17)

        transition = 0.0
        for target in (result_time, cta_time):
            distance = target - t
            if 0.0 < distance < 1.35:
                amount = 1.0 - distance / 1.35
                transition += math.sin(2 * math.pi * (220 + 900 * amount * amount) * t) * 0.020 * amount

        sig_l, sig_r = _signature(t, 0.14)
        out_l, out_r = _signature(t, cta_time + 0.05)
        left = (left_pad + bass + kick + arp * (1 - arp_pan * 0.55) + hat + snare + transition + sig_l + out_l) * energy * fade
        right = (right_pad + bass + kick + arp * (1 + arp_pan * 0.55) + hat + snare + transition + sig_r + out_r) * energy * fade
        pcm.append(int(math.tanh(left * 1.55) * 0.76 * 32767))
        pcm.append(int(math.tanh(right * 1.55) * 0.76 * 32767))

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(RATE)
        audio.writeframes(pcm.tobytes())
    return variation


def _texts(data: Dict[str, Any]) -> Tuple[str, str]:
    loteria = str(data.get("loteria") or data.get("produto") or "loteria").strip()
    concurso = str(data.get("concurso") or "").strip()
    suffix = f", concurso {concurso}" if concurso else ""
    return (
        f"Portal SimonSports apresenta. Resultado oficial da {loteria}{suffix}.",
        "Portal SimonSports. Informação em movimento.",
    )


async def _edge(text: str, output: Path, voice: str) -> None:
    import edge_tts  # type: ignore
    await edge_tts.Communicate(
        text, voice,
        rate=os.getenv("VOICEOVER_RATE", "-4%"),
        volume=os.getenv("VOICEOVER_VOLUME", "+0%"),
        pitch=os.getenv("VOICEOVER_PITCH", "-2Hz"),
    ).save(str(output))


def _run_async(coro) -> None:
    try:
        asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()


def _espeak(text: str, output: Path) -> bool:
    executable = shutil.which("espeak-ng") or shutil.which("espeak")
    if not executable:
        return False
    result = subprocess.run(
        [executable, "-v", "pt-br", "-s", "150", "-p", "42", "-a", "165", "-w", str(output), text],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    return result.returncode == 0 and output.exists() and output.stat().st_size > 256


def voice_assets(directory: str | Path, data: Dict[str, Any]) -> Tuple[Optional[Path], Optional[Path], str]:
    if os.getenv("ENABLE_VOICEOVER", "true").strip().lower() in {"0", "false", "off", "nao", "não"}:
        return None, None, "desativada"
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    intro_text, outro_text = _texts(data)
    voice = os.getenv("VOICEOVER_VOICE", "pt-BR-AntonioNeural")
    intro_mp3, outro_mp3 = folder / "intro.mp3", folder / "outro.mp3"
    try:
        _run_async(_edge(intro_text, intro_mp3, voice))
        _run_async(_edge(outro_text, outro_mp3, voice))
        if intro_mp3.stat().st_size > 256 and outro_mp3.stat().st_size > 256:
            return intro_mp3, outro_mp3, f"neural:{voice}"
    except Exception as exc:
        print(f"[ÁUDIO V8] Voz neural indisponível: {exc}", flush=True)

    intro_wav, outro_wav = folder / "intro.wav", folder / "outro.wav"
    if _espeak(intro_text, intro_wav) and _espeak(outro_text, outro_wav):
        return intro_wav, outro_wav, "offline:espeak-ng"
    return None, None, "indisponível"
