# cleanup_output.py
# Portal SimonSports — Limpeza da pasta ./output
#
# Regra:
# - Para cada loteria+concurso, manter APENAS UM arquivo:
#   • Se existir <slug>-<concurso>.jpg  (sem sufixo numérico), ele é o principal.
#   • Se só existirem arquivos com sufixo "-1", "-2", ...:
#       -> mantém o MENOR sufixo e renomeia para <slug>-<concurso>.jpg
#   • Todos os outros sufixos são APAGADOS.
#
# Exemplos:
#   dia-de-sorte-1074.jpg            -> mantido
#   dia-de-sorte-1074-1.jpg          -> apagado
#   dia-de-sorte-1074-2.jpg          -> apagado
#
#   megasena-2560-1.jpg              -> renomeado para megasena-2560.jpg
#   megasena-2560-2.jpg              -> apagado
#
# IMPORTANTE:
# - Ele só mexe em arquivos .jpg/.jpeg/.png dentro de ./output
# - Ignora .gitkeep e outros arquivos/formatos.
# - Rode uma vez, confira o resultado e depois faça commit no GitHub.

import os
import re
from pathlib import Path

# Se quiser testar sem apagar nada, mude para True.
DRY_RUN = False

# Pasta de saída (relativa a este arquivo)
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

# Regex: captura base + sufixo numérico opcional + extensão
# Ex.: "dia-de-sorte-1074-12.jpg"
#      base="dia-de-sorte-1074", suffix="12", ext="jpg"
PATTERN = re.compile(r"^(?P<base>.+?)(?:-(?P<suffix>\d+))?\.(?P<ext>jpe?g|png)$", re.IGNORECASE)


def main():
    if not OUTPUT_DIR.exists():
        print(f"Pasta output não encontrada: {OUTPUT_DIR}")
        return

    # Mapa: base.ext -> lista de (Path, suffix_int_ou_None)
    groups = {}

    for f in OUTPUT_DIR.iterdir():
        if not f.is_file():
            continue
        if f.name.startswith("."):
            # ignora .gitkeep ou arquivos ocultos
            continue

        m = PATTERN.match(f.name)
        if not m:
            # não é jpg/jpeg/png no padrão esperado
            continue

        base = m.group("base")
        ext = m.group("ext").lower()
        suffix = m.group("suffix")
        suffix_int = int(suffix) if suffix is not None else None

        key = f"{base}.{ext}"
        groups.setdefault(key, []).append((f, suffix_int))

    total_deleted = 0
    total_renamed = 0
    total_kept = 0

    for key, files in groups.items():
        # Se houver arquivo SEM sufixo (suffix_int is None), ele é o principal
        main_file = None
        with_suffix = []

        for f, sfx in files:
            if sfx is None:
                main_file = f
            else:
                with_suffix.append((f, sfx))

        if main_file is None and with_suffix:
            # Não existe arquivo "base.jpg" ainda.
            # Escolhe o menor sufixo para ser o principal.
            with_suffix.sort(key=lambda x: x[1])  # ordena por sufixo
            main_file, main_suffix = with_suffix[0]
            target = main_file.with_name(key)  # base.ext sem sufixo

            if main_file.name != target.name:
                print(f"[RENOMEAR] {main_file.name}  ->  {target.name}")
                if not DRY_RUN:
                    main_file.rename(target)
                main_file = target
                total_renamed += 1

            # Os demais arquivos com sufixo serão apagados
            for f, sfx in with_suffix[1:]:
                print(f"[APAGAR]   {f.name}")
                if not DRY_RUN:
                    f.unlink()
                total_deleted += 1

            total_kept += 1

        elif main_file is not None:
            # Já existe arquivo base (sem sufixo) -> apagar TODOS os sufixados
            total_kept += 1
            for f, sfx in with_suffix:
                print(f"[APAGAR]   {f.name}")
                if not DRY_RUN:
                    f.unlink()
                total_deleted += 1

        else:
            # Só tem 1 arquivo, e ele tem ou não tem sufixo. Nada a fazer.
            (single_file, _) = files[0]
            print(f"[MANTER]   {single_file.name}")
            total_kept += 1

    print("\nResumo:")
    print(f"  Mantidos : {total_kept}")
    print(f"  Renomeados: {total_renamed}")
    print(f"  Apagados : {total_deleted}")
    if DRY_RUN:
        print("  (DRY_RUN=True, nada foi alterado de verdade.)")


if __name__ == "__main__":
    main()

