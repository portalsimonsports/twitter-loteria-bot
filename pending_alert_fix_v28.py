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
    # V41: narração pt-BR aprovada, sem vinheta nem música inicial.
    import subprocess
    import sys
    with tempfile.TemporaryDirectory(prefix="chamada-v41-") as folder:
        temp = Path(folder)
        with Image.open(cover) as source:
            frame = ImageOps.pad(source.convert("RGB"), (1920, 1080), color=(0, 18, 44))
        speech_audio = temp / "speech.mp3"
        audio = temp / "audio.wav"
        subprocess.run([sys.executable, "-m", "edge_tts", "--voice", "pt-BR-FranciscaNeural",
            "--text", speech, "--write-media", str(speech_audio)], check=True, timeout=180)
        length = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(speech_audio)], text=True))
        if length < 5:
            raise RuntimeError("Narração ausente ou incompleta")
        duration = length + 18.0
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(speech_audio),
            "-af", "adelay=10000:all=1,apad", "-t", str(duration), "-ar", "44100",
            "-ac", "2", str(audio)], check=True)
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


def _transmit_narrated_call(date, targets, prize, cofre_get, cofre_cache):
    """V41: transmite a chamada no broadcast já existente, sem criar outro."""
    package = None
    import time
    import subprocess
    for account, token, _privacy in _credentials(cofre_get, cofre_cache):
        for item in _broadcasts(token, date):
            state = item.get("status", {}).get("lifeCycleStatus", "")
            if state not in ("created", "ready", "testing"):
                continue
            vid = item["id"]
            try:
                stream_id = item.get("contentDetails", {}).get("boundStreamId")
                if not stream_id:
                    stream_id = base.live._create_stream(token, date)["id"]
                    base.live._bind(token, vid, stream_id)
                if package is None:
                    package = _render_call(date, targets, prize, _scheduled_hour())
                stream = base.live._stream_details(token, stream_id)
                process = base.live._start_ffmpeg(package[0], base.live._rtmp_target(stream))
                try:
                    base.live._wait_stream_active(token, stream_id, timeout_seconds=45)
                    base.live._transition(token, vid, "live")
                    if process.wait(timeout=300) != 0:
                        raise RuntimeError("FFmpeg falhou")
                    time.sleep(3)
                    base.live._transition(token, vid, "complete")
                    base.queue._log(f"V41 chamada narrada concluída no mesmo URL: {base.build_watch_url(vid)}")
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
            except Exception as exc:
                base.queue._log(f"V41 chamada narrada pendente: {type(exc).__name__}")


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
        confirmed = base.live._request("GET", f"{api}/videos", token=token, params={"part": "snippet", "id": vid})
        if not any(RESULTS_URL in x.get("snippet", {}).get("description", "").splitlines() for x in confirmed.get("items", [])):
            raise RuntimeError("V46: URL integral não confirmada pelo YouTube")
        base.queue._log(f"V46 descrição corrigida e confirmada sem reenviar: {vid} | {RESULTS_URL}")


def _repair_recent_descriptions(cofre_get, cofre_cache):
    """V46: read actual video snippets, repair links without uploading again."""
    import re
    for account, token, _privacy in _credentials(cofre_get, cofre_cache):
        try:
            api = base.live.API
            channels = base.live._request("GET", f"{api}/channels", token=token, params={"part": "contentDetails", "mine": "true"})
            for channel in channels.get("items", []):
                playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
                page = None
                for _ in range(3):
                    params = {"part": "snippet", "playlistId": playlist, "maxResults": 50}
                    if page:
                        params["pageToken"] = page
                    result = base.live._request("GET", f"{api}/playlistItems", token=token, params=params)
                    ids = [item.get("snippet", {}).get("resourceId", {}).get("videoId", "") for item in result.get("items", [])]
                    ids = [vid for vid in ids if vid]
                    if ids:
                        details = base.live._request("GET", f"{api}/videos", token=token, params={"part": "snippet", "id": ",".join(ids)})
                        for item in details.get("items", []):
                            sn = item.get("snippet", {})
                            desc, title = sn.get("description", ""), sn.get("title", "")
                            tags = sn.get("tags", [])
                            is_lottery = any(str(t).startswith(("PSS_RESULTADO_", "PSS_CHAMADA_")) for t in tags) or bool(re.search(r"(?i)loterias? caixa|lotof[aá]cil|mega[- ]sena|timemania|dia de sorte|dupla sena|lotomania|super sete|milion[aá]ria|loteria federal|\bquina\b|\bloteca\b", title))
                            if not is_lottery:
                                continue
                            vid = item["id"]
                            broken = any("portalsimo" in line.lower() and ("..." in line or "…" in line or (RESULTS_URL not in line and ("outros resultados" in line.lower() or "/search/label/loterias" in line.lower()))) for line in desc.splitlines())
                            try:
                                if broken or RESULTS_URL not in desc.splitlines() or re.search(r"(?m)^\s*PSS_(?:RESULTADO|CHAMADA)_", desc):
                                    _clean_public_video(token, vid)
                                else:
                                    base.queue._log(f"V46 descrição API confirmada: {vid} | {RESULTS_URL}")
                            except Exception as exc:
                                base.queue._log(f"V46 descrição pendente {vid}: {type(exc).__name__}")
                    page = result.get("nextPageToken")
                    if not page:
                        break
        except Exception as exc:
            base.queue._log(f"V46 revisão indisponível: {type(exc).__name__}")


