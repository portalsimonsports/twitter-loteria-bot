from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import requests

BASE_URL = "https://servicebus2.caixa.gov.br/portaldeloterias/api"

SLUGS = {
    "quina": "quina",
    "lotofacil": "lotofacil",
    "dia de sorte": "diadesorte",
    "diadesorte": "diadesorte",
    "mega sena": "megasena",
    "megasena": "megasena",
    "timemania": "timemania",
    "dupla sena": "duplasena",
    "duplasena": "duplasena",
    "super sete": "supersete",
    "supersete": "supersete",
    "lotomania": "lotomania",
    "mais milionaria": "maismilionaria",
    "maismilionaria": "maismilionaria",
    "loteria federal": "federal",
    "federal": "federal",
}


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    repl = str.maketrans({
        "á": "a", "à": "a", "ã": "a", "â": "a",
        "é": "e", "ê": "e", "í": "i",
        "ó": "o", "ô": "o", "õ": "o",
        "ú": "u", "ç": "c", "+": "mais ", "-": " ",
    })
    text = text.translate(repl)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _contest(value: Any) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    return digits


def _slug(key: str, display: str) -> str:
    for candidate in (_norm(key), _norm(display)):
        if candidate in SLUGS:
            return SLUGS[candidate]
        compact = candidate.replace(" ", "")
        if compact in SLUGS:
            return SLUGS[compact]
    return ""


def _join_numbers(values: Iterable[Any]) -> str:
    out = [str(item).strip() for item in (values or []) if str(item).strip()]
    return ",".join(out)


def _extract_numbers(payload: Dict[str, Any], slug: str) -> str:
    main = _join_numbers(payload.get("listaDezenas") or payload.get("dezenasSorteadasOrdemSorteio") or [])
    if not main:
        return ""

    if slug == "duplasena":
        second = _join_numbers(
            payload.get("listaDezenasSegundoSorteio")
            or payload.get("listaDezenas2")
            or payload.get("dezenasSegundoSorteio")
            or []
        )
        if second:
            return f"{main} | {second}"

    if slug == "timemania":
        team = str(
            payload.get("nomeTimeCoracaoMesSorte")
            or payload.get("nomeTimeCoracao")
            or ""
        ).strip()
        if team:
            return f"{main} - {team}"

    if slug == "diadesorte":
        month = str(
            payload.get("nomeTimeCoracaoMesSorte")
            or payload.get("mesSorte")
            or payload.get("mesDaSorte")
            or ""
        ).strip()
        if month:
            return f"{main} - {month}"

    if slug == "maismilionaria":
        trevos = _join_numbers(payload.get("trevosSorteados") or payload.get("listaTrevos") or [])
        if trevos:
            return f"{main} | Trevos: {trevos}"

    return main


def fetch_official_result(key: str, display: str, contest: str, *, timeout: int = 25) -> Dict[str, Any] | None:
    slug = _slug(key, display)
    contest_digits = _contest(contest)
    if not slug or not contest_digits:
        return None

    response = requests.get(
        f"{BASE_URL}/{slug}/{contest_digits}",
        headers={
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "PortalSimonSports-GitHubActions/2026",
        },
        timeout=timeout,
    )
    if response.status_code in (404, 204):
        return None
    response.raise_for_status()
    payload = response.json() or {}

    returned_contest = _contest(payload.get("numero") or payload.get("numeroConcurso") or "")
    if returned_contest and returned_contest != contest_digits:
        return None

    date = str(payload.get("dataApuracao") or payload.get("dataSorteio") or "").strip()
    numbers = _extract_numbers(payload, slug)
    if not date or not numbers:
        return None

    return {
        "loteria": display,
        "concurso": contest_digits,
        "data": date,
        "numeros": numbers,
        "url": "",
        "fonte": f"{BASE_URL}/{slug}/{contest_digits}",
    }


def _header_index(headers: Sequence[str], *names: str) -> int | None:
    normalized = [_norm(item).replace(" ", "") for item in headers]
    for name in names:
        target = _norm(name).replace(" ", "")
        if target in normalized:
            return normalized.index(target)
    return None


def append_missing_results(
    worksheet,
    values: List[List[str]],
    targets: Sequence[Tuple[str, str, str]],
    *,
    expected_date: str,
    log=print,
) -> List[Dict[str, Any]]:
    if not values:
        return []

    headers = list(values[0])
    i_lottery = _header_index(headers, "Loteria", "Produto")
    i_contest = _header_index(headers, "Concurso")
    i_date = _header_index(headers, "Data", "Data Sorteio")
    i_numbers = _header_index(headers, "Números", "Numeros", "Descrição", "Descricao")
    if None in (i_lottery, i_contest, i_date, i_numbers):
        raise RuntimeError("ImportadosBlogger2 sem colunas mínimas para fallback CAIXA.")

    existing = set()
    for row in values[1:]:
        lottery = row[i_lottery] if i_lottery < len(row) else ""
        contest = row[i_contest] if i_contest < len(row) else ""
        existing.add((_norm(lottery), _contest(contest)))

    inserted: List[Dict[str, Any]] = []
    for key, display, contest in targets:
        pair = (_norm(display), _contest(contest))
        if pair in existing:
            continue

        try:
            result = fetch_official_result(key, display, contest)
        except Exception as error:
            log(f"Fallback CAIXA {display} {contest}: erro ao consultar API: {error}")
            continue
        if not result:
            log(f"Fallback CAIXA {display} {contest}: resultado ainda indisponível.")
            continue
        if result["data"] != expected_date:
            log(
                f"Fallback CAIXA {display} {contest}: data recebida {result['data']} "
                f"difere de {expected_date}; ignorado."
            )
            continue

        row = [""] * len(headers)
        row[i_lottery] = display
        row[i_contest] = result["concurso"]
        row[i_date] = result["data"]
        row[i_numbers] = result["numeros"]
        worksheet.append_row(row, value_input_option="USER_ENTERED")
        inserted.append(result)
        existing.add(pair)
        log(f"Fallback CAIXA inseriu {display} {contest} em ImportadosBlogger2.")

    return inserted


__all__ = ["append_missing_results", "fetch_official_result"]
