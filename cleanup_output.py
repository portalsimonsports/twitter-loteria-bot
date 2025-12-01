# cleanup_output.py
# Portal SimonSports — Limpeza da pasta ./output
#
# Regras:
# 1) Trabalha com nomes no padrão:
#      <slug-loteria>-<concurso>.jpg
#      <slug-loteria>-<concurso>-1.jpg
#      <slug-loteria>-<concurso>-2.jpg
#    (jpg/jpeg/png)
#
# 2) Para cada combinação (loteria, concurso, extensão):
#    - Mantém APENAS 1 arquivo:
#        • escolhe preferencialmente o que NÃO tem sufixo (-1, -2...)
#        • se só tiver com sufixo, pega o MENOR sufixo
#    - Todos os outros são APAGADOS.
#
# 3) Também normaliza o "slug" da loteria, removendo palavras repetidas:
#      federal-loteria-federal-5995.jpg  -> federal-loteria-5995.jpg
#      mega-mega-sena-2945.jpg           -> mega-sena-2945.jpg
#
# IMPORTANTE:
# - Só mexe em arquivos .jpg/.jpeg/.png na pasta ./output
# - Ignora .gitkeep e arquivos ocultos.
# - Pode ser rodado localmente ou via GitHub Actions.
#
# Para testar sem apagar nada, basta mudar DRY_RUN = True.

import os
import re
from pathlib import Path

# False = apaga/renomeia de verdade
# True  = só mostra o que faria, sem alterar nada
DRY_RUN = False

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

# Ex.: slug="federal-loteria-federal", conc="5995", suffix="2" (opcional), ext="jpg"
PAT = re.compile(
    r"^(?P<slug>[a-z0-9\-]+?)-(?P<conc>\d+)(?:-(?P<suffix>\d+))?\.(?P<ext>jpe?g|png)$",
    re.IGNORECASE,
)


def canonical_slug(slug: str) -> str:
    """
    Remove palavras duplicadas do slug, mantendo a ordem da 1ª ocorrência.

    Ex.:
      "federal-loteria-federal" -> "federal-loteria"
      "mega-mega-sena"          -> "mega-sena"
    """
    parts = [p for p in slug.split("-") if p]
    seen = set()
    uniq = []
    for p in parts:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return "-".join(uniq)


def main():
    if not OUTPUT_DIR.exists():
        print(f"Pasta output não encontrada: {OUTPUT_DIR}")
        return

    # key = (canon_slug, conc, ext) -> [ (Path, suffix_int, original_slug) ]
    groups = {}

    # Varre todos os arquivos da pasta output
    for f in OUTPUT_DIR.iterdir():
        if not f.is_file():
            continue
        if f.name.startswith("."):
            # ignora .gitkeep e ocultos
            continue

        m = PAT.match(f.name)
        if not m:
            # não está no padrão esperado; ignoramos
            continue

        slug = m["slug"].lower()
        conc = m["conc"]
        suffix = m["suffix"]
        ext = m["ext"].lower()

        canon = canonical_slug(slug)
        suffix_int = int(suffix) if suffix is not None else None

        key = (canon, conc, ext)
        groups.setdefault(key, []).append((f, suffix_int, slug))

    total_deleted = 0
    total_renamed = 0
    total_kept = 0

    # Para cada (loteria normalizada, concurso, extensão)
    for (canon, conc, ext), files in groups.items():
        # Escolha do arquivo principal:
        # 1) Sem sufixo e já com slug canônico
        # 2) Sem sufixo (slug que for)
        # 3) Menor sufixo numérico
        main = None

        # 1) Sem sufixo e slug == canon
        for f, sfx, slug in files:
            if sfx is None and slug == canon:
                main = (f, sfx, slug)
                break

        # 2) Qualquer sem sufixo
        if main is None:
            for f, sfx, slug in files:
                if sfx is None:
                    main = (f, sfx, slug)
                    break

        # 3) Se todos tiverem sufixo, escolhe o menor
        if main is None:
            main = sorted(
                files, key=lambda t: (999999 if t[1] is None else t[1])
            )[0]

        main_file, main_sfx, main_slug = main
        old_main_path = main_file  # guarda o caminho original

        # Nome final desejado (slug já "limpo")
        target_name = f"{canon}-{conc}.{ext}"
        target_path = main_file.with_name(target_name)

        if main_file.name != target_name:
            print(f"[RENOMEAR] {main_file.name} -> {target_name}")
            if not DRY_RUN:
                main_file.rename(target_path)
            main_file = target_path
            total_renamed += 1

        total_kept += 1

        # Apaga todos os outros arquivos do grupo
        for f, sfx, slug in files:
            # não apagar nem o novo caminho nem o original (caso já tenha sido renomeado)
            if f == main_file or f == old_main_path:
                continue
            if not f.exists():
                continue
            print(f"[APAGAR]   {f.name}")
            if not DRY_RUN:
                try:
                    f.unlink()
                except FileNotFoundError:
                    # se por qualquer razão já tiver sido removido, ignora
                    pass
            total_deleted += 1

    print("\nResumo da limpeza:")
    print(f"  Mantidos   : {total_kept}")
    print(f"  Renomeados : {total_renamed}")
    print(f"  Apagados   : {total_deleted}")
    if DRY_RUN:
        print("  (DRY_RUN=True, nada foi alterado de verdade.)")


if __name__ == "__main__":
    main()