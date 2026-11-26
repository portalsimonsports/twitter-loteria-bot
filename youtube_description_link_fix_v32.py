from __future__ import annotations

"""Patch V32 — descrição YouTube com URL completa em linha própria.

Objetivo:
- preservar todo o padrão atual de título/descrição/tags;
- garantir que o link da seção Loterias Caixa apareça completo;
- colocar a URL em linha isolada para o YouTube transformá-la em link clicável;
- aplicar tanto ao vídeo completo quanto ao Short diário.
"""

import re
from typing import Any, Dict, Sequence

import daily_queue_v19 as dq


RESULTS_URL = "https://www.portalsimonsports.com/search/label/Loterias%20Caixa?m=1"
_ORIGINAL_METADATA = dq._metadata


def _fix_description(description: str) -> str:
    text = str(description or "")
    # Identificadores da automação nunca pertencem à descrição pública.
    text = re.sub(r"(?m)^\s*PSS_(?:RESULTADO|CHAMADA)_[A-Za-z0-9_]+\s*$", "", text)
    text = re.sub(r"(?im)^Outros resultados(?: das Loterias Caixa)?:[ \t]*\n?[ \t]*(?:https?://[^\s]+)?[ \t]*$", "", text)
    text = re.sub(r"https?://(?:www\.)?portalsimonsports\.com/search/label/Loterias(?:%20| )Caixa(?:\?m=1)?", "", text, flags=re.I)
    # Link no início: preservado mesmo se o restante alcançar o limite da API.
    header = "Outros resultados das Loterias Caixa:\n" + RESULTS_URL + "\n\n"
    return header + text.strip()[:5000-len(header)]


def _metadata_with_clickable_link(results: Sequence[Dict[str, Any]], tipo: str) -> Dict[str, Any]:
    meta = dict(_ORIGINAL_METADATA(results, tipo) or {})
    meta["description"] = _fix_description(meta.get("description", ""))
    return meta


dq.RESULTS_INDEX_URL = RESULTS_URL
dq._metadata = _metadata_with_clickable_link


__all__ = ["RESULTS_URL", "_fix_description", "_metadata_with_clickable_link"]