def _publish_regular_results(date, rows, worksheet, daily_index, cofre_get, cofre_cache, config, *, consolidated=False):
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
    # Federal 6120: substituir o conteúdo visual incorreto, sem reutilizar o upload antigo.
    federal_repair = date == "25/11/2026" and any(
        "federal" in str(d.get("loteria", "")).lower()
        and base.cal._contest_key(d.get("concurso")) == "6120" for d in results)
    prefix = ("PSS_RESULTADO_V42_" if federal_repair else "PSS_RESULTADO_V39_") + date.replace("/", "") + "_" + signature
    if consolidated:
        prefix = "PSS_RESULTADO_V44_CONSOLIDADO_" + date.replace("/", "") + "_" + signature
    package = None
    done = []
    need_short = not consolidated
    for account, token, privacy in _credentials(cofre_get, cofre_cache):
        try:
            normal = _find_call(token, prefix + "_NORMAL")
            short = _find_call(token, prefix + "_SHORT") if need_short else ""
            # Reutiliza URLs históricas somente se o vídeo pertence ao canal,
            # tem conteúdo de resultados na descrição e não é replay nem chamada.
            # Tags por concurso/formato sao a chave; nao reutilizar consolidado como individual.
            for mark in []:
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
                    if consolidated:
                        meta["title"] = f"Resultados de Todas as Loterias Caixa | {date}"
                    else:
                        lottery = q._display_lottery(results[0].get("loteria"))
                        contest = base.cal._contest_key(results[0].get("concurso"))
                        meta["title"] = f"Resultado {lottery} {contest} | {date}" + (" #Shorts" if kind == "SHORT" else "")
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
    if not consolidated:
        q._mark_rows(worksheet, [n for n, _ in rows], daily_index, mark)
    q._log(f"V44 {'CONSOLIDADO' if consolidated else 'INDIVIDUAL'} {date}: {base.build_watch_url(normal)}")
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
    return [found[(k, str(contest))] for k, _, contest in targets if (k, str(contest)) in found], missing



