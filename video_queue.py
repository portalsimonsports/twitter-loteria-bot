# video_queue.py — Portal SimonSports — Fila de Vídeos (YouTube) via Planilha + Cofre
# Rev: 2026-01-25b (ATUALIZADO)
# - Corrige batch_update (gspread Worksheet.batch_update) com fallback seguro
# - Garante colunas Enfileirado_Videos e Publicado_Youtube
# - Processa:
#     Enfileirado_Videos != vazio  E  Publicado_Youtube vazio
# - Monta dados_video a partir da MESMA BASE (Loteria/Concurso/Data/Números/URL)
# - Chama post_video.publicar_video_em_multicanais(...)
# - Marca:
#     Publicado_Youtube = mark_value retornado
#     Enfileirado_Videos = "OK dd/mm/aaaa hh:mm" ou "ERRO dd/mm/aaaa hh:mm" (mantém histórico)
#
# ENV necessários:
#   GOOGLE_SERVICE_JSON (Secret)
#   COFRE_SHEET_ID (Secret/Var)  -> Planilha Cofre Credenciais
#
# Opcional:
#   GOOGLE_SHEET_ID (default: 16NcdSwX6q_EQ2XjS1KNIBe6C3Piq-lCBgA38TMszXCI)
#   SHEET_TAB (default: ImportadosBlogger2)
#   COFRE_ABA_CRED (default: Credenciais_Rede)
#   ENFILEIRADO_VIDEOS_COL (default: Enfileirado_Videos)
#   PUBLICADO_YT_COL (default: Publicado_Youtube)
#   MAX_VIDEOS_RODADA (default: 10)
#   PAUSA_ENTRE_VIDEOS (default: 2.0)
#   DRY_RUN_VIDEOS ('true'/'false')

import os
import json
import time
import datetime as dt
from typing import Dict, Any, List, Tuple, Optional

import gspread
from google.oauth2.service_account import Credentials

from post_video import publicar_video_em_multicanais


TZ_NAME = "America/Sao_Paulo"


def _log(*a):
    print("[VIDEO_QUEUE]", *a, flush=True)


def _now_br() -> dt.datetime:
    try:
        import pytz
        tz = pytz.timezone(TZ_NAME)
        return dt.datetime.now(tz)
    except Exception:
        return dt.datetime.now()


def _ts_br() -> str:
    return _now_br().strftime("%d/%m/%Y %H:%M")


def _as_bool(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "sim", "yes", "y", "on")


def _load_service_account() -> Credentials:
    raw = os.getenv("GOOGLE_SERVICE_JSON", "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_JSON ausente.")
    info = json.loads(raw)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    return Credentials.from_service_account_info(info, scopes=scopes)


def _open_ws(sheet_id: str, tab_name: str):
    creds = _load_service_account()
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(sheet_id)
    return ss.worksheet(tab_name)


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _upper(s: Any) -> str:
    return _norm(s).upper()


def _ensure_col(headers: List[str], want: str) -> Tuple[List[str], int, bool]:
    """
    Garante que existe a coluna `want` nos headers.
    Retorna (headers, idx0, created)
    """
    want_n = want.strip()
    for i, h in enumerate(headers):
        if (h or "").strip() == want_n:
            return headers, i, False
    headers.append(want_n)
    return headers, len(headers) - 1, True


def _worksheet_set_headers(ws, headers: List[str]):
    ws.update("A1", [headers], value_input_option="RAW")


def _read_all(ws) -> Tuple[List[str], List[List[Any]]]:
    values = ws.get_all_values()
    if not values:
        return [], []
    headers = values[0]
    rows = values[1:]
    return headers, rows


