# -*- coding: utf-8 -*-
"""Publicação automática do mesmo evento em contas X distintas.

Cada conta recebe uma versão editorial e uma composição visual próprias. O
controle de idempotência usa evento + conta; a segunda conta é escalonada para
não publicar simultaneamente com a primeira.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import time
from datetime import timedelta
from typing import Any, Dict, List, Sequence, Set, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import bot
import x_publisher as base


def _label(account: Any) -> str:
    return (getattr(account, "label", None) or "ACC").strip().upper()


def _name(account: Any) -> str:
    return getattr(account, "handle", None) or _label(account)


def _scoped_key(event_key: str, account_label: str) -> str:
    return hashlib.sha256(f"{event_key}|{account_label}".encode("utf-8")).hexdigest()


def _parse_detail(detail: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in (detail or "").split("|"):
        if "=" in part:
            key, value = part.split("=", 1)
            out[key.strip().lower()] = value.strip()
    return out


def _detail(event_key: str, account_label: str, profile: int, extra: str = "") -> str:
    parts = [
        f"base={event_key}",
        f"account_label={account_label}",
        f"profile={profile}",
        f"run_id={os.getenv('GITHUB_RUN_ID', '')}",
    ]
    if extra:
        parts.append(extra)
    return "|".join(parts)


def _snapshot(ledger_ws: Any) -> Dict[str, Any]:
    values = ledger_ws.get_all_values()
    posted_keys: Set[str] = set()
    posted_by_base: Dict[str, Set[str]] = {}
    tweet_ids: Dict[str, Dict[str, str]] = {}
    first_post: Dict[str, Any] = {}
    legacy: Set[str] = set()
    text_hashes: Set[str] = set()
    media_hashes: Set[str] = set()
    posted_24h = 0
    cutoff = base._now() - timedelta(hours=24)

    for row in values[1:]:
        key = (row[0] if len(row) > 0 else "").strip()
        status = (row[1] if len(row) > 1 else "").strip().upper()
        tweet_id = (row[2] if len(row) > 2 else "").strip()
        text_hash = (row[7] if len(row) > 7 else "").strip()
        media_hash = (row[8] if len(row) > 8 else "").strip()
        created = base._parse_iso((row[10] if len(row) > 10 else "").strip())
        detail = _parse_detail((row[11] if len(row) > 11 else "").strip())
        if status != "POSTED":
            continue
        if key:
            posted_keys.add(key)
        if text_hash:
            text_hashes.add(text_hash)
        if media_hash:
            media_hashes.add(media_hash)
        if created and created >= cutoff:
            posted_24h += 1

        event_key = detail.get("base", "")
        account_label = detail.get("account_label", "").upper()
        if event_key and account_label:
            posted_by_base.setdefault(event_key, set()).add(account_label)
            tweet_ids.setdefault(event_key, {})[account_label] = tweet_id
            if created and (event_key not in first_post or created < first_post[event_key]):
                first_post[event_key] = created
        elif key:
            legacy.add(key)

    return {
        "posted_keys": posted_keys,
        "posted_by_base": posted_by_base,
        "tweet_ids": tweet_ids,
        "first_post": first_post,
        "legacy": legacy,
        "text_hashes": text_hashes,
        "media_hashes": media_hashes,
        "posted_24h": posted_24h,
    }


def _status_candidate(status: str, ttl: int) -> bool:
    status = bot._strip_invisible(status)
    if not status or status.startswith("PENDENTE_X_CONTAS|"):
        return True
    return status.startswith("PROCESSANDO_X|") and base._claim_is_stale(status, ttl)


def _candidates(ws: Any) -> List[Tuple[int, List[str]]]:
    rows = ws.get_all_values()
    status_col = base._status_column(ws)
    ttl = base._cfg_int("X_CLAIM_TTL_MINUTES", 60, 10, 1440)
    found = []
    for row_number, row in enumerate(rows[1:], start=2):
        status = row[status_col - 1] if len(row) >= status_col else ""
        if _status_candidate(status, ttl) and bot._row_has_min_payload(row):
            priority = 0 if str(status).startswith("PENDENTE_X_CONTAS|") else 1
            found.append((priority, row_number, row))
    found.sort(key=lambda item: (item[0], item[1]))
    return [(row_number, row) for _, row_number, row in found]


def _mark_pending(ws: Any, row_number: int, pending: Sequence[str], complete: Sequence[str]) -> None:
    value = (
        f"PENDENTE_X_CONTAS|faltam={','.join(pending) or '-'}|"
        f"concluidas={','.join(complete) or '-'}|{base._iso()}"
    )
    ws.update_cell(row_number, base._status_column(ws), value[:500])


def _mark_complete(
    ws: Any,
    row_number: int,
    event_key: str,
    labels: Sequence[str],
    tweet_ids: Dict[str, str],
    recovered: bool = False,
) -> None:
    ids = ",".join(f"{label}:{tweet_ids.get(label, '')}" for label in labels)
    prefix = "Publicado X (recuperado)" if recovered else "Publicado X"
    bot.marcar_publicado(
        ws,
        row_number,
        "X",
        value=(
            f"{prefix} em {len(labels)} conta(s) via {bot.BOT_ORIGEM} em {bot._ts_br()} | "
            f"{ids[:260]} | chave={event_key[:16]}"
        ),
    )


def _weighted_length(text: str) -> int:
    return base._weighted_length(text)


def _fit(parts: List[str]) -> str:
    text = "\n".join(part for part in parts if part).strip()
    if _weighted_length(text) <= base.X_LIMIT:
        return text
    without_tag = [part for part in parts if not part.startswith("#")]
    text = "\n".join(part for part in without_tag if part).strip()
    if _weighted_length(text) <= base.X_LIMIT:
        return text
    without_link = [part for part in without_tag if not re.match(r"^(Detalhes|Página completa|Consulta):", part)]
    return "\n".join(part for part in without_link if part).strip()[: base.X_LIMIT]


def montar_texto(row: Sequence[str], event_key: str, account_label: str, profile: int) -> str:
    data = base._event_data(row)
    loteria = data["loteria"] or "Loteria"
    concurso = data["concurso"] or "sem número"
    date = data["data"] or "data informada na publicação"
    result = base._trim_result(data["numeros"], 145)
    source = base._cfg("X_SOURCE_LABEL", "Fonte: Loterias CAIXA")
    disclosure = base._cfg("X_DISCLOSURE_TEXT", "Atualização automática informativa.")
    seed = int(hashlib.sha256(f"{event_key}|{account_label}".encode()).hexdigest()[:8], 16)

    families = [
        [
            f"🎯 {loteria} — concurso {concurso}\nResultado: {result}\nSorteio de {date}.",
            f"✅ Resultado confirmado: {loteria} {concurso}\nNúmeros apurados: {result}\nData: {date}.",
            f"📌 {loteria} | Concurso {concurso}\nResultado: {result}\nReferência: {date}.",
        ],
        [
            f"📊 Painel do concurso {concurso}\n{loteria} • {date}\nResultado no painel: {result}",
            f"🔎 Resumo visual da {loteria}\nConcurso {concurso}, realizado em {date}.\nResultado: {result}",
            f"ℹ️ Atualização do concurso {concurso}\nModalidade: {loteria}\n{date} • {result}",
        ],
        [
            f"🗂️ Boletim de resultados\n{loteria}, concurso {concurso}\n{date} • {result}",
            f"🧾 Registro do sorteio\n{loteria} {concurso}\nData: {date}\nResultado: {result}",
            f"📍 Concurso atualizado\n{loteria}: {concurso}\nResultado de {date}: {result}",
        ],
    ]
    body = families[profile % len(families)][seed % 3]
    link = ""
    if base._cfg_bool("X_INCLUDE_LINK", True) and data["url"]:
        labels = ["Detalhes", "Página completa", "Consulta"]
        link = f"{labels[profile % len(labels)]}: {data['url']}"
    tag = base._hashtag(loteria) if base._cfg_bool("X_INCLUDE_HASHTAG", True) else ""
    return _fit([body, source, disclosure, link, tag])


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _accent(account_label: str, profile: int) -> Tuple[int, int, int]:
    colors = [(255, 211, 0), (69, 205, 255), (255, 120, 180), (120, 235, 150)]
    seed = int(hashlib.sha256(account_label.encode()).hexdigest()[:4], 16)
    return colors[(seed + profile) % len(colors)]


def _classic(base_image: Image.Image, data: Dict[str, str], label: str, profile: int) -> Image.Image:
    accent = _accent(label, profile)
    canvas = Image.new("RGB", (1080, 1080), (18, 20, 31))
    card = ImageOps.fit(base_image, (1010, 1010), method=Image.Resampling.LANCZOS)
    card = ImageOps.expand(card, border=6, fill=accent)
    canvas.paste(card, ((1080 - card.width) // 2, (1080 - card.height) // 2))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((42, 42, 430, 104), radius=20, fill=(18, 20, 31), outline=accent, width=4)
    draw.text((60, 73), "RESULTADO CONFIRMADO", font=_font(29, True), fill="white", anchor="lm")
    return canvas


def _panel(base_image: Image.Image, data: Dict[str, str], label: str, profile: int) -> Image.Image:
    accent = _accent(label, profile)
    canvas = Image.new("RGB", (1080, 1080), (13, 17, 30))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1080, 132), fill=(22, 28, 48))
    draw.rectangle((0, 0, 24, 1080), fill=accent)
    draw.text((70, 50), "PAINEL DO CONCURSO", font=_font(46, True), fill="white")
    draw.text(
        (72, 104),
        f"{data['loteria']} • Concurso {data['concurso']}"[:55],
        font=_font(28),
        fill=accent,
        anchor="lm",
    )
    card = ImageOps.fit(base_image, (850, 850), method=Image.Resampling.LANCZOS)
    shadow = Image.new("RGBA", (890, 890), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((18, 18, 872, 872), radius=38, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    canvas.paste(shadow, (112, 153), shadow)
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, card.width, card.height), radius=30, fill=255)
    canvas.paste(card, (115, 150), mask)
    draw.rounded_rectangle((115, 1018, 965, 1060), radius=18, fill=(22, 28, 48))
    footer = f"Sorteio: {data['data']} • Atualização automática"
    draw.text((540, 1039), footer[:75], font=_font(24, True), fill=(238, 240, 246), anchor="mm")
    return canvas


def _bulletin(base_image: Image.Image, data: Dict[str, str], label: str, profile: int) -> Image.Image:
    accent = _accent(label, profile)
    canvas = Image.new("RGB", (1080, 1080), (245, 246, 249))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1080, 165), fill=(23, 27, 44))
    draw.text((64, 62), "BOLETIM DE RESULTADOS", font=_font(44, True), fill="white")
    draw.text((64, 125), f"{data['loteria']} • {data['data']}"[:62], font=_font(28), fill=accent, anchor="lm")
    card = ImageOps.fit(base_image, (820, 820), method=Image.Resampling.LANCZOS)
    canvas.paste(ImageOps.expand(card, border=10, fill="white"), (120, 190))
    draw.rectangle((0, 1030, 1080, 1080), fill=accent)
    draw.text((540, 1055), f"CONCURSO {data['concurso']}", font=_font(28, True), fill=(18, 20, 31), anchor="mm")
    return canvas


def gerar_imagem(row: Sequence[str], account_label: str, profile: int) -> io.BytesIO:
    source = bot._build_image_from_row(row)
    source.seek(0)
    base_image = Image.open(source).convert("RGB")
    data = base._event_data(row)
    image = [_classic, _panel, _bulletin][profile % 3](base_image, data, account_label, profile)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def _accounts(accounts: Sequence[Any], event_key: str) -> List[Any]:
    # O projeto exige todas as contas com material distinto. A variável abaixo
    # permite desativar somente em uma emergência operacional.
    if base._cfg_bool("X_PUBLISH_ALL_ACCOUNTS_DISTINCT", True):
        return list(accounts)
    strategy = base._cfg("X_ACCOUNT_STRATEGY", "ALL_DISTINCT").upper()
    if strategy == "PRIMARY_ONLY":
        return [accounts[0]]
    if strategy == "ROUND_ROBIN":
        return [accounts[int(event_key[:8], 16) % len(accounts)]]
    return list(accounts)


def _eligible(event_key: str, index: int, snapshot: Dict[str, Any], stagger: int) -> bool:
    if index == 0 or stagger <= 0:
        return True
    first = snapshot["first_post"].get(event_key)
    return bool(first and base._now() >= first + timedelta(seconds=stagger * index))


def publicar_x_automatico(main_ws: Any) -> base.XRunResult:
    result = base.XRunResult()
    ledger_ws = base._ledger_ws(main_ws)
    state_ws = base._state_ws(main_ws)

    circuit_open, circuit_detail = base._circuit_status(state_ws)
    if circuit_open:
        result.circuit_opened = True
        result.circuit_reason = circuit_detail
        base._log(f"Publicação suspensa automaticamente: {circuit_detail}")
        return result

    all_accounts = bot._build_x_accounts()
    candidates = _candidates(main_ws)
    if not candidates:
        return result

    snapshot = _snapshot(ledger_ws)
    max_run = base._cfg_int("X_MAX_PUBLICACOES_RODADA", 3, 1, 10)
    max_24h = base._cfg_int("X_MAX_PUBLICACOES_24H", 20, 1, 100)
    pause = base._cfg_float("X_PAUSA_ENTRE_POSTS", 60.0, 10.0, 900.0)
    stagger = base._cfg_int("X_ACCOUNT_STAGGER_SECONDS", 900, 0, 86400)
    circuit_hours = base._cfg_int("X_CIRCUIT_HOURS", 24, 1, 168)
    require_distinct_media = base._cfg_bool("X_REQUIRE_DISTINCT_MEDIA", True)
    remaining = max(0, max_24h - snapshot["posted_24h"])
    sent_run = 0
    stop = False

    for row_number, row in candidates:
        if stop or sent_run >= max_run or remaining <= 0:
            break
        event_key = base._event_key(row)
        data = base._event_data(row)
        accounts = _accounts(all_accounts, event_key)
        labels = [_label(account) for account in accounts]

        if event_key in snapshot["legacy"]:
            _mark_complete(main_ws, row_number, event_key, labels, {}, recovered=True)
            result.recovered += 1
            continue

        complete = set(snapshot["posted_by_base"].get(event_key, set()))
        tweet_ids = dict(snapshot["tweet_ids"].get(event_key, {}))
        if all(label in complete for label in labels):
            _mark_complete(main_ws, row_number, event_key, labels, tweet_ids, recovered=True)
            result.recovered += 1
            continue

        if not base._claim(main_ws, row_number, event_key):
            result.skipped += 1
            continue

        row_error = False
        for profile, account in enumerate(accounts):
            if sent_run >= max_run or remaining <= 0:
                break
            label = _label(account)
            if label in complete:
                continue
            if not _eligible(event_key, profile, snapshot, stagger):
                continue

            scoped_key = _scoped_key(event_key, label)
            if scoped_key in snapshot["posted_keys"]:
                complete.add(label)
                continue

            text = montar_texto(row, event_key, label, profile)
            text_hash = base._sha256_text(text)
            if text_hash in snapshot["text_hashes"]:
                base._mark_error(main_ws, row_number, "TEXTO_DUPLICADO", f"conta={label}|hash={text_hash[:16]}")
                result.errors += 1
                row_error = True
                break

            ledger_row = base._ledger_append(
                ledger_ws,
                scoped_key,
                "PENDING",
                _name(account),
                data,
                text_hash,
                detail=_detail(event_key, label, profile),
            )
            media_hash = ""
            media_ids = None

            try:
                if bot._x_post_with_image() and not bot.DRY_RUN:
                    try:
                        image = gerar_imagem(row, label, profile)
                        media_hash = base._sha256_bytes(image.getvalue())
                    except Exception as image_exc:
                        detail = f"Falha ao gerar imagem distinta: {image_exc}"
                        base._ledger_update(
                            ledger_ws,
                            ledger_row,
                            "IMAGE_ERROR",
                            detail=_detail(event_key, label, profile, detail),
                        )
                        base._mark_error(main_ws, row_number, "IMAGEM", f"conta={label}|{detail}")
                        result.errors += 1
                        row_error = True
                        break

                    if media_hash in snapshot["media_hashes"]:
                        detail = f"Imagem repetida em {label}; hash={media_hash[:16]}"
                        base._ledger_update(
                            ledger_ws,
                            ledger_row,
                            "MEDIA_DUPLICATE",
                            media_hash=media_hash,
                            detail=_detail(event_key, label, profile, detail),
                        )
                        if require_distinct_media:
                            base._mark_error(main_ws, row_number, "MIDIA_DUPLICADA", detail)
                            result.errors += 1
                            row_error = True
                            break
                        media_hash = ""
                    else:
                        image.seek(0)
                        media = account.api_v1.media_upload(
                            filename=f"resultado-{label.lower()}-{event_key[:10]}.png",
                            file=image,
                        )
                        media_ids = [media.media_id_string]

                if bot.DRY_RUN:
                    fake_id = f"DRY-{label}-{scoped_key[:10]}"
                    base._log(f"DRY_RUN | {_name(account)} | perfil={profile}\n{text}")
                    base._ledger_update(
                        ledger_ws,
                        ledger_row,
                        "DRY_RUN",
                        tweet_id=fake_id,
                        media_hash=media_hash,
                        detail=_detail(event_key, label, profile, "dry_run=true"),
                    )
                    result.skipped += 1
                    continue

                response = account.client_v2.create_tweet(text=text, media_ids=media_ids)
                tweet_id = str(response.data["id"])
                base._ledger_update(
                    ledger_ws,
                    ledger_row,
                    "POSTED",
                    tweet_id=tweet_id,
                    media_hash=media_hash,
                    detail=_detail(event_key, label, profile, f"published_to={_name(account)}"),
                )
                complete.add(label)
                tweet_ids[label] = tweet_id
                snapshot["posted_keys"].add(scoped_key)
                snapshot["posted_by_base"].setdefault(event_key, set()).add(label)
                snapshot["tweet_ids"].setdefault(event_key, {})[label] = tweet_id
                snapshot["text_hashes"].add(text_hash)
                if media_hash:
                    snapshot["media_hashes"].add(media_hash)
                if event_key not in snapshot["first_post"]:
                    snapshot["first_post"][event_key] = base._now()
                result.published += 1
                sent_run += 1
                remaining -= 1
                base._log(f"OK | linha={row_number} | conta={_name(account)} | perfil={profile} | id={tweet_id}")
                if sent_run < max_run and remaining > 0:
                    time.sleep(pause)

            except Exception as exc:
                status = base._http_status(exc)
                detail = base._exception_detail(exc)
                result.errors += 1
                row_error = True
                base._log(f"ERRO | linha={row_number} | conta={label} | status={status} | {detail}")

                if status in {400, 422}:
                    base._ledger_update(
                        ledger_ws,
                        ledger_row,
                        "REJECTED",
                        media_hash=media_hash,
                        detail=_detail(event_key, label, profile, detail),
                    )
                    base._mark_error(main_ws, row_number, str(status), f"conta={label}|{detail}")
                    break

                base._release_claim(main_ws, row_number)
                if status in {401, 403}:
                    reason = f"X bloqueou autenticação/permissão de {label} ({status}): {detail}"
                    base._ledger_update(ledger_ws, ledger_row, "AUTH_POLICY_BLOCK", media_hash=media_hash, detail=detail)
                    base._open_circuit(state_ws, reason, base._now() + timedelta(hours=circuit_hours))
                    result.circuit_opened = True
                    result.circuit_reason = reason
                    stop = True
                    break
                if status == 429:
                    reason = f"Limite da API do X em {label}: {detail}"
                    base._ledger_update(ledger_ws, ledger_row, "RATE_LIMIT", media_hash=media_hash, detail=detail)
                    base._open_circuit(state_ws, reason, base._rate_reset(exc))
                    result.circuit_opened = True
                    result.circuit_reason = reason
                    stop = True
                    break
                reason = f"Falha temporária no X em {label}: {detail}"
                base._ledger_update(ledger_ws, ledger_row, "TEMP_ERROR", media_hash=media_hash, detail=detail)
                base._open_circuit(state_ws, reason, base._now() + timedelta(minutes=30))
                result.circuit_opened = True
                result.circuit_reason = reason
                stop = True
                break

        complete_ordered = [label for label in labels if label in complete]
        pending = [label for label in labels if label not in complete]
        if not pending and not row_error:
            _mark_complete(main_ws, row_number, event_key, labels, tweet_ids)
        elif row_error:
            current = str(main_ws.cell(row_number, base._status_column(main_ws)).value or "")
            if not current.startswith("ERRO_X_"):
                base._mark_error(
                    main_ws,
                    row_number,
                    "PARCIAL",
                    f"concluidas={','.join(complete_ordered)}|faltam={','.join(pending)}",
                )
        else:
            _mark_pending(main_ws, row_number, pending, complete_ordered)
            result.skipped += 1

    base._log(
        f"Resumo multicontas: publicados={result.published} | recuperados={result.recovered} | "
        f"ignorados={result.skipped} | erros={result.errors}"
    )
    return result
