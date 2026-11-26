from __future__ import annotations

import os
from datetime import timedelta

import pending_alert_fix_v27 as base



# V34: chamada narrada independente + recuperação da transmissão no mesmo URL.
from pathlib import Path
import tempfile
from PIL import Image, ImageOps
import daily_video_v19 as video
from youtube_thumbnail_v24 import gerar_capa_live

RESULTS_URL = "https://www.portalsimonsports.com/search/label/Loterias%20Caixa?m=1"


def _broadcasts(token, date):
    items = []
    page = None
    while True:
        params = {"part": "id,snippet,status,contentDetails", "mine": "true", "maxResults": 50}
        if page:
            params["pageToken"] = page
        payload = base.live._request("GET", f"{base.live.API}/liveBroadcasts", token=token, params=params)
        for item in payload.get("items", []):
            snippet = item.get("snippet", {})
            if date in snippet.get("title", "") and base.live.LIVE_MARKER in snippet.get("description", ""):
                items.append(item)
        page = payload.get("nextPageToken")
        if not page:
            return items


def _credentials(cofre_get, cofre_cache):
    for account in base.listar_contas_youtube(cofre_cache):
        get = lambda key, default="": base._cofre_get_safe(cofre_get, "YOUTUBE", key, conta=account, default=default)
        if not all(get(k) for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN")):
            continue
        yield account, base.get_access_token(get("CLIENT_ID"), get("CLIENT_SECRET"), get("REFRESH_TOKEN")), get("PRIVACY_STATUS", "public") or "public"


def _scheduled_hour():
    return max(0, min(23, int(os.getenv("YOUTUBE_DAILY_LIVE_SCHEDULE_HOUR", "21"))))


def _find_call(token, marker):
    api = base.live.API
    payload = base.live._request("GET", f"{api}/channels", token=token,
        params={"part": "contentDetails", "mine": "true"})
    for channel in payload.get("items", []):
        playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
        page = None
        # A chamada pertence ao dia atual. Inspeciona até 250 uploads recentes.
        for _ in range(5):
            params = {"part": "snippet", "playlistId": playlist, "maxResults": 50}
            if page:
                params["pageToken"] = page
            result = base.live._request("GET", f"{api}/playlistItems", token=token, params=params)
            for item in result.get("items", []):
                sn = item.get("snippet", {})
                if marker in sn.get("description", ""):
                    return sn.get("resourceId", {}).get("videoId", "")
            ids = [item.get("snippet", {}).get("resourceId", {}).get("videoId", "") for item in result.get("items", [])]
            ids = [vid for vid in ids if vid]
            if ids:
                details = base.live._request("GET", f"{api}/videos", token=token, params={"part": "snippet", "id": ",".join(ids)})
                for item in details.get("items", []):
                    if marker in item.get("snippet", {}).get("tags", []):
                        return item["id"]
            page = result.get("nextPageToken")
            if not page:
                break
    return ""


def _render_call(date, targets, prize, hour):
    directory = Path("output")
    directory.mkdir(exist_ok=True)
    cover = Path(gerar_capa_live(date, targets, prize_highlight=prize or {}))
    output = directory / ("chamada_" + date.replace("/", "-") + "_v34.mp4")
    names = "; ".join(f"{display}, concurso {contest}" for _, display, contest in targets)
    speech = (f"Olá! Portal Simon Sports. Hoje, {date}, temos os seguintes concursos previstos: "
              f"{names}. Acompanhe os resultados no nosso canal. "
              "Inscreva-se, compartilhe e ative as notificações. "
              "Confira também os resultados completos no Portal Simon Sports.")
    duration = max(45.0, len(speech.split()) * 0.65 + 8.0)
    voice = video.select_single_voice({"concurso": date, "loteria": "Resultados Diários"})
    if not str(voice).startswith("pt-BR-"):
        raise RuntimeError("Voz fora do padrão pt-BR; chamada bloqueada.")
    with tempfile.TemporaryDirectory(prefix="chamada-v34-") as folder:
        temp = Path(folder)
        with Image.open(cover) as source:
            frame = ImageOps.pad(source.convert("RGB"), (1920, 1080), color=(0, 18, 44))
        music, audio = temp / "music.wav", temp / "audio.wav"
        video.write_soundtrack(music, duration, "Resultados Diários", date, 0, duration - 5)
        video.synthesize_custom_segments({"data": date}, duration,
            [video.SpeechSegment(0.5, voice, speech, 1.0, video.FULL_RATE, "opening")],
            music, audio, primary_voice=voice)
        video._write_concat_video([(frame, duration)], audio, output, duration, temp)
    return str(output), str(cover)


def _ensure_call(date, targets, prize, cofre_get, cofre_cache, timezone):
    marker = "PSS_CHAMADA_V34_" + date.replace("/", "")
    hour = _scheduled_hour()
    now = base.queue._now_in_timezone(timezone)
    if now.hour < 7 or now.hour >= hour:
        return
    package = None
    for account, token, privacy in _credentials(cofre_get, cofre_cache):
        try:
            if _find_call(token, marker):
                continue
            broadcasts = _broadcasts(token, date)
            live_url = next((base.build_watch_url(b["id"]) for b in broadcasts
                if b.get("status", {}).get("lifeCycleStatus") not in ("complete", "revoked")), "")
            if package is None:
                package = _render_call(date, targets, prize, hour)
            description = "\n".join([f"Concursos previstos para {date}:", *[
                f"{display} — concurso {contest}" for _, display, contest in targets],
                "", "Inscreva-se e ative as notificações.",
                f"Transmissão programada: {hour:02d}h (Brasília).",
                live_url, "", RESULTS_URL, "", marker])
            vid = base.live.upload_video(access_token=token, video_path=package[0],
                title=f"Hoje tem sorteio! Loterias Caixa | {date} | Portal SimonSports",
                description=description, tags=["Loterias Caixa", "Portal SimonSports"],
                category_id="24", privacy_status=privacy)
            base.live.upload_thumbnail(token, vid, package[1])
            base.queue._log(f"[{account}] Chamada narrada publicada: {base.build_watch_url(vid)}")
        except Exception as error:
            base.queue._log(f"[{account}] Chamada narrada falhou: {type(error).__name__}")


def _existing_live_state(date, cofre_get, cofre_cache):
    active, completed = [], []
    for account, token, _privacy in _credentials(cofre_get, cofre_cache):
        for item in _broadcasts(token, date):
            state = item.get("status", {}).get("lifeCycleStatus", "")
            if state == "complete":
                completed.append(base.build_watch_url(item["id"]))
            elif state != "revoked":
                active.append(base.build_watch_url(item["id"]))
    return active, completed


_original_pending_dates = base._pending_dates


def _pending_dates_recent_only(api_spreadsheet, today: str):
    """Recupera pendências dos últimos 7 dias sem permitir que elas bloqueiem o dia atual."""
    dates = _original_pending_dates(api_spreadsheet, today)
    today_dt = base._date_obj(today)
    if not today_dt:
        return dates
    cutoff = today_dt - timedelta(days=7)
    filtered = []
    for date in dates:
        dt = base._date_obj(date)
        if dt and dt >= cutoff:
            filtered.append(date)
        else:
            base.queue._log(f"{date}: pendência com mais de 7 dias mantida apenas para auditoria.")
    return filtered



def _clean_public_video(token, vid, marker=""):
    """Migra identificadores antigos para tags e corrige URL sem reenviar vídeo."""
    from youtube_description_link_fix_v32 import _fix_description
    from youtube_upload import sanitize_youtube_tags
    import re
    api = base.live.API
    response = base.live._request("GET", f"{api}/videos", token=token, params={"part": "snippet", "id": vid})
    for item in response.get("items", []):
        original = item.get("snippet", {})
        description = original.get("description", "")
        internal = re.findall(r"(?m)^\s*(PSS_(?:RESULTADO|CHAMADA)_[A-Za-z0-9_]+)\s*$", description)
        tags = sanitize_youtube_tags(list(dict.fromkeys(([marker] if marker else []) + internal + original.get("tags", []))))
        cleaned = _fix_description(description)
        if cleaned == description and tags == original.get("tags", []):
            continue
        snippet = {k: original[k] for k in ("title", "categoryId", "defaultLanguage", "defaultAudioLanguage") if k in original}
        snippet.update({"description": cleaned, "tags": tags})
        base.live._request("PUT", f"{api}/videos", token=token, params={"part": "snippet"}, json_body={"id": vid, "snippet": snippet})
        base.queue._log(f"V40 descrição corrigida sem reenviar: {vid}")


def _repair_recent_descriptions(cofre_get, cofre_cache):
    """Corrige publicações anteriores V34/V39 na conta autenticada."""
    import re
    for account, token, _privacy in _credentials(cofre_get, cofre_cache):
        try:
            api = base.live.API
            channels = base.live._request("GET", f"{api}/channels", token=token, params={"part": "contentDetails", "mine": "true"})
            for channel in channels.get("items", []):
                playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
                result = base.live._request("GET", f"{api}/playlistItems", token=token, params={"part": "snippet", "playlistId": playlist, "maxResults": 50})
                for item in result.get("items", []):
                    sn = item.get("snippet", {})
                    description = sn.get("description", "")
                    vid = sn.get("resourceId", {}).get("videoId", "")
                    if vid and (re.search(r"(?m)^\s*PSS_(?:RESULTADO|CHAMADA)_", description) or ("Loterias Caixa" in description and "portalsimonsports.com/search/label/Loterias" in description and RESULTS_URL not in description)):
                        try:
                            _clean_public_video(token, vid)
                        except Exception as exc:
                            base.queue._log(f"[{account}] V40 revisão pendente {vid}: {type(exc).__name__}")
        except Exception as exc:
            base.queue._log(f"[{account}] V40 revisão indisponível: {type(exc).__name__}")


def _publish_regular_results(date, rows, worksheet, daily_index, cofre_get, cofre_cache, config):
    """V39: vídeo normal e Short têm identificadores independentes da transmissão."""
    q = base.queue
    results = [data for _, data in rows]
    if config.dry_run:
        q._log(f"PREVISÃO V39: vídeo normal de resultados {date}, sem upload.")
        return 0
    # Não confundir o replay ou a chamada antecipada com um upload de resultados.
    markers = [str(worksheet.cell(n, daily_index + 1).value or "") for n, _ in rows]
    import re
    import hashlib
    signature = hashlib.sha256("|".join(sorted(
        f"{q._lottery_key(d.get('loteria'))}:{d.get('concurso')}" for d in results
    )).encode()).hexdigest()[:16]
    prefix = "PSS_RESULTADO_V39_" + date.replace("/", "") + "_" + signature
    package = None
    done = []
    need_short = q._special_short(results)
    for account, token, privacy in _credentials(cofre_get, cofre_cache):
        try:
            normal = _find_call(token, prefix + "_NORMAL")
            short = _find_call(token, prefix + "_SHORT") if need_short else ""
            # Reutiliza URLs históricas somente se o vídeo pertence ao canal,
            # tem conteúdo de resultados na descrição e não é replay nem chamada.
            for mark in markers:
                for kind, vid in re.findall(r"(Completo|Short):\s*https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]+)", mark):
                    if (kind == "Completo" and normal) or (kind == "Short" and (short or not need_short)):
                        continue
                    payload = base.live._request("GET", f"{base.live.API}/videos", token=token,
                        params={"part": "snippet,status", "id": vid})
                    channel = base.live._request("GET", f"{base.live.API}/channels", token=token,
                        params={"part": "id", "mine": "true"})
                    mine = {item["id"] for item in channel.get("items", [])}
                    for item in payload.get("items", []):
                        sn = item.get("snippet", {})
                        desc = sn.get("description", "")
                        if sn.get("channelId") not in mine or date not in desc:
                            continue
                        if "PSS_CHAMADA_" in desc or base.live.LIVE_MARKER in desc:
                            continue
                        if not all(q._compact_result(d) in desc for d in results):
                            continue
                        if item.get("status", {}).get("uploadStatus") not in ("processed", "uploaded"):
                            continue
                        if kind == "Completo" and "V22 LIVE" not in mark.upper():
                            normal = vid
                        elif kind == "Short" and need_short:
                            short = vid
            if not normal or (need_short and not short):
                if package is None:
                    package = video.gerar_pacote_diario(results, output_dir="output", gerar_short=need_short)
                for kind in ("NORMAL", "SHORT"):
                    if (kind == "NORMAL" and normal) or (kind == "SHORT" and (short or not need_short)):
                        continue
                    meta = q._metadata(results, "completo" if kind == "NORMAL" else "short")
                    from youtube_description_link_fix_v32 import _fix_description
                    desc = _fix_description(meta["description"])
                    vid = base.live.upload_video(access_token=token,
                        video_path=package["completo" if kind == "NORMAL" else "short"],
                        title=meta["title"], description=desc, tags=[prefix + "_" + kind, *meta["tags"]],
                        category_id=base._cofre_get_safe(cofre_get, "YOUTUBE", "CATEGORY_ID", conta=account, default="24") or "24",
                        privacy_status=privacy)
                    if kind == "NORMAL":
                        normal = vid
                        try:
                            base.live.upload_thumbnail(token, vid, package["poster"])
                        except Exception as exc:
                            q._log(f"[{account}] Capa do vídeo normal pendente: {type(exc).__name__}")
                    else:
                        short = vid
            if normal and (short or not need_short):
                for vid, marker in ((normal, prefix + "_NORMAL"), (short, prefix + "_SHORT")):
                    if vid:
                        try:
                            _clean_public_video(token, vid, marker)
                        except Exception as exc:
                            q._log(f"[{account}] V40 limpeza pendente: {type(exc).__name__}")
                done.append((normal, short))
                q._log(f"[{account}] V39 normal={base.build_watch_url(normal)} short={base.build_watch_url(short) if short else 'não necessário'}")
        except Exception as exc:
            q._log(f"[{account}] V39 publicação independente pendente: {type(exc).__name__}: {exc}")
    accounts = base.listar_contas_youtube(cofre_cache)
    if not done or len(done) != len(accounts):
        return 0
    normal, short = done[0]
    mark = f"Publicado YOUTUBE DIÁRIO V19 V39 | Completo: {base.build_watch_url(normal)}"
    mark += f" | Short: {base.build_watch_url(short)}" if short else " | Short: não necessário"
    q._mark_rows(worksheet, [n for n, _ in rows], daily_index, mark)
    return 1


def _all_result_rows(values, headers, date, targets):
    wanted = {(k, str(n)) for k, _, n in targets}
    found = {}
    for n, row in enumerate(values[1:], start=2):
        try:
            data = base.queue._row_data(row, headers)
            base.queue._validate_video_data(data)
        except Exception:
            continue
        pair = (base.queue._lottery_key(data.get("loteria")), base.cal._contest_key(data.get("concurso")))
        if str(data.get("data") or "").strip() == date and pair in wanted:
            found[pair] = (n, data)
    missing = [display for k, display, contest in targets if (k, str(contest)) not in found]
    if missing:
        return [], missing
    return [found[(k, str(contest))] for k, _, contest in targets], []


def _process_date_decoupled(
    date: str,
    *,
    today: str,
    config,
    worksheet,
    values,
    api_spreadsheet,
    calendar_values,
    history_values,
    cofre_get,
    cofre_cache,
) -> int:
    """Live é somente chamada; resultados usam o publicador normal e independente."""
    is_today = date == today
    if is_today:
        # V33: o calendário da CAIXA pode avançar para o próximo concurso logo após
        # a apuração. Nesse intervalo, dataProximoConcurso deixa de apontar para hoje,
        # embora dataUltimoConcurso já contenha justamente os resultados que precisam
        # ser publicados. Unimos as duas visões para não perder concursos noturnos.
        scheduled_targets = base.cal.targets_for_date(calendar_values, date)
        result_targets = base._last_result_targets(calendar_values, date)
        targets = []
        seen = set()
        for item in list(scheduled_targets) + list(result_targets):
            pair = (item[0], item[2])
            if pair in seen:
                continue
            seen.add(pair)
            targets.append(item)
        if not scheduled_targets and result_targets:
            base.queue._log(
                f"{date}: calendário já avançou; recuperando {len(result_targets)} concurso(s) via dataUltimoConcurso."
            )
    else:
        targets = base._last_result_targets(calendar_values, date)
    if not targets:
        if not is_today and not config.dry_run:
            base._mark_orphan_alert_ignored(api_spreadsheet, date, config.timezone)
        else:
            base.queue._log(f"{date}: sem concursos previstos para chamada/publicação.")
        return 0

    prize_highlight = base.cal.largest_prize_for_date(calendar_values, date, targets) if is_today else {}

    imported = base.cal.history_imported_map(history_values)
    waiting_history = [f"{display} {contest}" for key, display, contest in targets if imported.get(key) != contest]
    if waiting_history and not config.dry_run:
        try:
            inserted = base.caixa_fallback.append_missing_results(
                worksheet,
                values,
                targets,
                expected_date=date,
                log=base.queue._log,
            )
            if inserted:
                values = worksheet.get_all_values()
        except Exception as error:
            base.queue._log(f"Fallback CAIXA {date} falhou: {error}")

    headers = list(values[0])
    daily_column = os.getenv("PUBLICADO_YT_DIARIO_COL", base.queue.DAILY_COLUMN_DEFAULT)
    daily_index = base.queue._ensure_column(worksheet, headers, daily_column)
    rows, missing_rows = _all_result_rows(values, headers, date, targets)

    active_live = []
    completed_live = []
    if is_today and not config.dry_run:
        try:
            active_live, completed_live = _existing_live_state(date, cofre_get, cofre_cache)
            now = base.queue._now_in_timezone(config.timezone)
            if not active_live and not completed_live and now.hour < _scheduled_hour():
                live_urls = base.live.ensure_daily_lives(
                    date,
                    targets,
                    cofre_get,
                    cofre_cache,
                    timezone=config.timezone,
                    prize_highlight=prize_highlight,
                )
                active_live = live_urls
            live_url = (active_live or completed_live or [""])[0]
            base._upsert_alert_status(
                api_spreadsheet,
                date,
                live_url,
                "LIVE_AGENDADA | aguardando resultados" if active_live else "SEM_LIVE_ATIVA",
                config.timezone,
            )
            base.queue._log(f"{date}: Live/chamada independente preparada: {live_url}")
        except Exception as error:
            base._upsert_alert_status(
                api_spreadsheet,
                date,
                "",
                f"ERRO_CHAMADA_NAO_BLOQUEANTE: {type(error).__name__}: {error}"[:4500],
                config.timezone,
            )
            base.queue._log(f"{date}: chamada falhou, mas o fluxo de resultados continuará: {error}")

    # V39: antes dos resultados somente o agendamento da live; nenhum MP4 normal de chamada.
    if not rows:
        if missing_rows == ["JÁ PUBLICADO"]:
            if not config.dry_run:
                base._mark_alert_final(api_spreadsheet, date, config.timezone)
            return 0
        base.queue._log(f"{date}: aguardando resultados para publicação independente: " + ", ".join(missing_rows))
        return 0

    # Verificação explícita do resultado oficial, inclusive na recuperação.
    if not config.dry_run:
        for key, display, contest in targets:
            try:
                official = base.caixa_fallback.fetch_official_result(key, display, contest)
                if not official or official.get("data") != date or not official.get("numeros"):
                    base.queue._log(f"V39 bloqueado: {display} {contest} ainda sem confirmação oficial.")
                    return 0
            except Exception as exc:
                base.queue._log(f"V39 aguardando CAIXA: {display} {contest}: {type(exc).__name__}")
                return 0
    if is_today and active_live and not completed_live and not config.dry_run:
        if base.queue._now_in_timezone(config.timezone).hour >= _scheduled_hour():
            try:
                base.live.publish_day_as_live(
                    date, targets, rows, worksheet, daily_index, cofre_get, cofre_cache,
                    dry_run=False, pause=config.pausa, timezone=config.timezone,
                    prize_highlight=prize_highlight,
                )
            except Exception as error:
                base.queue._log(f"Falha na live; vídeo normal independente continua: {type(error).__name__}")
    result = _publish_regular_results(date, rows, worksheet, daily_index, cofre_get, cofre_cache, config)
    if result:
        base._mark_alert_final(api_spreadsheet, date, config.timezone)
    return result


def processar_resumo_por_calendario_api_v28() -> int:
    """Executa chamada do dia + publicações independentes, recuperando até 7 dias sem bloqueio."""
    base._pending_dates = _pending_dates_recent_only

    config = base.queue.carregar_config()
    client = base.queue._google_client()
    cofre_cache, cofre_get = base.queue._load_cofre(client, config)
    if not config.dry_run:
        _repair_recent_descriptions(cofre_get, cofre_cache)

    main_spreadsheet = client.open_by_key(config.google_sheet_id)
    worksheet = main_spreadsheet.worksheet(config.sheet_tab)
    values = worksheet.get_all_values()
    if not values:
        raise RuntimeError("A planilha principal está vazia.")

    api_sheet_id = os.getenv("YOUTUBE_API_CALENDAR_SHEET_ID", base.cal.API_CALENDAR_SHEET_ID_DEFAULT).strip()
    api_calendar_tab = os.getenv("YOUTUBE_API_CALENDAR_TAB", base.cal.API_CALENDAR_TAB_DEFAULT).strip()
    api_history_tab = os.getenv("YOUTUBE_API_HISTORY_CONFIG_TAB", base.cal.API_HISTORY_CONFIG_TAB_DEFAULT).strip()
    api_spreadsheet = client.open_by_key(api_sheet_id)
    calendar_values = api_spreadsheet.worksheet(api_calendar_tab).get_all_values()
    history_values = api_spreadsheet.worksheet(api_history_tab).get_all_values()

    today = base.cal._today(config.timezone)
    pending = _pending_dates_recent_only(api_spreadsheet, today)
    yesterday = (base._date_obj(today) - timedelta(days=1)).strftime("%d/%m/%Y")
    previous_dates = sorted({d for d in pending if d != today} | {yesterday}, key=base._date_obj)

    published = 0
    for date in previous_dates:
        current_values = worksheet.get_all_values()
        published += _process_date_decoupled(
            date,
            today=today,
            config=config,
            worksheet=worksheet,
            values=current_values,
            api_spreadsheet=api_spreadsheet,
            calendar_values=calendar_values,
            history_values=history_values,
            cofre_get=cofre_get,
            cofre_cache=cofre_cache,
        )

    current_values = worksheet.get_all_values()
    published += _process_date_decoupled(
        today,
        today=today,
        config=config,
        worksheet=worksheet,
        values=current_values,
        api_spreadsheet=api_spreadsheet,
        calendar_values=calendar_values,
        history_values=history_values,
        cofre_get=cofre_get,
        cofre_cache=cofre_cache,
    )
    return published
