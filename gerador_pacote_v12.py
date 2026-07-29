from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict

import gerador_pacote_v11 as v11
from audio_identity_v9 import write_soundtrack
from voice_dialogue_v11 import extract_numbers, reveal_times_short, synthesize_dialogue_mix


VERSION = "V12"


def _create_short(base_video: Path, data: Dict[str, Any], output_dir: Path) -> Path:
    """Gera o Short de 30 segundos sem usar xfade fora da duração válida.

    A sequência possui 24 segundos de apresentação/resultado e 6 segundos de
    encerramento. As duas partes recebem fades próprios e são concatenadas,
    evitando o erro do FFmpeg que ocorria quando a transição começava
    exatamente no último quadro do primeiro trecho.
    """
    lottery_text = str(data.get("loteria") or "Loteria").strip()
    contest_text = str(data.get("concurso") or "").strip()
    lottery = v11._slug(lottery_text) or "loteria"
    contest = v11._slug(contest_text or "resultado") or "resultado"
    output = output_dir / f"short_{lottery}_{contest}_30s_dialogo_v12.mp4"

    numbers = extract_numbers(data)
    # A leitura termina antes do encerramento visual, deixando margem para a
    # última dezena e para o convite final das três vozes.
    reveals = reveal_times_short(
        lottery_text,
        len(numbers),
        intro_duration=5.4,
        result_duration=18.1,
    )

    with tempfile.TemporaryDirectory(prefix="portalsimonsports-short-v12-") as temp_dir:
        temp = Path(temp_dir)
        cta = temp / "cta_short.png"
        music = temp / "trilha_short.wav"
        narrated = temp / "audio_short_narrado.wav"

        v11._short_cta(data, cta)
        write_soundtrack(music, 30.0, lottery_text, contest_text, 23.4, 24.0)
        synthesize_dialogue_mix(data, 30.0, reveals, music, narrated, compact=True)

        intro_duration = 5.4
        result_duration = 18.6
        filter_complex = (
            f"[0:v]trim=start=0:end=0.9,setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={intro_duration - 0.9:.3f},"
            "fps=30,settb=AVTB,format=yuv420p[intro];"
            f"[0:v]trim=start=7.0:end=54.0,setpts={(result_duration / 47.0):.9f}*PTS,"
            "fps=30,settb=AVTB,format=yuv420p[result];"
            "[intro][result]concat=n=2:v=1:a=0,trim=duration=24,"
            "setpts=PTS-STARTPTS,fade=t=out:st=23.55:d=0.45[v0];"
            "[1:v]scale=1080:1920,trim=duration=6,setpts=PTS-STARTPTS,"
            "fps=30,settb=AVTB,format=yuv420p,fade=t=in:st=0:d=0.45[v1];"
            "[v0][v1]concat=n=2:v=1:a=0,trim=duration=30,setpts=PTS-STARTPTS[v]"
        )

        v11._run([
            "ffmpeg",
            "-y",
            "-i",
            str(base_video),
            "-loop",
            "1",
            "-t",
            "6",
            "-i",
            str(cta),
            "-i",
            str(narrated),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "2:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            "30",
            "-movflags",
            "+faststart",
            str(output),
        ])

    return output


def gerar_pacote(data: Dict[str, Any]) -> Dict[str, str]:
    output_dir = Path(str(data.get("output_dir") or "output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    base_video = Path(v11.gerar_base_vertical(data))
    short_path = _create_short(base_video, data, output_dir)
    full_path = Path(v11._create_full(base_video, data, output_dir))

    print(
        f"[VÍDEO {VERSION}] Pacote corrigido com Francisca, Antônio e Thalita | "
        f"Short={short_path.name} | completo={full_path.name}",
        flush=True,
    )
    return {
        "short": str(short_path),
        "completo": str(full_path),
        "base": str(base_video),
    }


def executar(data: Dict[str, Any]) -> str:
    return gerar_pacote(data)["short"]


__all__ = ["executar", "gerar_pacote"]
