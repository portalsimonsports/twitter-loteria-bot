from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import edge_tts

TEXT = (
    "Portal SimonSports. Chegou a hora de conferir o resultado oficial da Mega-Sena, "
    "concurso três mil e vinte e um. Tenha o seu comprovante em mãos. Vamos ao resultado."
)

APPROVED = {
    "Francisca": "pt-BR-FranciscaNeural",
    "Thalita Multilingual": "pt-BR-ThalitaMultilingualNeural",
    "Antônio": "pt-BR-AntonioNeural",
}

# Francisca, Thalita Multilingual e Antônio já foram aprovados e não entram como
# novas candidatas. O serviço é testado com todos os nomes adicionais abaixo.
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

DIALOGUES = [
    ("Francisca e Antônio", "Francisca", "Antônio"),
    ("Thalita e Antônio", "Thalita Multilingual", "Antônio"),
    ("Francisca e Thalita", "Francisca", "Thalita Multilingual"),
]

DIALOGUE_LINES = [
    ("A", "Olá! Seja muito bem-vindo ao Portal SimonSports."),
    ("B", "Chegou a hora de conferir o resultado oficial da Mega-Sena, concurso três mil e vinte e um."),
    ("A", "Tenha o seu comprovante em mãos. Confira agora as dezenas sorteadas."),
    ("A", "Dezesseis. Dezenove. Vinte e dois. Vinte e quatro. Quarenta e seis. Cinquenta e oito."),
    ("B", "Conferiu o seu jogo? Conte nos comentários se acertou alguma dezena."),
    ("A", "Deixe o seu like, inscreva-se e ative as notificações."),
    ("B", "Portal SimonSports, simplesmente o melhor. Até o próximo resultado!"),
]


def slug(text: str) -> str:
    table = str.maketrans("áàãâéêíóôõúçÁÀÃÂÉÊÍÓÔÕÚÇ", "aaaaeeioooucAAAAEEIOOOUC")
    value = text.translate(table).lower()
    return "_".join(part for part in "".join(ch if ch.isalnum() else " " for ch in value).split())


async def synthesize(text: str, voice: str, target: Path, rate: str = "+0%") -> None:
    communicator = edge_tts.Communicate(text, voice=voice, rate=rate, pitch="+0Hz", volume="+0%")
    await communicator.save(str(target))
    if not target.exists() or target.stat().st_size < 1000:
        raise RuntimeError("arquivo de áudio vazio ou incompleto")


async def generate_one(label: str, voice: str, output: Path) -> dict:
    target = output / f"nova_voz_{slug(label)}.mp3"
    try:
        await synthesize(TEXT, voice, target)
        data = target.read_bytes()
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


async def generate_dialogue(label: str, speaker_a: str, speaker_b: str, output: Path) -> dict:
    work = output / f"partes_{slug(label)}"
    work.mkdir(parents=True, exist_ok=True)
    clips = []
    try:
        for index, (speaker, text) in enumerate(DIALOGUE_LINES):
            voice_name = speaker_a if speaker == "A" else speaker_b
            voice = APPROVED[voice_name]
            clip = work / f"{index:02d}_{slug(voice_name)}.mp3"
            await synthesize(text, voice, clip, rate="+1%")
            clips.append(clip)

        concat_file = work / "concat.txt"
        concat_file.write_text("\n".join(f"file '{clip.resolve()}'" for clip in clips), encoding="utf-8")
        target = output / f"dialogo_{slug(label)}.mp3"
        process = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-af", "aresample=48000,alimiter=limit=0.95,loudnorm=I=-16:TP=-1.2:LRA=9",
                "-c:a", "libmp3lame", "-b:a", "192k", str(target),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if process.returncode != 0 or not target.exists() or target.stat().st_size < 1000:
            raise RuntimeError(process.stderr[-2000:] or "falha ao montar diálogo")
        data = target.read_bytes()
        return {
            "label": label,
            "speaker_a": speaker_a,
            "speaker_b": speaker_b,
            "file": target.name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "status": "ok",
        }
    except Exception as exc:
        return {
            "label": label,
            "speaker_a": speaker_a,
            "speaker_b": speaker_b,
            "file": "",
            "bytes": 0,
            "sha256": "",
            "status": "erro",
            "erro": str(exc),
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def main() -> None:
    output = Path("voice_samples_candidates")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    results = []
    for label, voice in CANDIDATES:
        print(f"Testando {label}: {voice}", flush=True)
        results.append(await generate_one(label, voice, output))

    dialogues = []
    for label, speaker_a, speaker_b in DIALOGUES:
        print(f"Gerando diálogo {label}", flush=True)
        dialogues.append(await generate_dialogue(label, speaker_a, speaker_b, output))

    valid = [item for item in results if item["status"] == "ok"]
    valid_dialogues = [item for item in dialogues if item["status"] == "ok"]
    duplicate_hashes = {}
    for item in valid:
        duplicate_hashes.setdefault(item["sha256"], []).append(item["label"])
    duplicates = [labels for labels in duplicate_hashes.values() if len(labels) > 1]

    manifest = {
        "texto_novas_vozes": TEXT,
        "novas_vozes_validas": valid,
        "novas_vozes_rejeitadas": [item for item in results if item["status"] != "ok"],
        "dialogos": dialogues,
        "duplicidades": duplicates,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "AMOSTRAS DE APRESENTADORES — PORTAL SIMONSPORTS",
        "",
        f"Texto das novas vozes: {TEXT}",
        "",
        f"Novas vozes válidas no serviço atual: {len(valid)}",
    ]
    for index, item in enumerate(valid, start=1):
        lines.append(f"{index:02d}. {item['label']} | {item['voice']} | {item['file']}")
    lines.extend(["", f"Diálogos válidos: {len(valid_dialogues)}"])
    for index, item in enumerate(valid_dialogues, start=1):
        lines.append(f"{index:02d}. {item['label']} | {item['file']}")
    lines.extend(["", f"Vozes adicionais recusadas pelo serviço atual: {len(results) - len(valid)}"])
    for item in results:
        if item["status"] != "ok":
            lines.append(f"- {item['label']} | {item['voice']} | {item.get('erro', '')}")
    if duplicates:
        lines.extend(["", "ATENÇÃO: áudios duplicados detectados:"])
        lines.extend("- " + ", ".join(group) for group in duplicates)
    else:
        lines.extend(["", "Nenhum áudio duplicado entre as novas vozes válidas."])
    (output / "LEIA-ME.txt").write_text("\n".join(lines), encoding="utf-8")

    shutil.make_archive("amostras_apresentadores_adicionais_simonsports", "zip", output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
