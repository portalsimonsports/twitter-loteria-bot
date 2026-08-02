from __future__ import annotations

import os
import re
import time
import traceback
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Sequence, Tuple

from daily_video_v19 import gerar_pacote_diario
from lottery_result_v18 import parse_lottery_result, team_name_without_code
from post_video import (
    BRAND_LINE,
    PORTAL_DESCRIPTION,
    RESULTS_INDEX_URL,
    _cofre_get_safe,
    _parse_tags,
    _ts_br,
    _unique_tags,
    listar_contas_youtube,
)
from video_queue import (
    _empty,
    _ensure_column,
    _find_col,
    _google_client,
    _load_cofre,
    _log,
    _row_to_video_data,
    _validate_video_data,
    carregar_config,
)
from youtube_auth import get_access_token
from youtube_upload import build_watch_url, upload_thumbnail, upload_video


DAILY_COLUMN_DEFAULT = "Publicado_Youtube_Diario"
CALENDAR_TAB_DEFAULT = "Calendário_Loterias"
DAILY_START_DATE_DEFAULT = "01/08/2026"

DailyCandidate = Tuple[str, List[Tuple[int, Dict[str, Any]]], List[str]]


def _normalize(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in ascii_text).split())


def _lottery_key(value: Any) -> str:
    text = _normalize(value)
    aliases = {
        "mega sena": "mega sena",
        "lotofacil": "lotofacil",
        "mais milionaria": "mais milionaria",
        "mais milhonaria": "mais milionaria",
        "loteria federal": "loteria federal",
    }
    return aliases.get(text, text)


def _display_lottery(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    key = _lottery_key(text)
    aliases = {
        "mega sena": "Mega-Sena",
        "lotofacil": "Lotofácil",
        "mais milionaria": "+Milionária",
        "loteria federal": "Loteria Federal",
    }
    return aliases.get(key, text or "Loteria")


def _parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _date_sort_key(value: str) -> float:
    parsed = _parse_date(value)
    return parsed.timestamp() if parsed else 0.0


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "sim", "yes", "on"}


def _header_value(row: Sequence[str], headers: Sequence[str], names: Sequence[str]) -> str:
    index = _find_col(list(headers), list(names))
    if index is None or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _expected_by_date(calendar_values: List[List[str]]) -> Dict[str, List[str]]:
    expected: Dict[str, List[str]] = {}
    for row in calendar_values[1:]:
        lottery = str(row[0] if len(row) > 0 else "").strip()
        date = str(row[1] if len(row) > 1 else "").strip()
        if not lottery or not _parse_date(date):
            continue
        key = _lottery_key(lottery)
        if not key:
            continue
        expected.setdefault(date, [])
        if key not in expected[date]:
            expected[date].append(key)
    return expected


