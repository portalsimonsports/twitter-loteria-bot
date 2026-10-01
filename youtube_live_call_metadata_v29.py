from __future__ import annotations

from typing import Sequence, Tuple

import youtube_daily_live_v22 as live


def _call_metadata(date: str, targets: Sequence[Tuple[str, str, str]]):
    names = []
    lines = []
    for _key, display, contest in targets:
        if display not in names:
            names.append(display)
        lines.append(f"• {display} — concurso {contest}")

    joined = ", ".join(names[:4]) + (" e mais" if len(names) > 4 else "")
    title = f"Hoje tem sorteio! {joined} | Acompanhe o Portal SimonSports | {date}"
    if len(title) > 95:
        title = f"Hoje tem sorteio! Acompanhe o Portal SimonSports | {date}"

    description = "\n".join([
        f"CHAMADA DO DIA — sorteios previstos para {date}:",
        "",
        *lines,
        "",
        "Inscreva-se no canal, ative as notificações e compartilhe o Portal SimonSports.",
        "Os resultados de cada concurso serão publicados separadamente assim que estiverem disponíveis.",
        "Esta live é somente uma chamada do dia e não será substituída pelo vídeo de resultados.",
        "",
        "Portal SimonSports — Loterias Caixa",
        "Fonte dos resultados: CAIXA Loterias. Conteúdo informativo.",
        "",
        live.LIVE_MARKER,
    ])
    return {"title": title[:95], "description": description[:4500]}


live._alert_metadata = _call_metadata