def _cofre_load(creds_ws_id: str, aba_cred: str) -> Dict[str, Any]:
    """
    Lê aba do Cofre no formato:
    Rede | Conta | Chave | Valor
    """
    ws = _open_ws(creds_ws_id, aba_cred)
    vals = ws.get_all_values()
    if not vals or len(vals) < 2:
        return {"creds_rc": {}}

    headers = [c.strip() for c in vals[0]]

    def col(name: str) -> int:
        for i, h in enumerate(headers):
            if h.strip().lower() == name.lower():
                return i
        return -1

    i_rede = col("Rede")
    i_conta = col("Conta")
    i_chave = col("Chave")
    i_valor = col("Valor")

    if min(i_rede, i_conta, i_chave, i_valor) < 0:
        raise RuntimeError(f"Cofre aba '{aba_cred}' precisa ter cabeçalho: Rede, Conta, Chave, Valor")

    creds_rc = {}
    for r in vals[1:]:
        rede = _upper(r[i_rede] if i_rede < len(r) else "")
        conta = _norm(r[i_conta] if i_conta < len(r) else "")
        chave = _upper(r[i_chave] if i_chave < len(r) else "")
        valor = _norm(r[i_valor] if i_valor < len(r) else "")
        if rede and chave and valor:
            creds_rc[(rede, conta, chave)] = valor

    return {"creds_rc": creds_rc}


def _cofre_get(cofre_cache: Dict[str, Any], rede: str, chave: str, conta: Optional[str] = None, default: str = "") -> str:
    creds_rc = cofre_cache.get("creds_rc", {}) or {}
    r = _upper(rede)
    k = _upper(chave)
    c = _norm(conta or "")
    v = _norm(creds_rc.get((r, c, k), ""))
    if v:
        return v
    v2 = _norm(creds_rc.get((r, "", k), ""))
    if v2:
        return v2
    return default


def _is_pending(enf_val: str, pub_val: str) -> bool:
    """
    Pendência: enfileirado tem algo, publicado está vazio.
    E evita reprocessar se Enfileirado já marcado como OK/ERRO/FALHA.
    """
    enf = _norm(enf_val)
    pub = _norm(pub_val)
    if not enf or pub:
        return False
    low = enf.lower()
    if low.startswith("ok ") or low.startswith("erro ") or low.startswith("falha "):
        return False
    return True


def _batch_apply(ws, updates: List[Tuple[str, Any]]):
    """
    updates: [(A1, valor), ...]
    Usa Worksheet.batch_update (gspread) no formato correto.
    Fallback para ws.update se necessário.
    """
    if not updates:
        return

    data = [{"range": a1, "values": [[val]]} for (a1, val) in updates]
    try:
        # gspread Worksheet.batch_update(data, **kwargs)
        ws.batch_update(data, value_input_option="USER_ENTERED")
        return
    except Exception as e:
        _log("batch_update falhou, aplicando fallback update 1 a 1:", e)

    # fallback seguro (mais lento, mas garante)
    for a1, val in updates:
        try:
            ws.update(a1, [[val]], value_input_option="USER_ENTERED")
        except Exception as ee:
            _log("Falha no update fallback:", a1, "->", ee)


