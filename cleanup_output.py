# cleanup_output.py
# Portal SimonSports — Limpeza da pasta ./output
#
# Regras principais:
# 1) Trabalha com nomes no padrão:
#      <slug-loteria>-<concurso>.jpg
#      <slug-loteria>-<concurso>-1.jpg
#      <slug-loteria>-<concurso>-2.jpg
#    (jpg/jpeg/png)
#
#    → Para cada (loteria, concurso, extensão):
#       - Mantém APENAS 1 arquivo (preferencialmente sem sufixo)
#       - Remove os demais (duplicados / com sufixo).
#
# 2) Normaliza o slug:
#      - Remove palavras duplicadas
#      - Caso especial Loteria Federal:
#          qualquer combinação {"federal","loteria"} vira "loteria-federal"
#
# 3) Remove também arquivos “errados” que sobram:
#      - slug-slug.jpg  (ex.: dupla-sena-dupla-sena.jpg,
#                        dia-de-sorte-dia-de-sorte.jpg,
#                        federal-loteria-federal.jpg,
#                        loteca-loteca.jpg)
#      - slug.jpg       (sem número de concurso) para slugs conhecidos de loteria,
#                        ex.: dupla-sena.jpg, dia-de-sorte.jpg, loteria-federal.jpg
#
# IMPORTANTE:
# - Só mexe em arquivos .jpg/.jpeg/.png na pasta ./output
# - Ignora .gitkeep e arquivos ocultos.
# - Pode ser rodado localmente ou via GitHub Actions.
#
# Para testar sem apagar nada:
#   DRY_RUN = True

import os
import re
from pathlib import Path

# False = apaga/renomeia de verdade
# True  = só mostra o que faria, sem alterar nada
DRY_RUN = False

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

# Padrão principal: slug-concurso(-sufixo).ext
PAT = re.compile(
    r"^(?P<slug>[a-z0-9\-]+?)-(?P<conc>\d+)(?:-(?P<suffix>\d+))?\.(?P<ext>jpe?g|png)$",
    re.IGNORECASE,
)

# Padrões extras para lixo:
#  - slug-slug.jpg
PAT_DOUBLE_SLUG = re.compile(
    r"^(?P<slug>[a-z0-9\-]+)-(?P=slug)\.(?P<ext>jpe?g|png)$",
    re.IGNORECASE,
)

#  - slug.jpg
PAT_SINGLE_SLUG = re.compile(
    r"^(?P<slug>[a-z0-9\-]+)\.(?P<ext>jpe?g|png)$",
    re.IGNORECASE,
)

# Slugs conhecidos de loterias (para decidir o que é “só slug” que pode apagar)
# → Usamos a forma canonizada (sem acento / duplicidade).
KNOWN_CANON_LOTS = {
    "mega-sena",
    "megasena",
    "quina",
    "lotofacil",
    "lotofacil",
    "lotomania",
    "timemania",
    "dupla-sena",
    "duplasena",
    "dia-de-sorte",
    "diadesorte",
    "super-sete",
    "supersete",
    "loteca",
    "loteria-federal",
    "federal-loteria",
    "federal-loteria-federal",
}


def canonical_slug(slug: str) -> str:
    """
    Remove palavras duplicadas do slug, mantendo a ordem da 1ª ocorrência
    e aplica alguns ajustes especiais (como Loteria Federal).

    Exemplos:
      "federal-loteria-federal" -> "loteria-federal"
      "loteria-federal"         -> "loteria-federal"
      "mega-mega-sena"          -> "mega-sena"
    """
    parts = [p for p in slug.split("-") if p]
    seen = set()
    uniq = []
    for p in parts:
        if p not in seen:
            uniq.append(p)
            seen.add(p)

    key = frozenset(uniq)

    # Caso Loteria Federal: queremos SEMPRE "loteria-federal"
    if key == frozenset({"federal", "loteria"}):
        ordered = [w for w in ["loteria", "federal"] if w in uniq]
        return "-".join(ordered)

    # Outros casos: só remove duplicados mantendo ordem original
    return "-".join(uniq)


def main():
    if not OUTPUT_DIR.exists():
        print(f"Pasta output não encontrada: {OUTPUT_DIR}")
        return

    # =====================================================
    #  PRIMEIRO PASSO: agrupar arquivos com concurso
    # =====================================================
    # key = (canon_slug, conc, ext) -> [ (Path, suffix_int, original_slug) ]
    groups = {}

    for f in OUTPUT_DIR.iterdir():
        if not f.is_file():
            continue
        if f.name.startswith("."):
            continue  # ignora .gitkeep e ocultos

        m = PAT.match(f.name)
        if not m:
            # não é do tipo slug-concurso(-sufixo).jpg → veremos depois
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

        # Apaga todos os outros arquivos do grupo (duplicados/numerados)
        for f, sfx, slug in files:
            # não apagar o novo caminho nem o original (caso já tenha sido renomeado)
            if f == main_file or f == old_main_path:
                continue
            if not f.exists():
                continue
            print(f"[APAGAR]   {f.name}")
            if not DRY_RUN:
                try:
                    f.unlink()
                except FileNotFoundError:
                    pass
            total_deleted += 1

    # =====================================================
    #  SEGUNDO PASSO: remover “slug-slug” e “slug” sozinho
    # =====================================================
    extra_deleted = 0

    for f in OUTPUT_DIR.iterdir():
        if not f.is_file():
            continue
        if f.name.startswith("."):
            continue

        name = f.name

        # 2.1) slug-slug.jpg (ex.: dupla-sena-dupla-sena.jpg)
        m2 = PAT_DOUBLE_SLUG.match(name)
        if m2:
            slug = m2["slug"].lower()
            canon = canonical_slug(slug)
            # Se o slug canonizado é de uma loteria conhecida, apagamos
            if canon in {canonical_slug(s) for s in KNOWN_CANON_LOTS}:
                print(f"[APAGAR EXTRA slug-slug] {name}")
                if not DRY_RUN:
                    try:
                        f.unlink()
                    except FileNotFoundError:
                        pass
                extra_deleted += 1
            continue

        # 2.2) slug.jpg sem número de concurso
        m3 = PAT_SINGLE_SLUG.match(name)
        if m3:
            slug = m3["slug"].lower()
            canon = canonical_slug(slug)
            if canon in {canonical_slug(s) for s in KNOWN_CANON_LOTS}:
                print(f"[APAGAR EXTRA slug] {name}")
                if not DRY_RUN:
                    try:
                        f.unlink()
                    except FileNotFoundError:
                        pass
                extra_deleted += 1
            continue

    print("\nResumo da limpeza:")
    print(f"  Mantidos           : {total_kept}")
    print(f"  Renomeados         : {total_renamed}")
    print(f"  Apagados (grupo)   : {total_deleted}")
    print(f"  Apagados (extras)  : {extra_deleted}")
    if DRY_RUN:
        print("  (DRY_RUN=True, nada foi alterado de verdade.)")


if __name__ == "__main__":
    main()
