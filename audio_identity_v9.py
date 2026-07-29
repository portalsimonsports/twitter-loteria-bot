from __future__ import annotations

import hashlib
import math
import wave
from array import array
from pathlib import Path

RATE = 44100


def variation_for(loteria: str, concurso: str) -> int:
    digits = "".join(c for c in str(concurso or "") if c.isdigit())
    if digits:
        return int(digits) % 4
    return hashlib.sha256(f"{loteria}|{concurso}".encode()).digest()[0] % 4


def _midi(note: float) -> float:
    return 440.0 * 2.0 ** ((note - 69.0) / 12.0)


def _env_exp(dt: float, attack: float, decay: float, length: float) -> float:
    if dt < 0.0 or dt >= length:
        return 0.0
    return (1.0 - math.exp(-dt * attack)) * math.exp(-dt * decay)


def _pulse(phase: float, decay: float = 7.0) -> float:
    phase %= 1.0
    return math.exp(-phase * decay) * min(1.0, phase * 36.0)


def _brand_signature(t: float, start: float) -> tuple[float, float]:
    """Assinatura fixa: impacto, whoosh e quatro notas ascendentes."""
    dt = t - start
    if dt < 0.0 or dt > 2.25:
        return 0.0, 0.0

    left = right = 0.0

    if dt < 0.85:
        sweep = 64.0 - 28.0 * min(1.0, dt / 0.45)
        impact_env = _env_exp(dt, 55.0, 6.5, 0.85)
        impact = (
            math.sin(2.0 * math.pi * sweep * dt)
            + 0.30 * math.sin(2.0 * math.pi * sweep * 2.0 * dt)
        ) * 0.19 * impact_env
        left += impact
        right += impact

    if dt < 1.25:
        amount = max(0.0, min(1.0, dt / 1.25))
        whoosh_env = math.sin(math.pi * amount) ** 1.45
        f1 = 180.0 + 1800.0 * amount * amount
        f2 = 310.0 + 2800.0 * amount * amount
        whoosh = (
            math.sin(2.0 * math.pi * f1 * dt)
            + 0.55 * math.sin(2.0 * math.pi * f2 * dt + 0.7)
            + 0.25 * math.sin(2.0 * math.pi * (f2 * 1.73) * dt + 1.4)
        ) * 0.028 * whoosh_env
        pan = math.sin(amount * math.pi * 1.5) * 0.42
        left += whoosh * (1.0 - pan)
        right += whoosh * (1.0 + pan)

    notes = (
        (0.42, 74, 0.105, -0.36),
        (0.69, 81, 0.105, 0.12),
        (0.96, 86, 0.125, 0.38),
        (1.28, 90, 0.090, 0.0),
    )
    for offset, note, amp, pan in notes:
        ndt = dt - offset
        env = _env_exp(ndt, 70.0, 4.2, 1.10)
        if env:
            freq = _midi(note)
            tone = (
                math.sin(2.0 * math.pi * freq * ndt)
                + 0.42 * math.sin(2.0 * math.pi * freq * 2.01 * ndt + 0.2)
                + 0.18 * math.sin(2.0 * math.pi * freq * 3.02 * ndt + 0.55)
            ) * amp * env
            left += tone * (1.0 - pan * 0.45)
            right += tone * (1.0 + pan * 0.45)

    return left, right


