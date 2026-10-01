from __future__ import annotations

from datetime import timedelta

import pending_alert_fix_v27 as base

_original_pending_dates = base._pending_dates


def _pending_dates_recent_only(api_spreadsheet, today: str):
    """Considera bloqueantes apenas hoje e ontem.

    Pendências mais antigas continuam registradas para auditoria, mas não podem impedir
    indefinidamente a atualização da Live de ontem nem o fluxo do dia atual.
    """
    dates = _original_pending_dates(api_spreadsheet, today)
    today_dt = base._date_obj(today)
    if not today_dt:
        return dates
    cutoff = today_dt - timedelta(days=1)
    filtered = []
    for date in dates:
        dt = base._date_obj(date)
        if dt and dt >= cutoff:
            filtered.append(date)
        else:
            base.queue._log(f"{date}: pendência histórica não bloqueante ignorada pelo V28.")
    return filtered


def processar_resumo_por_calendario_api_v28() -> int:
    base._pending_dates = _pending_dates_recent_only
    return base.processar_resumo_por_calendario_api_v27()