def _history_result(api_spreadsheet, history_values, key, display, contest, date):
    """V45: use the actual official JSON stored in history, never just the counter."""
    import json
    import re
    f = base.caixa_fallback
    slug = f._slug(key, display)
    if not slug:
        return None
    # A provisional source must not be treated as official.
    for line in history_values[1:]:
        record = dict(zip(history_values[0], line))
        if record.get("loteria") == slug and str(record.get("status", "")).upper().startswith("PROVIS") and str(record.get("ultimoImportado")) == str(contest):
            return None
    try:
        ws = api_spreadsheet.worksheet(f"API_HIST_{slug.upper()}_RESUMO")
        headers = ws.row_values(1)
        ci, ji, ui = (headers.index(name) for name in ("concurso", "json_extra", "url_fonte"))
        from gspread.utils import rowcol_to_a1
        # Exact contest lookup; only read a single matching row, no full JSON history.
        cell = ws.find(re.compile(r"^" + re.escape(str(contest)) + r"$"), in_column=ci + 1)
        if cell is None:
            return None
        line = ws.row_values(cell.row)
        if line[ui].strip() != f"{f.BASE_URL}/{slug}/{contest}":
            return None
        payload = json.loads(line[ji])
        if str(payload.get("numero")) != str(contest) or payload.get("dataApuracao") != date:
            return None
        counts = {"quina":5,"lotofacil":15,"diadesorte":7,"megasena":6,"timemania":7,"duplasena":6,"supersete":7,"lotomania":20,"maismilionaria":6}
        nums = payload.get("listaDezenas") or []
        if slug not in counts or len(nums) != counts[slug] or not all(re.fullmatch(r"\d{1,2}", str(n)) for n in nums):
            return None
        if slug == "duplasena" and len(payload.get("listaDezenasSegundoSorteio") or []) != 6:
            return None
        if slug in ("diadesorte", "timemania") and not str(payload.get("nomeTimeCoracaoMesSorte") or "").strip("\\x00 "):
            return None
        if slug == "maismilionaria" and len(payload.get("trevosSorteados") or payload.get("listaTrevos") or []) != 2:
            return None
        numbers = f._extract_numbers(payload, slug)
        if numbers:
            base.queue._log(f"V45 HISTORICO_CAIXA confirmado: {display} {contest} {date}")
            return {"loteria":display,"concurso":str(contest),"data":date,"numeros":numbers,"fonte":line[ui]}
    except Exception as exc:
        base.queue._log(f"V45 histórico indisponível {display} {contest}: {type(exc).__name__}")
    return None


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

    headers = list(values[0])
    daily_column = os.getenv("PUBLICADO_YT_DIARIO_COL", base.queue.DAILY_COLUMN_DEFAULT)
    daily_index = base.queue._ensure_column(worksheet, headers, daily_column)
    rows, missing_rows = _all_result_rows(values, headers, date, targets)
    official_cache = {}
    f = base.caixa_fallback
    existing = {(base.queue._lottery_key(d.get("loteria")), base.cal._contest_key(d.get("concurso"))): n for n,d in rows}
    for key, display, contest in targets:
        pair = (key, str(contest))
        if config.dry_run:
            continue
        official = _history_result(api_spreadsheet, history_values, key, display, str(contest), date)
        if official is None:
            try:
                official = f.fetch_official_result(key, display, contest)
            except Exception as exc:
                base.queue._log(f"V45 aguardando fonte oficial {display} {contest}: {type(exc).__name__}")
        if not official or official.get("data") != date or not official.get("numeros"):
            continue
        official_cache[pair] = official
        if pair not in existing:
            # Preserve existing source rows and avoid inserting duplicate contest keys.
            indices = [f._header_index(headers, *aliases) for aliases in (
                ("Produto","Loteria"), ("Concurso",), ("Data","Data Sorteio"), ("Numeros","Descricao","Resultado"))]
            if None in indices:
                raise RuntimeError("V45: colunas mínimas ausentes")
            il, ic, idate, inu = indices
            if any(base.queue._lottery_key(line[il] if il < len(line) else "") == key and base.cal._contest_key(line[ic] if ic < len(line) else "") == str(contest) for line in values[1:]):
                base.queue._log(f"V45 linha existente incompleta: {display} {contest}; sem duplicar")
                continue
            new_row = [""] * len(headers)
            new_row[il], new_row[ic], new_row[idate], new_row[inu] = display, str(contest), date, official["numeros"]
            worksheet.append_row(new_row, value_input_option="RAW")
    if not config.dry_run:
        values = worksheet.get_all_values()
        headers = list(values[0])
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

    # V41: a chamada ao vivo não depende da apuração.
    if not config.dry_run and (not is_today or base.queue._now_in_timezone(config.timezone).hour >= _scheduled_hour()):
        try:
            _transmit_narrated_call(date, targets, prize_highlight, cofre_get, cofre_cache)
        except Exception as exc:
            base.queue._log(f"V41 transmissão pendente {date}: {type(exc).__name__}")
    if not rows:
        if not config.dry_run:
            base._upsert_alert_status(api_spreadsheet, date, "", "PENDENTE_RESULTADOS_V45", config.timezone)
        base.queue._log(f"{date}: aguardando resultados: " + ", ".join(missing_rows))
        return 0

    verified = []
    for row in rows:
        data = row[1]
        key = base.queue._lottery_key(data.get("loteria"))
        contest = base.cal._contest_key(data.get("concurso"))
        display = next((d for k, d, c in targets if k == key and str(c) == contest), str(data.get("loteria")))
        if config.dry_run:
            verified.append(row)
            continue
        official = official_cache.get((key, contest))
        if official:
            # Render from the verified numbers, not a stale Blogger description.
            data = dict(data)
            data["numeros"] = official["numeros"]
            verified.append((row[0], data))
    if not verified:
        if not config.dry_run:
            base._upsert_alert_status(api_spreadsheet, date, "", "PENDENTE_RESULTADOS_V45", config.timezone)
        return 0
    complete = len(verified) == len(targets) and not missing_rows
    # V44: cada concurso recebe normal + Short, independentemente dos demais.
    result = 0
    for row in verified:
        result += _publish_regular_results(date, [row], worksheet, daily_index, cofre_get, cofre_cache, config)
    # Consolidado possui identificador próprio e nunca sobrescreve os individuais.
    # Com um único concurso, o vídeo individual já representa o dia inteiro.
    if complete:
        if len(verified) > 1:
            summary = _publish_regular_results(date, verified, worksheet, daily_index, cofre_get, cofre_cache, config, consolidated=True)
            if summary and result == len(verified):
                base._mark_alert_final(api_spreadsheet, date, config.timezone)
            result += summary
        elif result:
            base._mark_alert_final(api_spreadsheet, date, config.timezone)
    if not config.dry_run and (not complete or result < len(verified) + (1 if len(verified) > 1 else 0)):
        base._upsert_alert_status(api_spreadsheet, date, "", "PENDENTE_PUBLICACAO_V45", config.timezone)
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
