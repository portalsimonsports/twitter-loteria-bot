from __future__ import annotations

"""Patch V32 — descrição YouTube com URL completa em linha própria.

Objetivo:
- preservar todo o padrão atual de título/descrição/tags;
- garantir que o link da seção Loterias Caixa apareça completo;
- colocar a URL em linha isolada para o YouTube transformá-la em link clicável;
- aplicar tanto ao vídeo completo quanto ao Short diário.
"""

from typing import Any, Dict, Sequence

import daily_queue_v19 as dq


RESULTS_URL = "https://www.portalsimonsports.com/search/label/Loterias%20Caixa"
_ORIGINAL_METADATA = dq._metadata


def _fix_description(description: str) -> str:
    text = str(description or "")

    replacements = (
        (
            f"Outros resultados das Loterias Caixa: {RESULTS_URL}",
            f"Outros resultados das Loterias Caixa:\n{RESULTS_URL}",
        ),
        (
            f"Outros resultados: {RESULTS_URL}",
            f"Outros resultados das Loterias Caixa:\n{RESULTS_URL}",
        ),
    )

    for old, new in replacements:
        text = text.replace(old, new)

    # Se alguma versão anterior inseriu apenas o domínio ou uma URL truncada,
    # acrescenta a URL oficial completa sem duplicar quando ela já existir.
    if RESULTS_URL not in text:
        text = text.rstrip() + f"\n\nOutros resultados das Loterias Caixa:\n{RESULTS_URL}"

    return text[:5000]


def _metadata_with_clickable_link(results: Sequence[Dict[str, Any]], tipo: str) -> Dict[str, Any]:
    meta = dict(_ORIGINAL_METADATA(results, tipo) or {})
    meta["description"] = _fix_description(meta.get("description", ""))
    return meta


dq.RESULTS_INDEX_URL = RESULTS_URL
dq._metadata = _metadata_with_clickable_link


__all__ = ["RESULTS_URL", "_fix_description", "_metadata_with_clickable_link"]
