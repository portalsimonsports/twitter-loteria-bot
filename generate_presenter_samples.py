from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from pathlib import Path

import edge_tts

TEXT = (
    "Portal SimonSports. Chegou a hora de conferir o resultado oficial da Mega-Sena, "
    "concurso três mil e vinte e um. Tenha o seu comprovante em mãos. Vamos ao resultado."
)

# Francisca, Thalita Multilingual e Antônio já foram aprovados e não entram neste lote.
CANDIDATES = [
    ("Macerio Multilingual", "pt-BR-MacerioMultilingualNeural"),
    ("Brenda", "pt-BR-BrendaNeural"),
    ("Donato", "pt-BR-DonatoNeural"),
    ("Elza", "pt-BR-ElzaNeural"),
    ("Fábio", "pt-BR-FabioNeural"),
    ("Giovanna", "pt-BR-GiovannaNeural"),
    ("Humberto", "pt-BR-HumbertoNeural"),
    ("Júlio", "pt-BR-JulioNeural"),
    ("Leila", "pt-BR-LeilaNeural"),
    ("Manuela", "pt-BR-ManuelaNeural"),
    ("Nicolau", "pt-BR-NicolauNeural"),
    ("Thalita Neural", "pt-BR-ThalitaNeural"),
    ("Valério", "pt-BR-ValerioNeural"),
    ("Yara", "pt-BR-YaraNeural"),
    ("Macerio HD", "pt-BR-Macerio:DragonHDLatestNeural"),
    ("Thalita HD", "pt-BR-Thalita:DragonHDLatestNeural"),
    ("Caio", "pt-BR-Caio:MAI-Voice-2"),
    ("Luana", "pt-BR-Luana:MAI-Voice-2"),
    ("Pedro", "pt-BR-Pedro:MAI-Voice-2"),
    ("Rafael", "pt-BR-Rafael:MAI-Voice-2"),
]


def slug(text: str) -> str:
    table = str.maketrans("áàãâéêíóôõúçÁÀÃÂÉÊÍÓÔÕÚÇ", "aaaaeeioooucAAAAEEIOOOUC")
    value = text.translate(table).lower()
    return "_".join(part for part in "".join(ch if ch.isalnum() else " " for ch in value).split())


async def generate_one(label: str, voice: str, output: Path) -> dict:
    target = output / f"{slug(label)}.mp3"
    try:
        communicator = edge_tts.Communicate(TEXT, voice=voice, rate="+0%", pitch="+0Hz", volume="+0%")
        await communicator.save(str(target))
        data = target.read_bytes()
        if len(data) < 1000:
            raise RuntimeError("arquivo de áudio vazio ou incompleto")
        return {
            "label": label,
            "voice": voice,
            "file": target.name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "status": "ok",
        }
    except Exception as exc:
        target.unlink(missing_ok=True)
        return {
            "label": label,
            "voice": voice,
            "file": "",
            "bytes": 0,
            "sha256": "",
            "status": "erro",
            "erro": str(exc),
        }


async def main() -> None:
    output = Path("voice_samples_candidates")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    results = []
    for label, voice in CANDIDATES:
        print(f"Testando {label}: {voice}", flush=True)
        results.append(await generate_one(label, voice, output))

    valid = [item for item in results if item["status"] == "ok"]
    duplicate_hashes = {}
    for item in valid:
        duplicate_hashes.setdefault(item["sha256"], []).append(item["label"])
    duplicates = [labels for labels in duplicate_hashes.values() if len(labels) > 1]

    manifest = {
        "texto": TEXT,
        "validas": valid,
        "rejeitadas": [item for item in results if item["status"] != "ok"],
        "duplicidades": duplicates,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "AMOSTRAS DE APRESENTADORES — PORTAL SIMONSPORTS",
        "",
        f"Texto: {TEXT}",
        "",
        f"Vozes válidas: {len(valid)}",
    ]
    for index, item in enumerate(valid, start=1):
        lines.append(f"{index:02d}. {item['label']} | {item['voice']} | {item['file']}")
    lines.extend(["", f"Vozes recusadas pelo serviço: {len(results) - len(valid)}"])
    for item in results:
        if item["status"] != "ok":
            lines.append(f"- {item['label']} | {item['voice']} | {item.get('erro', '')}")
    if duplicates:
        lines.extend(["", "ATENÇÃO: áudios duplicados detectados:"])
        lines.extend("- " + ", ".join(group) for group in duplicates)
    else:
        lines.extend(["", "Nenhum áudio duplicado entre as vozes válidas."])
    (output / "LEIA-ME.txt").write_text("\n".join(lines), encoding="utf-8")

    shutil.make_archive("amostras_apresentadores_adicionais_simonsports", "zip", output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