def _is_daily_final_marker(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return "PUBLICADO YOUTUBE DIÁRIO V19" in text or "PUBLICADO YOUTUBE DIARIO V19" in text


def _partial_full_url(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"Completo:\s*(https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]+)", text)
    return match.group(1) if match else ""


def _row_data(row: Sequence[str], headers: Sequence[str]) -> Dict[str, Any]:
    data = _row_to_video_data(row, list(headers))
    optional_fields = {
        "premiacao": ["Premiação", "Premiacao", "Prêmio", "Premio"],
        "ganhadores": ["Ganhadores", "Quantidade_Ganhadores", "Qtd_Ganhadores"],
        "destaque_short": ["Destaque_Short", "Destaque Short"],
    }
    for target, aliases in optional_fields.items():
        value = _header_value(row, headers, aliases)
        if value:
            data[target] = value
    return data


def _candidate_dates(
    values: List[List[str]],
    headers: List[str],
    daily_index: int,
    expected_map: Dict[str, List[str]],
) -> List[DailyCandidate]:
    start_date = _parse_date(os.getenv("YOUTUBE_DAILY_START_DATE", DAILY_START_DATE_DEFAULT))
    today = datetime.now().date()
    grouped: Dict[str, Dict[Tuple[str, str], Tuple[int, Dict[str, Any], str]]] = {}

    for sheet_row, row in enumerate(values[1:], start=2):
        try:
            data = _row_data(row, headers)
            _validate_video_data(data)
        except Exception:
            continue
        date = str(data.get("data") or "").strip()
        parsed = _parse_date(date)
        if parsed is None or parsed.date() > today:
            continue
        if start_date is not None and parsed.date() < start_date.date():
            continue
        lottery_key = _lottery_key(data.get("loteria"))
        contest = re.sub(r"\D+", "", str(data.get("concurso") or "")) or str(data.get("concurso") or "").strip()
        if not lottery_key or not contest:
            continue
        marker = row[daily_index] if daily_index < len(row) else ""
        grouped.setdefault(date, {})[(lottery_key, contest)] = (sheet_row, data, marker)

    candidates: List[DailyCandidate] = []
    for date, unique_rows in grouped.items():
        expected_order = expected_map.get(date, [])
        if not expected_order:
            continue
        rows = list(unique_rows.values())
        if any(_is_daily_final_marker(marker) for _sheet_row, _data, marker in rows):
            continue
        actual_modalities = {_lottery_key(data.get("loteria")) for _sheet_row, data, _marker in rows}
        if not set(expected_order).issubset(actual_modalities):
            missing = [item for item in expected_order if item not in actual_modalities]
            _log(f"Resumo diário {date} aguardando modalidades: {', '.join(missing)}")
            continue

        order_index = {key: index for index, key in enumerate(expected_order)}
        rows.sort(
            key=lambda item: (
                order_index.get(_lottery_key(item[1].get("loteria")), 999),
                _display_lottery(item[1].get("loteria")),
                str(item[1].get("concurso") or ""),
            )
        )
        candidates.append((date, [(sheet_row, data) for sheet_row, data, _marker in rows], expected_order))

    candidates.sort(key=lambda item: _date_sort_key(item[0]))
    return candidates


def _special_short(resultados: Sequence[Dict[str, Any]]) -> bool:
    if len(resultados) > 1:
        return True
    if not resultados:
        return False
    data = resultados[0]
    name = _normalize(data.get("loteria"))
    special_tokens = ("virada", "sao joao", "independencia", "especial")
    if any(token in name for token in special_tokens):
        return True
    return _env_bool("YOUTUBE_FORCE_SHORT_SINGLE_LOTTERY", False) or str(data.get("destaque_short") or "").strip().lower() in {"1", "sim", "true", "yes"}


def _compact_result(data: Dict[str, Any]) -> str:
    lottery = _display_lottery(data.get("loteria"))
    contest = str(data.get("concurso") or "").strip()
    raw = data.get("numeros") or data.get("descricao") or data.get("Descrição") or ""
    parts = parse_lottery_result(lottery, raw)
    if parts.loteca_games:
        result = f"{lottery} {contest}: 14 jogos e placares"
    elif _lottery_key(lottery) == "loteria federal":
        prizes = [item.strip() for item in str(raw).split("|") if item.strip()]
        result = f"{lottery} {contest}: " + " | ".join(prizes[:5])
    else:
        result = f"{lottery} {contest}: " + ", ".join(parts.display_numbers)
        if parts.trevos:
            result += " | Trevos: " + " e ".join(parts.trevos)
        if parts.team:
            result += " | Time do Coração: " + team_name_without_code(parts.team).title()
        if parts.lucky_month:
            result += " | Mês da Sorte: " + str(parts.lucky_month).title()
    prize = str(data.get("premiacao") or "").strip()
    winners = str(data.get("ganhadores") or "").strip()
    if prize:
        result += f" | Premiação: {prize}"
    if winners:
        result += f" | Ganhadores: {winners}"
    return result


def _title_names(resultados: Sequence[Dict[str, Any]]) -> str:
    names: List[str] = []
    for data in resultados:
        name = _display_lottery(data.get("loteria"))
        if name not in names:
            names.append(name)
    if len(names) <= 3:
        return ", ".join(names)
    return ", ".join(names[:3]) + " e Mais"


def _metadata(resultados: Sequence[Dict[str, Any]], tipo: str) -> Dict[str, Any]:
    date = str(resultados[0].get("data") or "").strip()
    names = _title_names(resultados)
    if tipo == "completo":
        title = f"Resultados das Loterias de Hoje — {names} | {date}"
        if len(title) > 95:
            title = f"Resultados das Loterias de Hoje — Todos os Sorteios | {date}"
        description_lines = [
            f"Confira em um único vídeo os resultados oficiais das loterias sorteadas em {date}.",
            "",
        ]
        for data in resultados:
            description_lines.append("• " + _compact_result(data))
            url = str(data.get("url") or "").strip()
            if url:
                description_lines.append(f"  Detalhes: {url}")
        description_lines.extend([
            "",
            "Curta, comente, compartilhe e inscreva-se no canal para acompanhar os próximos resultados.",
            f"Outros resultados das Loterias Caixa: {RESULTS_INDEX_URL}",
            "",
            BRAND_LINE,
            PORTAL_DESCRIPTION,
            "Fonte: CAIXA Loterias. Conteúdo informativo.",
            "",
            "#LoteriasCaixa #ResultadosDeHoje #ResultadoOficial #PortalSimonSports #SimonSports",
        ])
        tags = [
            "resultados das loterias de hoje",
            "loterias de hoje",
            f"resultados loterias {date}",
            "resultado oficial Caixa",
            "Loterias Caixa",
            "dezenas sorteadas hoje",
            "Portal SimonSports",
            "SimonSports",
            "resultados completos",
        ]
    else:
        title = f"Resultados das Loterias de Hoje em 1 Minuto | {date} #Shorts"
        description_lines = [
            f"Resumo dos principais resultados das Loterias Caixa de {date}.",
            "O vídeo completo com todos os concursos está disponível no canal SimonSports.",
            "",
        ]
        description_lines.extend("• " + _compact_result(data) for data in resultados)
        description_lines.extend([
            "",
            "Inscreva-se para acompanhar os próximos resultados.",
            f"Outros resultados: {RESULTS_INDEX_URL}",
            "Fonte: CAIXA Loterias. Conteúdo informativo.",
            "",
            "#Shorts #LoteriasCaixa #ResultadosDeHoje #PortalSimonSports",
        ])
        tags = [
            "resultados das loterias hoje em 1 minuto",
            "short loterias",
            "resultado rápido loterias",
            "Loterias Caixa hoje",
            "Portal SimonSports",
            "SimonSports",
            "Shorts",
        ]

    for data in resultados:
        lottery = _display_lottery(data.get("loteria"))
        contest = str(data.get("concurso") or "").strip()
        tags.extend([
            f"resultado {lottery}",
            f"{lottery} hoje",
            f"{lottery} concurso {contest}" if contest else lottery,
        ])
    return {
        "title": title[:95],
        "description": "\n".join(description_lines)[:4500],
        "tags": tags,
    }


def _mark_rows(worksheet, row_numbers: Sequence[int], column_index: int, value: str) -> None:
    for row_number in row_numbers:
        worksheet.update_cell(row_number, column_index + 1, value)


def _publish_day(
    date: str,
    rows: Sequence[Tuple[int, Dict[str, Any]]],
    worksheet,
    daily_index: int,
    cofre_get,
    cofre_cache: Dict[str, Any],
    *,
    dry_run: bool,
    pause: float,
    timezone: str,
) -> int:
    resultados = [data for _sheet_row, data in rows]
    row_numbers = [sheet_row for sheet_row, _data in rows]
    gerar_short = _special_short(resultados)
    existing_markers = [worksheet.cell(row_number, daily_index + 1).value or "" for row_number in row_numbers]
    existing_full_url = next((url for url in (_partial_full_url(value) for value in existing_markers) if url), "")

    if dry_run:
        package = {
            "completo": "DRYRUN_resultados_diarios_completo.mp4",
            "short": "DRYRUN_resultados_diarios_short.mp4" if gerar_short else "",
            "poster": "DRYRUN_resultados_diarios_capa.png",
        }
    else:
        package = gerar_pacote_diario(resultados, output_dir="output", gerar_short=gerar_short)

    full_meta = _metadata(resultados, "completo")
    short_meta = _metadata(resultados, "short") if gerar_short else None
    accounts = listar_contas_youtube(cofre_cache)
    if not accounts:
        raise RuntimeError("Nenhuma conta YOUTUBE com REFRESH_TOKEN no Cofre.")

    successes = 0
    first_full_url = existing_full_url
    first_short_url = ""

    for account in accounts:
        client_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_ID", conta=account)
        client_secret = _cofre_get_safe(cofre_get, "YOUTUBE", "CLIENT_SECRET", conta=account)
        refresh_token = _cofre_get_safe(cofre_get, "YOUTUBE", "REFRESH_TOKEN", conta=account)
        if not (client_id and client_secret and refresh_token):
            _log(f"[{account}] Credenciais incompletas para o resumo diário.")
            continue
        privacy = _cofre_get_safe(cofre_get, "YOUTUBE", "PRIVACY_STATUS", conta=account, default="public") or "public"
        category_id = _cofre_get_safe(cofre_get, "YOUTUBE", "CATEGORY_ID", conta=account, default="24") or "24"
        custom_tags = _parse_tags(_cofre_get_safe(cofre_get, "YOUTUBE", "TAGS", conta=account, default=""))

        try:
            if dry_run:
                full_url = existing_full_url or f"https://www.youtube.com/watch?v=DRYRUN_FULL_{account}"
                short_url = f"https://www.youtube.com/watch?v=DRYRUN_SHORT_{account}" if gerar_short else ""
            else:
                access_token = get_access_token(client_id, client_secret, refresh_token)
                if existing_full_url:
                    full_url = existing_full_url
                else:
                    full_id = upload_video(
                        access_token=access_token,
                        video_path=package["completo"],
                        title=full_meta["title"],
                        description=full_meta["description"],
                        tags=_unique_tags(custom_tags, full_meta["tags"]),
                        category_id=category_id,
                        privacy_status=privacy,
                    )
                    full_url = build_watch_url(full_id)
                    try:
                        upload_thumbnail(access_token, full_id, package["poster"])
                        _log(f"[{account}] Capa diária aplicada ao vídeo completo.")
                    except Exception as thumbnail_error:
                        _log(f"[{account}] Vídeo publicado, mas a capa não foi aplicada: {thumbnail_error}")
                    partial = (
                        f"PARCIAL YOUTUBE DIÁRIO V19 em {_ts_br(timezone)} | "
                        f"Completo: {full_url}"
                    )
                    _mark_rows(worksheet, row_numbers, daily_index, partial)

                short_url = ""
                if gerar_short:
                    short_id = upload_video(
                        access_token=access_token,
                        video_path=package["short"],
                        title=short_meta["title"],
                        description=short_meta["description"],
                        tags=_unique_tags(custom_tags, short_meta["tags"]),
                        category_id=category_id,
                        privacy_status=privacy,
                    )
                    short_url = build_watch_url(short_id)

            first_full_url = first_full_url or full_url
            first_short_url = first_short_url or short_url
            successes += 1
            _log(f"[{account}] Resumo diário {date} publicado | completo={full_url} | short={short_url or 'não necessário'}")
        except Exception as error:
            _log(f"[{account}] Erro no resumo diário {date}: {error}")
            traceback.print_exc()
        time.sleep(max(0.5, min(pause, 15.0)))

    if successes <= 0:
        return 0

    final_mark = (
        f"Publicado YOUTUBE DIÁRIO V19 em {_ts_br(timezone)} | "
        f"Completo: {first_full_url}"
    )
    if gerar_short:
        final_mark += f" | Short: {first_short_url}"
    else:
        final_mark += " | Short: não necessário — apenas uma loteria no dia"
    _mark_rows(worksheet, row_numbers, daily_index, final_mark)
    return 1


def processar_resumo_diario() -> int:
    config = carregar_config()
    dry_run = config.dry_run
    client = _google_client()
    cofre_cache, cofre_get = _load_cofre(client, config)
    spreadsheet = client.open_by_key(config.google_sheet_id)
    worksheet = spreadsheet.worksheet(config.sheet_tab)
    calendar_tab = os.getenv("YOUTUBE_CALENDAR_TAB", CALENDAR_TAB_DEFAULT)
    calendar = spreadsheet.worksheet(calendar_tab)

    values = worksheet.get_all_values()
    calendar_values = calendar.get_all_values()
    if not values or not calendar_values:
        _log("Planilha principal ou calendário vazio.")
        return 0

    headers = list(values[0])
    daily_column = os.getenv("PUBLICADO_YT_DIARIO_COL", DAILY_COLUMN_DEFAULT)
    daily_index = _ensure_column(worksheet, headers, daily_column)
    expected_map = _expected_by_date(calendar_values)
    candidates = _candidate_dates(values, headers, daily_index, expected_map)
    if not candidates:
        _log("Nenhum dia completo pendente para publicação consolidada.")
        return 0

    date, rows, expected_order = candidates[0]
    _log(
        f"Publicação diária selecionada: {date} | resultados={len(rows)} | "
        f"modalidades previstas={len(expected_order)} | máximo diário=1 completo + 1 Short"
    )
    return _publish_day(
        date,
        rows,
        worksheet,
        daily_index,
        cofre_get,
        cofre_cache,
        dry_run=dry_run,
        pause=config.pausa,
        timezone=config.timezone,
    )


def main() -> None:
    processar_resumo_diario()


if __name__ == "__main__":
    main()
