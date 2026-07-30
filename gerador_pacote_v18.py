from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import gerador_pacote_v17 as v17
import voice_narration_v18 as voice
from loteca_columns_v18 import gerar_pacote_loteca
from lottery_result_v18 import parse_lottery_result
from video_specials_v18 import install_visual_support


VERSION = "V18"


def _rename_version(path_value: str) -> str:
    if not path_value:
        return path_value
    path = Path(path_value)
    name = path.name.replace("_v17", "_v18").replace("v17.", "v18.")
    if name == path.name:
        return str(path)
    target = path.with_name(name)
    if path.exists():
        os.replace(path, target)
    return str(target)


def _generate_standard(data: Dict[str, Any]) -> Dict[str, str]:
    originals = {
        "extract_numbers": v17.extract_numbers,
        "reveal_times_full": v17.reveal_times_full,
        "reveal_times_short": v17.reveal_times_short,
        "select_presenter_pair": v17.select_presenter_pair,
        "select_single_voice": v17.select_single_voice,
        "synthesize_dialogue_mix": v17.synthesize_dialogue_mix,
        "synthesize_single_mix": v17.synthesize_single_mix,
        "voice_label": v17.voice_label,
        "pair_label": v17.pair_label,
    }
    v17.extract_numbers = voice.extract_numbers
    v17.reveal_times_full = voice.reveal_times_full
    v17.reveal_times_short = voice.reveal_times_short
    v17.select_presenter_pair = voice.select_presenter_pair
    v17.select_single_voice = voice.select_single_voice
    v17.synthesize_dialogue_mix = voice.synthesize_dialogue_mix
    v17.synthesize_single_mix = voice.synthesize_single_mix
    v17.voice_label = voice.voice_label
    v17.pair_label = voice.pair_label
    try:
        package = v17.gerar_pacote(data)
    finally:
        for name, value in originals.items():
            setattr(v17, name, value)

    package["short"] = _rename_version(package.get("short", ""))
    package["completo"] = _rename_version(package.get("completo", ""))
    package["versao"] = VERSION
    return package


def gerar_pacote(data: Dict[str, Any]) -> Dict[str, str]:
    install_visual_support()
    lottery = str(data.get("loteria") or data.get("produto") or "Loteria").strip()
    raw = data.get("numeros") or data.get("descricao") or data.get("Descrição") or ""
    parts = parse_lottery_result(lottery, raw)
    package = gerar_pacote_loteca(data) if parts.loteca_games else _generate_standard(data)
    print(
        f"[VÍDEO {VERSION}] modalidade={lottery} | modo={package.get('modo_apresentacao', '')} | "
        f"Short={Path(package.get('short', '')).name} | completo={Path(package.get('completo', '')).name}",
        flush=True,
    )
    return package


def executar(data: Dict[str, Any]) -> str:
    return gerar_pacote(data)["short"]


__all__ = ["executar", "gerar_pacote"]
