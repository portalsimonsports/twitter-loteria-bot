from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from gerador_video import criar_poster, executar


def _date_key(value: Any) -> datetime:
    text = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return datetime.min


def _parse_product(value: Any) -> Tuple[str, str]:
    text = str(value or "").strip()
    match = re.match(r"^(.*?)(?:\s+[-–—]?\s*)(\d{2,})$", text)
    if match:
        return match.group(1).strip(" -–—"), match.group(2)
    return text or "Mega-Sena", ""


def _from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    product = item.get("Produto") or item.get("produto") or item.get("Loteria") or item.get("loteria")
    loteria, concurso = _parse_product(product)
    descricao = item.get("Descricao") or item.get("Descrição") or item.get("numeros") or item.get("Números") or ""
    numeros = re.sub(r"^n[uú]meros?\s*:\s*", "", str(descricao), flags=re.I).strip()
    return {
        "loteria": loteria,
        "concurso": item.get("Concurso") or item.get("concurso") or concurso,
        "data": item.get("Data") or item.get("data") or "",
        "numeros": numeros,
        "premio": item.get("Premio") or item.get("Prêmio") or item.get("premio") or "",
        "url": item.get("URL") or item.get("url") or "https://www.portalsimonsports.com/",
    }


def _load_latest(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items: List[Dict[str, Any]] = [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []
            usable = [x for x in items if (x.get("Descricao") or x.get("numeros")) and (x.get("Produto") or x.get("loteria"))]
            if usable:
                latest = max(enumerate(usable), key=lambda pair: (_date_key(pair[1].get("Data") or pair[1].get("data")), pair[0]))[1]
                return _from_item(latest)
        except Exception as exc:
            print(f"[PREVIEW] Não foi possível ler {path}: {exc}", flush=True)

    return {
        "loteria": "Mega-Sena",
        "concurso": "3021",
        "data": "20/06/2026",
        "numeros": ["16", "19", "22", "24", "46", "58"],
        "premio": "R$ 3.500.000,00",
        "url": "https://www.portalsimonsports.com/",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera uma prévia MP4 contínua de 60 segundos para aprovação visual.")
    parser.add_argument("--source", default="data/to_publish.json")
    parser.add_argument("--output-dir", default="preview_output")
    parser.add_argument("--duration", type=float, default=60.0)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = _load_latest(Path(args.source))
    data.update({"previa": True, "duracao": 60.0, "output_dir": str(output_dir)})

    poster = criar_poster(data, output_dir / "previa_youtube_loterias.png")
    video = executar(data)
    print(f"[PREVIEW] Poster: {poster}")
    print(f"[PREVIEW] Vídeo: {video}")


if __name__ == "__main__":
    main()