def _section_energy(t: float, result_time: float, cta_time: float) -> tuple[float, float, float, float]:
    """Intensidades de pad, bateria, arpejo e transição por seção."""
    if t < 2.2:
        return 0.40, 0.00, 0.00, 0.20
    if t < 7.0:
        p = (t - 2.2) / 4.8
        return 0.50 + 0.22 * p, 0.10 + 0.20 * p, 0.15 + 0.25 * p, 0.22 + 0.20 * p
    if t < 24.0:
        return 0.76, 0.72, 0.58, 0.18
    if t < 41.0:
        return 0.82, 0.86, 0.78, 0.22
    if t < result_time:
        p = (t - 41.0) / max(0.1, result_time - 41.0)
        return 0.88 + 0.10 * p, 0.95 + 0.10 * p, 0.88 + 0.12 * p, 0.35 + 0.35 * p
    if t < cta_time:
        return 0.96, 0.48, 0.62, 0.30
    return 0.72, 0.34, 0.40, 0.22


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
        (122.0, 43, ((0, 3, 7), (-4, 0, 7), (3, 7, 10), (-2, 2, 7))),
        (116.0, 46, ((0, 4, 7), (5, 9, 12), (-3, 0, 4), (2, 5, 9))),
        (126.0, 48, ((0, 3, 7), (3, 7, 10), (-2, 2, 7), (5, 8, 12))),
        (120.0, 41, ((0, 4, 7), (-5, -1, 4), (2, 5, 9), (-3, 0, 4))),
    )
    bpm, root_base, progression = styles[variation]
    beat = 60.0 / bpm
    bar = beat * 4.0
    pcm = array("h")

    for sample_index in range(max(1, int(duration * RATE))):
        t = sample_index / RATE
        fade = min(1.0, t / 0.35) * min(1.0, max(0.0, duration - t) / 1.10)
        pad_e, drum_e, arp_e, trans_e = _section_energy(t, result_time, cta_time)

        beat_index = int(t / beat)
        beat_phase = (t / beat) % 1.0
        half_phase = (t / (beat / 2.0)) % 1.0
        quarter_phase = (t / (beat / 4.0)) % 1.0
        bar_index = int(t / bar)
        chord = progression[bar_index % len(progression)]
        root = root_base + chord[0]
        notes = [root_base + n for n in chord]

        left_pad = right_pad = 0.0
        for idx, note in enumerate(notes):
            freq = _midi(note + 12)
            phase = idx * 0.51 + variation * 0.17
            tone = (
                math.sin(2.0 * math.pi * freq * t + phase)
                + 0.30 * math.sin(2.0 * math.pi * freq * 2.0 * t + phase * 1.7)
                + 0.10 * math.sin(2.0 * math.pi * freq * 0.5 * t + phase * 0.7)
            )
            pan = -0.48 + idx * 0.48
            left_pad += tone * (1.0 - pan * 0.34)
            right_pad += tone * (1.0 + pan * 0.34)
        lfo = 0.82 + 0.18 * math.sin(2.0 * math.pi * (0.075 + variation * 0.008) * t)
        left_pad *= 0.020 * pad_e * lfo
        right_pad *= 0.020 * pad_e * lfo

        bass_freq = _midi(root - 12)
        bass_env = _pulse(beat_phase, 4.8)
        bass = (
            math.sin(2.0 * math.pi * bass_freq * t)
            + 0.27 * math.sin(2.0 * math.pi * bass_freq * 2.0 * t)
        ) * 0.087 * drum_e * bass_env

        kick_env = math.exp(-beat_phase * 18.0)
        kick_freq = 58.0 - 23.0 * min(1.0, beat_phase * 4.5)
        kick = math.sin(2.0 * math.pi * kick_freq * (beat_phase * beat)) * 0.18 * drum_e * kick_env

        snare = 0.0
        if beat_index % 4 in (1, 3) and t >= 7.0:
            snare_noise = (
                math.sin(2.0 * math.pi * 1710.0 * t)
                + 0.70 * math.sin(2.0 * math.pi * 2480.0 * t + 0.8)
                + 0.42 * math.sin(2.0 * math.pi * 3390.0 * t + 1.5)
            )
            snare = snare_noise * 0.032 * drum_e * math.exp(-beat_phase * 17.0)

        hat_noise = (
            math.sin(2.0 * math.pi * (6400 + variation * 430) * t)
            + 0.53 * math.sin(2.0 * math.pi * (8250 + variation * 510) * t + 0.7)
            + 0.30 * math.sin(2.0 * math.pi * 10100.0 * t + 1.4)
        )
        hat_phase = quarter_phase if t >= 41.0 else half_phase
        hat = hat_noise * 0.013 * drum_e * _pulse(hat_phase, 25.0)

        subdivision = beat / (4.0 if t >= 24.0 else 2.0)
        step = int(t / subdivision)
        pattern = (0, 1, 2, 1, 0, 2, 1, 2) if variation % 2 == 0 else (0, 2, 1, 2, 0, 1, 2, 1)
        arp_note = notes[pattern[step % len(pattern)] % len(notes)] + (24 if t >= 41.0 and step % 4 == 3 else 12)
        arp_freq = _midi(arp_note)
        arp_phase = (t / subdivision) % 1.0
        arp = (
            math.sin(2.0 * math.pi * arp_freq * t)
            + 0.22 * math.sin(2.0 * math.pi * arp_freq * 2.0 * t)
        ) * 0.061 * arp_e * _pulse(arp_phase, 8.8)
        arp_pan = -0.46 if step % 2 == 0 else 0.46

        transition = 0.0
        for target in (7.0, 24.0, 41.0, result_time, cta_time):
            distance = target - t
            if 0.0 < distance < 1.55:
                amount = 1.0 - distance / 1.55
                transition += (
                    math.sin(2.0 * math.pi * (190.0 + 1250.0 * amount * amount) * t)
                    + 0.35 * math.sin(2.0 * math.pi * (320.0 + 1800.0 * amount * amount) * t + 0.8)
                ) * 0.013 * amount * trans_e

        sig_l, sig_r = _brand_signature(t, 0.18)
        out_l, out_r = _brand_signature(t, cta_time + 0.10)

        left = left_pad + bass + kick + snare + hat + arp * (1.0 - arp_pan * 0.52) + transition + sig_l + out_l
        right = right_pad + bass + kick + snare + hat + arp * (1.0 + arp_pan * 0.52) + transition + sig_r + out_r

        if 0.10 <= t <= 2.30 or cta_time <= t <= min(duration, cta_time + 2.30):
            music_duck = 0.62
            left = (left - sig_l - out_l) * music_duck + sig_l + out_l
            right = (right - sig_r - out_r) * music_duck + sig_r + out_r

        left = math.tanh(left * 1.48) * 0.80 * fade
        right = math.tanh(right * 1.48) * 0.80 * fade
        pcm.append(int(max(-1.0, min(1.0, left)) * 32767))
        pcm.append(int(max(-1.0, min(1.0, right)) * 32767))

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(RATE)
        audio.writeframes(pcm.tobytes())
    return variation
