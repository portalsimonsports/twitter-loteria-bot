# -*- coding: utf-8 -*-
"""
Orquestrador das publicações.

O X usa x_multi_account.py para publicar cada evento nas contas configuradas,
com texto, composição visual e controle de duplicidade próprios por conta.
As demais redes continuam usando as funções estáveis de bot.py.
"""

from __future__ import annotations

import os
import time
from typing import List

import bot
from x_multi_account import publicar_x_automatico


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
            "TELEGRAM": bot.publicar_em_telegram,
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
