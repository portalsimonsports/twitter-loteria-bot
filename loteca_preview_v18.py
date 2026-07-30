from __future__ import annotations

import argparse
from pathlib import Path

from gerador_pacote_v18 import gerar_pacote


SAMPLE = {
    "loteria": "Loteca",
    "concurso": "1263",
    "data": "23/07/2026",
    "numeros": (
        "4 FRANCA/FRA x INGLATERRA/ING 6 (Sáb) | "
        "0 ESPANHA/ESP x ARGENTINA/ARG 0 (Dom) | "
        "1 ATLETICO/MG x BAHIA/BA 1 (Ter) | "
        "2 AVAI/SC x AMERICA/MG 1 (Ter) | "
        "0 NOVORIZONTINO/SP x CRICIUMA/SC 1 (Ter) | "
        "1 UNIV CENTRAL/VEN x SANTOS/SP 4 (Ter) | "
        "2 VILA NOVA/GO x FORTALEZA/CE 1 (Ter) | "
        "2 INDEP.MEDELLIN/COL x VASCO DA GAMA/RJ 2 (Qua) | "
        "1 CORITIBA/PR x PALMEIRAS/SP 3 (Qua) | "
        "2 LANUS/AR x CIENCIANO/PER 0 (Qua) | "
        "0 SPORTING CRISTAL/PER x BRAGANTINO/SP 0 (Qua) | "
        "0 CHAPECOENSE/SC x FLAMENGO/RJ 4 (Qua) | "
        "1 INTERNACIONAL/RS x CRUZEIRO/MG 2 (Qua) | "
        "1 SAO PAULO/SP x ATHLETICO/PR 2 (Qua)"
    ),
    "url": "https://www.portalsimonsports.com/2026/07/resultado-loteca-concurso-1263-23072026.html",
    "previa": True,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera a prévia especial V18 da Loteca.")
    parser.add_argument("--output-dir", default="preview_loteca_v18")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = dict(SAMPLE)
    data["output_dir"] = str(output)
    package = gerar_pacote(data)
    print(f"[LOTECA PREVIEW] Short: {package['short']}")
    print(f"[LOTECA PREVIEW] Completo: {package['completo']}")
    if package.get("poster"):
        print(f"[LOTECA PREVIEW] Pôster: {package['poster']}")


if __name__ == "__main__":
    main()
