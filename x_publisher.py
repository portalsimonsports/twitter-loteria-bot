# -*- coding: utf-8 -*-
"""
Publicador automático específico para o X.

Objetivos:
- manter a publicação 100% automática;
- impedir duplicidade por concurso/evento;
- publicar um evento em apenas uma conta;
- limitar rajadas e volume diário;
- criar textos informativos materialmente diferentes;
- registrar auditoria em planilha;
- abrir circuito em erros 401, 403, 429 e falhas temporárias.

Este módulo reutiliza credenciais, planilha e geração de imagens já existentes em bot.py.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytz
import tweepy

import bot


TZ = pytz.timezone("America/Sao_Paulo")
X_LIMIT = 280
TCO_URL_LENGTH = 23
LEDGER_HEADERS = [
    "EVENT_KEY",
    "STATUS",
    "TWEET_ID",
    "ACCOUNT",
    "LOTERIA",
    "CONCURSO",
    "DATA_SORTEIO",
    "TEXT_HASH",
    "MEDIA_HASH",
    "URL",
    "CREATED_AT",
    "DETAIL",
]
STATE_HEADERS = ["CHAVE", "VALOR", "ATUALIZADO"]


@dataclass
class XRunResult:
    published: int = 0
    recovered: int = 0
    skipped: int = 0
    errors: int = 0
    circuit_opened: bool = False
    circuit_reason: str = ""


def _now() -> datetime:
    return datetime.now(TZ)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _now()).isoformat(timespec="seconds")


def _log(*parts: Any) -> None:
    bot._log("[X-SEGURO]", *parts)


def _cfg(name: str, default: str = "") -> str:
    env = (os.getenv(name, "") or "").strip()
    if env:
        return env
    try:
        value = bot._cofre_get("X", name, default=default)
        return (value or default or "").strip()
    except Exception:
        return (default or "").strip()


def _cfg_bool(name: str, default: bool = False) -> bool:
    value = _cfg(name, "true" if default else "false").lower()
    if value in {"1", "true", "sim", "yes", "on"}:
        return True
    if value in {"0", "false", "nao", "não", "no", "off"}:
        return False
    return default


def _cfg_int(name: str, default: int, minimum: int = 0, maximum: int = 100000) -> int:
    try:
        value = int(float(_cfg(name, str(default))))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _cfg_float(name: str, default: float, minimum: float = 0.0, maximum: float = 86400.0) -> float:
    try:
        value = float(_cfg(name, str(default)))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _safe(row: Sequence[str], column: int, default: str = "") -> str:
    if len(row) < column:
        return default
    return bot._strip_invisible(row[column - 1])


def _event_data(row: Sequence[str]) -> Dict[str, str]:
    return {
        "loteria": _safe(row, bot.COL_LOTERIA, "Loteria"),
        "concurso": _safe(row, bot.COL_CONCURSO, "sem número"),
        "data": _safe(row, bot.COL_DATA, ""),
        "numeros": _safe(row, bot.COL_NUMEROS, ""),
        "url": _safe(row, bot.COL_URL, ""),
    }


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def _event_key(row: Sequence[str]) -> str:
    data = _event_data(row)
    raw = "|".join(
        _normalize(data[key])
        for key in ("loteria", "concurso", "data", "numeros", "url")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _worksheet(parent_ws: Any, title: str, headers: List[str], rows: int = 2000) -> Any:
    spreadsheet = parent_ws.spreadsheet
    try:
        ws = spreadsheet.worksheet(title)
    except Exception as exc:
        if exc.__class__.__name__ != "WorksheetNotFound":
            raise
        ws = spreadsheet.add_worksheet(title=title, rows=rows, cols=max(12, len(headers)))
        ws.append_row(headers, value_input_option="RAW")
        _log(f"Aba criada: {title}")
        return ws

    current = ws.row_values(1)
    if not current:
        ws.append_row(headers, value_input_option="RAW")
    else:
        for index, header in enumerate(headers, start=1):
            if len(current) < index or current[index - 1].strip() != header:
                ws.update_cell(1, index, header)
    return ws


def _ledger_ws(main_ws: Any) -> Any:
    return _worksheet(main_ws, _cfg("X_LEDGER_TAB", "X_Publicacoes"), LEDGER_HEADERS)


def _state_ws(main_ws: Any) -> Any:
    return _worksheet(main_ws, _cfg("X_STATE_TAB", "X_Estado"), STATE_HEADERS, rows=100)


def _state_load(state_ws: Any) -> Dict[str, Tuple[str, int]]:
    values = state_ws.get_all_values()
    result: Dict[str, Tuple[str, int]] = {}
    for row_number, row in enumerate(values[1:], start=2):
        key = (row[0] if len(row) > 0 else "").strip().upper()
        value = (row[1] if len(row) > 1 else "").strip()
        if key:
            result[key] = (value, row_number)
    return result


def _state_set(state_ws: Any, key: str, value: str) -> None:
    key = (key or "").strip().upper()
    state = _state_load(state_ws)
    if key in state:
        row_number = state[key][1]
        state_ws.update_cell(row_number, 2, value)
        state_ws.update_cell(row_number, 3, _iso())
    else:
        state_ws.append_row([key, value, _iso()], value_input_option="RAW")


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return TZ.localize(parsed)
        return parsed.astimezone(TZ)
    except Exception:
        return None


def _circuit_status(state_ws: Any) -> Tuple[bool, str]:
    state = _state_load(state_ws)
    until_raw = state.get("CIRCUIT_UNTIL", ("", 0))[0]
    reason = state.get("CIRCUIT_REASON", ("", 0))[0]
    until = _parse_iso(until_raw)
    if until and until > _now():
        return True, f"{reason or 'proteção ativa'} até {until.strftime('%d/%m/%Y %H:%M:%S')}"
    if until_raw:
        _state_set(state_ws, "CIRCUIT_UNTIL", "")
        _state_set(state_ws, "CIRCUIT_REASON", "")
    return False, ""


def _open_circuit(state_ws: Any, reason: str, until: datetime) -> None:
    _state_set(state_ws, "CIRCUIT_REASON", reason[:500])
    _state_set(state_ws, "CIRCUIT_UNTIL", _iso(until))
    _log(f"Circuito aberto: {reason} | até {_iso(until)}")


def _ledger_load(ledger_ws: Any) -> Dict[str, Any]:
    values = ledger_ws.get_all_values()
    posted_events: Dict[str, Dict[str, str]] = {}
    posted_text_hashes: set[str] = set()
    posted_media_hashes: set[str] = set()
    posted_24h = 0
    cutoff = _now() - timedelta(hours=24)

    for row_number, row in enumerate(values[1:], start=2):
        event_key = (row[0] if len(row) > 0 else "").strip()
        status = (row[1] if len(row) > 1 else "").strip().upper()
        created_at = (row[10] if len(row) > 10 else "").strip()
        if status == "POSTED":
            record = {
                "tweet_id": (row[2] if len(row) > 2 else "").strip(),
                "account": (row[3] if len(row) > 3 else "").strip(),
                "row_number": str(row_number),
            }
            if event_key:
                posted_events[event_key] = record
            text_hash = (row[7] if len(row) > 7 else "").strip()
            media_hash = (row[8] if len(row) > 8 else "").strip()
            if text_hash:
                posted_text_hashes.add(text_hash)
            if media_hash:
                posted_media_hashes.add(media_hash)
            created = _parse_iso(created_at)
            if created and created >= cutoff:
                posted_24h += 1

    return {
        "posted_events": posted_events,
        "posted_text_hashes": posted_text_hashes,
        "posted_media_hashes": posted_media_hashes,
        "posted_24h": posted_24h,
        "rows": len(values),
    }


def _ledger_append(
    ledger_ws: Any,
    event_key: str,
    status: str,
    account: str,
    data: Dict[str, str],
    text_hash: str,
    media_hash: str = "",
    tweet_id: str = "",
    detail: str = "",
) -> int:
    row_number = len(ledger_ws.get_all_values()) + 1
    ledger_ws.append_row(
        [
            event_key,
            status,
            tweet_id,
            account,
            data["loteria"],
            data["concurso"],
            data["data"],
            text_hash,
            media_hash,
            data["url"],
            _iso(),
            detail[:1000],
        ],
        value_input_option="RAW",
    )
    return row_number


def _ledger_update(
    ledger_ws: Any,
    row_number: int,
    status: str,
    tweet_id: str = "",
    media_hash: str = "",
    detail: str = "",
) -> None:
    ledger_ws.update_cell(row_number, 2, status)
    if tweet_id:
        ledger_ws.update_cell(row_number, 3, tweet_id)
    if media_hash:
        ledger_ws.update_cell(row_number, 9, media_hash)
    ledger_ws.update_cell(row_number, 11, _iso())
    ledger_ws.update_cell(row_number, 12, detail[:1000])


def _status_column(main_ws: Any) -> int:
    column = bot.COL_STATUS_REDES.get("X")
    if not column:
        column = bot._ensure_status_column(main_ws, "X", None)
        bot.COL_STATUS_REDES["X"] = column
    return int(column)


def _claim_is_stale(value: str, ttl_minutes: int) -> bool:
    value = (value or "").strip()
    if not value.startswith("PROCESSANDO_X|"):
        return False
    parts = value.split("|", 3)
    if len(parts) < 3:
        return True
    claimed_at = _parse_iso(parts[2])
    return not claimed_at or claimed_at < (_now() - timedelta(minutes=ttl_minutes))


def coletar_candidatos_x(main_ws: Any) -> List[Tuple[int, List[str]]]:
    rows = main_ws.get_all_values()
    if len(rows) <= 1:
        return []
    status_col = _status_column(main_ws)
    ttl = _cfg_int("X_CLAIM_TTL_MINUTES", 60, 10, 1440)
    candidates: List[Tuple[int, List[str]]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        status = row[status_col - 1] if len(row) >= status_col else ""
        status = bot._strip_invisible(status)
        if status and not _claim_is_stale(status, ttl):
            continue
        if not bot._row_has_min_payload(row):
            continue
        candidates.append((row_number, row))
    _log(f"Candidatas: {len(candidates)}/{len(rows) - 1}")
    return candidates


def _claim(main_ws: Any, row_number: int, event_key: str) -> bool:
    status_col = _status_column(main_ws)
    run_id = (os.getenv("GITHUB_RUN_ID", "") or uuid.uuid4().hex[:12]).strip()
    value = f"PROCESSANDO_X|{run_id}|{_iso()}|{event_key[:16]}"
    main_ws.update_cell(row_number, status_col, value)
    confirmed = bot._strip_invisible(main_ws.cell(row_number, status_col).value or "")
    return confirmed == value


def _release_claim(main_ws: Any, row_number: int) -> None:
    main_ws.update_cell(row_number, _status_column(main_ws), "")


def _mark_error(main_ws: Any, row_number: int, code: str, detail: str) -> None:
    value = f"ERRO_X_{code} em {bot._ts_br()} | {detail[:250]}"
    main_ws.update_cell(row_number, _status_column(main_ws), value)


def _hashtag(loteria: str) -> str:
    normalized = unicodedata.normalize("NFKD", loteria or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^A-Za-z0-9]", "", normalized)
    return f"#{normalized}" if normalized else ""


def _weighted_length(text: str) -> int:
    total = 0
    cursor = 0
    for match in re.finditer(r"https?://\S+", text or ""):
        total += len(text[cursor:match.start()])
        total += TCO_URL_LENGTH
        cursor = match.end()
    total += len((text or "")[cursor:])
    return total


def _trim_result(result: str, limit: int = 150) -> str:
    result = re.sub(r"\s+", " ", result or "").strip()
    if len(result) <= limit:
        return result
    return result[: max(0, limit - 3)].rstrip() + "..."


def montar_texto_x(row: Sequence[str], event_key: str) -> str:
    data = _event_data(row)
    loteria = data["loteria"] or "Loteria"
    concurso = data["concurso"] or "sem número"
    data_sorteio = data["data"] or "data informada na publicação"
    resultado = _trim_result(data["numeros"], 150)
    source = _cfg("X_SOURCE_LABEL", "Fonte: Loterias CAIXA")
    disclosure = _cfg("X_DISCLOSURE_TEXT", "Atualização automática informativa.")
    include_link = _cfg_bool("X_INCLUDE_LINK", True)
    include_hashtag = _cfg_bool("X_INCLUDE_HASHTAG", True)
    link = data["url"] if include_link else ""
    tag = _hashtag(loteria) if include_hashtag else ""

    variants = [
        (
            f"🎯 {loteria} — concurso {concurso}\n"
            f"Resultado: {resultado}\n"
            f"Sorteio de {data_sorteio}."
        ),
        (
            f"✅ Resultado confirmado: {loteria} {concurso}\n"
            f"Números apurados: {resultado}\n"
            f"Data do sorteio: {data_sorteio}."
        ),
        (
            f"📊 {loteria}, concurso {concurso}\n"
            f"Resultado oficial: {resultado}\n"
            f"Referência: {data_sorteio}."
        ),
        (
            f"🔎 Confira o resultado da {loteria}\n"
            f"Concurso {concurso}: {resultado}\n"
            f"Sorteio realizado em {data_sorteio}."
        ),
        (
            f"📌 Atualização da {loteria}\n"
            f"Concurso {concurso} — resultado: {resultado}\n"
            f"Data: {data_sorteio}."
        ),
        (
            f"ℹ️ {loteria} | Concurso {concurso}\n"
            f"Resultado divulgado: {resultado}\n"
            f"Sorteio: {data_sorteio}."
        ),
    ]
    variant_index = int(event_key[:8], 16) % len(variants)
    body = variants[variant_index]
    optional_lines = []
    if link:
        optional_lines.append(f"Detalhes: {link}")
    if tag:
        optional_lines.append(tag)

    text = "\n".join([body, source, disclosure] + optional_lines).strip()
    if _weighted_length(text) <= X_LIMIT:
        return text

    if tag:
        optional_lines = [line for line in optional_lines if line != tag]
        text = "\n".join([body, source, disclosure] + optional_lines).strip()
        if _weighted_length(text) <= X_LIMIT:
            return text

    if link:
        optional_lines = [line for line in optional_lines if not line.startswith("Detalhes: ")]
        text = "\n".join([body, source, disclosure] + optional_lines).strip()
        if _weighted_length(text) <= X_LIMIT:
            return text

    compact = (
        f"{loteria} — concurso {concurso}\n"
        f"Resultado: {_trim_result(resultado, 105)}\n"
        f"{source}\n{disclosure}"
    )
    if _weighted_length(compact) <= X_LIMIT:
        return compact

    return (
        f"{loteria} — concurso {concurso}\n"
        f"Resultado completo na imagem.\n{source}\n{disclosure}"
    )[:X_LIMIT]


def _select_account(accounts: Sequence[Any], event_key: str) -> Any:
    strategy = _cfg("X_ACCOUNT_STRATEGY", "PRIMARY_ONLY").strip().upper()
    if strategy == "ROUND_ROBIN" and len(accounts) > 1:
        return accounts[int(event_key[:8], 16) % len(accounts)]
    if strategy not in {"PRIMARY_ONLY", "ROUND_ROBIN"}:
        _log(f"X_ACCOUNT_STRATEGY inválida ({strategy}); usando PRIMARY_ONLY.")
    return accounts[0]


def _http_status(exc: Exception) -> Optional[int]:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status:
        try:
            return int(status)
        except Exception:
            pass
    if isinstance(exc, tweepy.TooManyRequests):
        return 429
    if isinstance(exc, tweepy.Unauthorized):
        return 401
    if isinstance(exc, tweepy.Forbidden):
        return 403
    if isinstance(exc, tweepy.BadRequest):
        return 400
    if isinstance(exc, tweepy.TwitterServerError):
        return 500
    return None


def _rate_reset(exc: Exception) -> datetime:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    raw = headers.get("x-rate-limit-reset") or headers.get("retry-after")
    if raw:
        try:
            number = int(float(raw))
            if number > 1000000000:
                return datetime.fromtimestamp(number, TZ) + timedelta(minutes=2)
            return _now() + timedelta(seconds=max(60, number)) + timedelta(minutes=2)
        except Exception:
            pass
    return _now() + timedelta(minutes=60)


def _exception_detail(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", "")
    text = getattr(response, "text", "")
    base = f"HTTP {status} | {type(exc).__name__}: {exc}"
    if text:
        base += f" | {text[:500]}"
    return re.sub(r"\s+", " ", base).strip()[:1000]


def publicar_x_automatico(main_ws: Any) -> XRunResult:
    result = XRunResult()
    ledger_ws = _ledger_ws(main_ws)
    state_ws = _state_ws(main_ws)

    circuit_open, circuit_detail = _circuit_status(state_ws)
    if circuit_open:
        _log(f"Publicação suspensa automaticamente: {circuit_detail}")
        result.circuit_opened = True
        result.circuit_reason = circuit_detail
        return result

    accounts = bot._build_x_accounts()
    if not accounts:
        _log("Nenhuma conta X configurada.")
        return result

    candidates = coletar_candidatos_x(main_ws)
    if not candidates:
        return result

    ledger = _ledger_load(ledger_ws)
    max_run = _cfg_int("X_MAX_PUBLICACOES_RODADA", 3, 1, 10)
    max_24h = _cfg_int("X_MAX_PUBLICACOES_24H", 20, 1, 100)
    pause = _cfg_float("X_PAUSA_ENTRE_POSTS", 60.0, 10.0, 900.0)
    circuit_hours = _cfg_int("X_CIRCUIT_HOURS", 24, 1, 168)

    remaining_24h = max(0, max_24h - int(ledger["posted_24h"]))
    limit = min(max_run, remaining_24h, len(candidates))
    if limit <= 0:
        _log(f"Limite automático de 24h atingido ({max_24h}).")
        return result

    _log(
        f"Contas configuradas={len(accounts)} | estratégia={_cfg('X_ACCOUNT_STRATEGY', 'PRIMARY_ONLY')} | "
        f"limite rodada={limit} | publicados 24h={ledger['posted_24h']}/{max_24h}"
    )

    processed = 0
    for row_number, row in candidates:
        if processed >= limit:
            break

        event_key = _event_key(row)
        data = _event_data(row)

        existing = ledger["posted_events"].get(event_key)
        if existing:
            value = (
                f"Publicado X (recuperado) em {bot._ts_br()} | "
                f"id={existing.get('tweet_id', '')} | conta={existing.get('account', '')} | chave={event_key[:16]}"
            )
            bot.marcar_publicado(main_ws, row_number, "X", value=value)
            result.recovered += 1
            continue

        text = montar_texto_x(row, event_key)
        text_hash = _sha256_text(text)
        if text_hash in ledger["posted_text_hashes"]:
            _mark_error(main_ws, row_number, "TEXTO_DUPLICADO", f"hash={text_hash[:16]}")
            result.skipped += 1
            _log(f"Linha {row_number}: texto duplicado bloqueado.")
            continue

        if not _claim(main_ws, row_number, event_key):
            result.skipped += 1
            _log(f"Linha {row_number}: não foi possível confirmar a posse do processamento.")
            continue

        account = _select_account(accounts, event_key)
        account_name = getattr(account, "handle", None) or getattr(account, "label", "ACC1")
        ledger_row = _ledger_append(
            ledger_ws=ledger_ws,
            event_key=event_key,
            status="PENDING",
            account=account_name,
            data=data,
            text_hash=text_hash,
            detail=f"run_id={os.getenv('GITHUB_RUN_ID', '')}",
        )

        media_ids = None
        media_hash = ""
        try:
            if bot._x_post_with_image() and not bot.DRY_RUN:
                try:
                    image_buffer = bot._build_image_from_row(row)
                    image_bytes = image_buffer.getvalue()
                    media_hash = _sha256_bytes(image_bytes)
                    if media_hash in ledger["posted_media_hashes"]:
                        _log(
                            f"Linha {row_number}: imagem idêntica a uma já publicada; "
                            "seguindo automaticamente somente com texto."
                        )
                        media_hash = ""
                    else:
                        image_buffer.seek(0)
                        media = account.api_v1.media_upload(
                            filename=f"resultado-{event_key[:12]}.png",
                            file=image_buffer,
                        )
                        media_ids = [media.media_id_string]
                except tweepy.TweepyException:
                    raise
                except Exception as image_exc:
                    _log(f"Linha {row_number}: geração local da imagem falhou; publicando texto. Erro: {image_exc}")
                    media_ids = None
                    media_hash = ""

            if bot.DRY_RUN:
                fake_id = f"DRY-{event_key[:12]}"
                _log(f"DRY_RUN | {account_name} | {fake_id}\n{text}")
                _ledger_update(
                    ledger_ws,
                    ledger_row,
                    "DRY_RUN",
                    tweet_id=fake_id,
                    media_hash=media_hash,
                    detail="Nenhum post real foi enviado.",
                )
                _release_claim(main_ws, row_number)
                result.skipped += 1
                processed += 1
                continue

            response = account.client_v2.create_tweet(
                text=text,
                media_ids=media_ids,
            )
            tweet_id = str(response.data["id"])
            _ledger_update(
                ledger_ws,
                ledger_row,
                "POSTED",
                tweet_id=tweet_id,
                media_hash=media_hash,
                detail=f"Publicado automaticamente em {account_name}",
            )
            bot.marcar_publicado(
                main_ws,
                row_number,
                "X",
                value=(
                    f"Publicado X via {bot.BOT_ORIGEM} em {bot._ts_br()} | "
                    f"id={tweet_id} | conta={account_name} | chave={event_key[:16]}"
                ),
            )
            ledger["posted_events"][event_key] = {"tweet_id": tweet_id, "account": account_name}
            ledger["posted_text_hashes"].add(text_hash)
            if media_hash:
                ledger["posted_media_hashes"].add(media_hash)
            result.published += 1
            processed += 1
            _log(f"OK | linha={row_number} | conta={account_name} | tweet_id={tweet_id}")

        except Exception as exc:
            status = _http_status(exc)
            detail = _exception_detail(exc)
            result.errors += 1
            processed += 1
            _log(f"ERRO | linha={row_number} | status={status} | {detail}")

            if status in {400, 422}:
                _ledger_update(ledger_ws, ledger_row, "REJECTED", media_hash=media_hash, detail=detail)
                _mark_error(main_ws, row_number, str(status), detail)
                continue

            _release_claim(main_ws, row_number)

            if status in {401, 403}:
                reason = f"X bloqueou autenticação/permissão ({status}): {detail}"
                _ledger_update(ledger_ws, ledger_row, "AUTH_POLICY_BLOCK", media_hash=media_hash, detail=detail)
                _open_circuit(state_ws, reason, _now() + timedelta(hours=circuit_hours))
                result.circuit_opened = True
                result.circuit_reason = reason
                print(f"::error title=Automação do X suspensa::{reason}", flush=True)
                break

            if status == 429:
                until = _rate_reset(exc)
                reason = f"Limite da API do X atingido: {detail}"
                _ledger_update(ledger_ws, ledger_row, "RATE_LIMIT", media_hash=media_hash, detail=detail)
                _open_circuit(state_ws, reason, until)
                result.circuit_opened = True
                result.circuit_reason = reason
                print(f"::warning title=Limite da API do X::{reason}", flush=True)
                break

            if status and status >= 500:
                reason = f"Falha temporária da API do X ({status}): {detail}"
                _ledger_update(ledger_ws, ledger_row, "TEMP_ERROR", media_hash=media_hash, detail=detail)
                _open_circuit(state_ws, reason, _now() + timedelta(minutes=30))
                result.circuit_opened = True
                result.circuit_reason = reason
                break

            reason = f"Falha não classificada no X: {detail}"
            _ledger_update(ledger_ws, ledger_row, "UNKNOWN_ERROR", media_hash=media_hash, detail=detail)
            _open_circuit(state_ws, reason, _now() + timedelta(minutes=30))
            result.circuit_opened = True
            result.circuit_reason = reason
            break

        if result.published < limit:
            time.sleep(pause)

    _log(
        f"Resumo: publicados={result.published} | recuperados={result.recovered} | "
        f"ignorados={result.skipped} | erros={result.errors}"
    )
    return result
