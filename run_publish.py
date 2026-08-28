# -*- coding: utf-8 -*-
"""
Orquestrador das publicações.

O X usa x_multi_account.py para publicar cada evento nas contas configuradas,
com texto, composição visual e controle de duplicidade próprios por conta.
As demais redes continuam usando as funções estáveis de bot.py.

Rev. 2026-08-28 — proteção persistente contra duplicidade no Telegram.
A deduplicação não depende mais apenas da coluna de status da aba de origem:
é mantido um ledger próprio (Telegram_Publicacoes) por loteria + concurso + URL.
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import List

import bot
from x_multi_account import publicar_x_automatico


TG_LEDGER_TAB = (os.getenv("TG_LEDGER_TAB", "Telegram_Publicacoes") or "Telegram_Publicacoes").strip()
TG_LEDGER_HEADERS = [
    "CHAVE",
    "LOTERIA",
    "CONCURSO",
    "URL",
    "STATUS",
    "ATUALIZADO_EM",
    "LINHA_ORIGEM",
]


def _target_networks() -> List[str]:
    raw = (os.getenv("TARGET_NETWORKS", "") or "").strip()
    if not raw:
        return bot._target_networks()
    values = []
    for part in raw.replace(";", ",").split(","):
        network = part.strip().upper()
        if network and network not in values:
            values.append(network)
    return values


def _apply_x_env_overrides() -> None:
    """Faz a variável do GitHub prevalecer sem alterar o Cofre existente."""
    raw = (os.getenv("POST_X_WITH_IMAGE", "") or "").strip().lower()
    if not raw:
        return
    enabled = raw in {"1", "true", "sim", "yes", "on"}
    bot._x_post_with_image = lambda: enabled


def _tg_ledger_ws(source_ws):
    """Obtém/cria o ledger persistente do Telegram na mesma planilha."""
    sh = source_ws.spreadsheet
    try:
        ledger = sh.worksheet(TG_LEDGER_TAB)
    except Exception:
        ledger = sh.add_worksheet(title=TG_LEDGER_TAB, rows=1000, cols=len(TG_LEDGER_HEADERS))
        ledger.append_row(TG_LEDGER_HEADERS, value_input_option="RAW")
        bot._log(f"[TELEGRAM][DEDUP] Criada aba {TG_LEDGER_TAB}.")
        return ledger

    header = ledger.row_values(1)
    if header != TG_LEDGER_HEADERS:
        ledger.update("A1:G1", [TG_LEDGER_HEADERS], value_input_option="RAW")
    return ledger


def _tg_key(row) -> str:
    loteria = bot._strip_invisible(row[bot.COL_LOTERIA - 1]) if bot._safe_len(row, bot.COL_LOTERIA) else ""
    concurso = bot._strip_invisible(row[bot.COL_CONCURSO - 1]) if bot._safe_len(row, bot.COL_CONCURSO) else ""
    url = bot._strip_invisible(row[bot.COL_URL - 1]) if bot._safe_len(row, bot.COL_URL) else ""
    raw = f"{loteria.lower()}|{concurso.lower()}|{url.lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _tg_fields(row):
    loteria = bot._strip_invisible(row[bot.COL_LOTERIA - 1]) if bot._safe_len(row, bot.COL_LOTERIA) else ""
    concurso = bot._strip_invisible(row[bot.COL_CONCURSO - 1]) if bot._safe_len(row, bot.COL_CONCURSO) else ""
    url = bot._strip_invisible(row[bot.COL_URL - 1]) if bot._safe_len(row, bot.COL_URL) else ""
    return loteria, concurso, url


def _tg_existing_keys(ledger):
    values = ledger.get_all_values()
    keys = set()
    for r in values[1:]:
        if not r:
            continue
        key = bot._strip_invisible(r[0] if len(r) > 0 else "")
        status = bot._strip_invisible(r[4] if len(r) > 4 else "").upper()
        if key and status in {"EM_PUBLICACAO", "PUBLICADO", "DUPLICADO"}:
            keys.add(key)
    return keys


def _tg_mark_source_duplicate(source_ws, rownum):
    """Evita que a mesma linha seja reavaliada em toda execução."""
    try:
        col = bot.COL_STATUS_REDES.get("TELEGRAM")
        if col:
            current = source_ws.cell(rownum, col).value or ""
            if bot._is_empty_status(current):
                source_ws.update_cell(
                    rownum,
                    col,
                    f"Ignorado Telegram: duplicado confirmado em {bot._ts_br()}",
                )
    except Exception as exc:
        bot._log(f"[TELEGRAM][DEDUP] Não foi possível marcar linha {rownum}: {exc}")


def _publicar_telegram_com_ledger(source_ws, candidates):
    """
    Publica Telegram um item por vez, com claim persistente antes do envio.

    Motivo do claim prévio: se a execução cair depois do sendPhoto/sendMessage e
    antes da atualização da coluna de origem, a próxima execução ainda verá a
    chave no ledger e NÃO reenviará o mesmo conteúdo.
    """
    ledger = _tg_ledger_ws(source_ws)
    existing = _tg_existing_keys(ledger)
    publicados = 0
    limite = min(bot.MAX_PUBLICACOES_RODADA, len(candidates))

    for rownum, row in candidates[:limite]:
        key = _tg_key(row)
        loteria, concurso, url = _tg_fields(row)

        if key in existing:
            bot._log(
                f"[TELEGRAM][DEDUP] SKIP já registrado: {loteria} concurso {concurso} | {url}"
            )
            _tg_mark_source_duplicate(source_ws, rownum)
            continue

        # Claim persistente ANTES do envio.
        # O workflow auto_publish.yml já usa concurrency/cancel-in-progress=false,
        # portanto não há duas execuções deste publicador processando o ledger em paralelo.
        row_ledger = len(ledger.get_all_values()) + 1
        ledger.append_row(
            [key, loteria, concurso, url, "EM_PUBLICACAO", bot._ts_br(), str(rownum)],
            value_input_option="RAW",
        )
        existing.add(key)

        try:
            qtd = bot.publicar_em_telegram(source_ws, [(rownum, row)])
            if qtd > 0:
                ledger.update_cell(row_ledger, 5, "PUBLICADO")
                ledger.update_cell(row_ledger, 6, bot._ts_br())
                publicados += qtd
                bot._log(
                    f"[TELEGRAM][DEDUP] PUBLICADO e gravado: {loteria} concurso {concurso}"
                )
            else:
                # Não houve publicação: remove o claim para permitir tentativa futura.
                ledger.delete_rows(row_ledger)
                existing.discard(key)
                bot._log(
                    f"[TELEGRAM][DEDUP] Sem envio; claim removido: {loteria} concurso {concurso}"
                )
        except Exception:
            # Falha antes/depois do envio é o caso perigoso. Mantemos o claim para
            # privilegiar não duplicar. A linha pode ser auditada manualmente no ledger.
            bot._log(
                f"[TELEGRAM][DEDUP] Erro após claim; chave mantida para bloquear duplicação: {key}"
            )
            raise

    bot._log(f"[TELEGRAM][DEDUP] Publicados nesta execução: {publicados}")
    return publicados


def main() -> None:
    bot._log("Start seguro", f"Origem={bot.BOT_ORIGEM} | DRY_RUN={bot.DRY_RUN}")
    keepalive_thread = bot.iniciar_keepalive() if bot.ENABLE_KEEPALIVE else None
    x_warning = ""

    try:
        bot._cofre_load()
        _apply_x_env_overrides()
        networks = _target_networks()
        bot._print_config_summary(networks)
        ws = bot._open_ws_principal()

        if "X" in networks:
            try:
                x_result = publicar_x_automatico(ws)
                if x_result.circuit_opened and (
                    "401" in x_result.circuit_reason or "403" in x_result.circuit_reason
                ):
                    x_warning = x_result.circuit_reason or "X bloqueado por 401/403"
                    bot._log(f"[X-SEGURO][AVISO] {x_warning}")
                    print(f"::warning title=X temporariamente isolado::{x_warning}", flush=True)
            except Exception as exc:
                # O X é uma rede independente. Falha nele não pode impedir Telegram,
                # Facebook, Discord e Pinterest de serem processados nem deixar a
                # automação inteira vermelha a cada 10 minutos.
                x_warning = str(exc)
                bot._log(f"[X-SEGURO][AVISO] {exc}")
                print(f"::warning title=Falha isolada no publicador do X::{exc}", flush=True)

        dispatch = {
            "FACEBOOK": bot.publicar_em_facebook,
            "TELEGRAM": _publicar_telegram_com_ledger,
            "DISCORD": bot.publicar_em_discord,
            "PINTEREST": bot.publicar_em_pinterest,
        }

        for network in networks:
            network = network.upper()
            if network == "X":
                continue
            publisher = dispatch.get(network)
            if not publisher:
                bot._log(f"[{network}] não suportada.")
                continue

            candidates = bot.coleta_candidatos_para(ws, network)
            if not candidates:
                bot._log(f"[{network}] Nenhuma candidata.")
                continue
            if not bot._has_creds_for(network):
                bot._log(f"[{network}] Sem credenciais no Cofre. Pulando.")
                continue
            publisher(ws, candidates)

        if x_warning:
            bot._log("Concluído com aviso isolado do X; demais redes preservadas.")
        else:
            bot._log("Concluído.")

    finally:
        if bot.ENABLE_KEEPALIVE and keepalive_thread:
            time.sleep(1)


if __name__ == "__main__":
    main()