def main():
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip() or "16NcdSwX6q_EQ2XjS1KNIBe6C3Piq-lCBgA38TMszXCI"
    tab = os.getenv("SHEET_TAB", "").strip() or "ImportadosBlogger2"

    cofre_id = (os.getenv("COFRE_SHEET_ID", "") or "").strip()
    cofre_aba = (os.getenv("COFRE_ABA_CRED", "") or "").strip() or "Credenciais_Rede"
    if not cofre_id:
        raise RuntimeError("COFRE_SHEET_ID ausente (necessário para YOUTUBE Cofre Only).")

    enf_col_name = (os.getenv("ENFILEIRADO_VIDEOS_COL", "") or "").strip() or "Enfileirado_Videos"
    pub_col_name = (os.getenv("PUBLICADO_YT_COL", "") or "").strip() or "Publicado_Youtube"

    max_videos = int((os.getenv("MAX_VIDEOS_RODADA", "") or "10").strip())
    pausa = float((os.getenv("PAUSA_ENTRE_VIDEOS", "") or "2.0").strip())
    dry_run = _as_bool(os.getenv("DRY_RUN_VIDEOS", "") or "false")

    _log("Planilha:", sheet_id, "Aba:", tab)
    _log("Colunas:", enf_col_name, "/", pub_col_name, "MAX:", max_videos, "DRY_RUN:", dry_run)

    # Carrega Cofre
    cofre_cache = _cofre_load(cofre_id, cofre_aba)

    # Abre planilha principal
    ws = _open_ws(sheet_id, tab)
    headers, rows = _read_all(ws)
    if not headers:
        _log("Aba vazia. Nada a fazer.")
        return

    # Garante colunas necessárias
    headers2 = [h for h in headers]
    headers2, _, created_enf = _ensure_col(headers2, enf_col_name)
    headers2, _, created_pub = _ensure_col(headers2, pub_col_name)

    if created_enf or created_pub:
        _log("Criando colunas faltantes:", ("ENF" if created_enf else ""), ("PUB" if created_pub else ""))
        _worksheet_set_headers(ws, headers2)
        headers, rows = _read_all(ws)

    # Busca colunas base por nome (com fallback A-E)
    def find_col(possible: List[str], fallback_idx: int) -> int:
        lower = [(_norm(h).lower()) for h in headers]
        for name in possible:
            n = name.lower()
            if n in lower:
                return lower.index(n)
        return fallback_idx

    idx_loteria = find_col(["Loteria"], 0)
    idx_concurso = find_col(["Concurso"], 1)
    idx_data = find_col(["Data"], 2)
    idx_numeros = find_col(["Números", "Numeros"], 3)
    idx_url = find_col(["URL", "Url"], 4)

    # Índices exatos de ENF/PUB
    idx_enf = headers.index(enf_col_name)
    idx_pub = headers.index(pub_col_name)

    pendentes: List[Tuple[int, List[Any]]] = []
    for i, row in enumerate(rows, start=2):  # linha real na planilha (1 = header)
        enf = row[idx_enf] if idx_enf < len(row) else ""
        pub = row[idx_pub] if idx_pub < len(row) else ""
        if _is_pending(enf, pub):
            pendentes.append((i, row))

    if not pendentes:
        _log("Sem vídeos pendentes (Enfileirado preenchido e Publicado vazio).")
        return

    _log("Pendentes encontrados:", len(pendentes))
    pendentes = pendentes[:max_videos]

    updates: List[Tuple[str, Any]] = []
    ok_any_count = 0

    for (rownum, row) in pendentes:
        loteria = _norm(row[idx_loteria] if idx_loteria < len(row) else "")
        concurso = _norm(row[idx_concurso] if idx_concurso < len(row) else "")
        data_s = _norm(row[idx_data] if idx_data < len(row) else "")
        numeros = _norm(row[idx_numeros] if idx_numeros < len(row) else "")
        url = _norm(row[idx_url] if idx_url < len(row) else "")

        dados_video = {
            "loteria": loteria,
            "concurso": concurso,
            "data": data_s,
            "numeros": numeros,
            "url": url,
            "premio": "",  # não existe na base — mantém vazio
        }

        _log(f"Processando linha {rownum}: {loteria} {concurso} ({data_s})")

        pub_a1 = gspread.utils.rowcol_to_a1(rownum, idx_pub + 1)
        enf_a1 = gspread.utils.rowcol_to_a1(rownum, idx_enf + 1)

        try:
            res = publicar_video_em_multicanais(
                dados_video=dados_video,
                cofre_get_fn=lambda rede, chave, conta=None, default="": _cofre_get(cofre_cache, rede, chave, conta=conta, default=default),
                cofre_cache=cofre_cache,
                dry_run=dry_run,
                sleep_between_channels=1.0,
                tz_name=TZ_NAME,
            )

            mark_value = _norm(res.get("mark_value", "")) or f"Processado em {_ts_br()}"
            ok_any = bool(res.get("ok_any"))

            updates.append((pub_a1, mark_value))
            if ok_any:
                ok_any_count += 1
                updates.append((enf_a1, f"OK {_ts_br()}"))
            else:
                updates.append((enf_a1, f"ERRO {_ts_br()}"))

        except Exception as e:
            _log("ERRO na linha", rownum, "->", e)
            updates.append((pub_a1, f"Falha YOUTUBE em {_ts_br()} | {e}"))
            updates.append((enf_a1, f"ERRO {_ts_br()}"))

        time.sleep(pausa)

    _log("Aplicando updates na planilha:", len(updates))
    _batch_apply(ws, updates)

    _log(f"Concluído. Linhas com OK em pelo menos 1 canal: {ok_any_count}/{len(pendentes)}")


if __name__ == "__main__":
    main()