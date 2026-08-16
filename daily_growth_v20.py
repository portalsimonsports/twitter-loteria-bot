from __future__ import annotations

"""
Portal SimonSports — crescimento orgânico do resumo diário do YouTube.

Patch isolado sobre V19 para melhorar:
- intenção de busca no título e nas primeiras linhas da descrição;
- tags por modalidade/concurso;
- thumbnail/capa legível no celular, com a principal loteria em destaque;
- CTA de inscrição sem aumentar a duração do vídeo.

Não altera filas, calendário, política da Loteca ou outras publicações.
"""

from datetime import datetime
from typing import Any, Dict, List, Sequence, Tuple
from zoneinfo import ZoneInfo

import daily_queue_v19 as dq
import daily_video_v19 as dv


PRIORIDADE = {
    "loteca": 0,
    "mega sena": 1,
    "lotofacil": 2,
    "quina": 3,
    "mais milionaria": 4,
    "lotomania": 5,
    "dupla sena": 6,
    "timemania": 7,
    "dia de sorte": 8,
    "super sete": 9,
    "loteria federal": 10,
}


def _primary(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {}
    return min(
        (dict(item) for item in results),
        key=lambda item: (
            PRIORIDADE.get(dq._lottery_key(item.get("loteria")), 99),
            dq._display_lottery(item.get("loteria")),
        ),
    )


def _is_today_br(date_text: str) -> bool:
    parsed = dq._parse_date(date_text)
    if parsed is None:
        return False
    try:
        today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    except Exception:
        today = datetime.now().date()
    return parsed.date() == today


def _contest(data: Dict[str, Any]) -> str:
    return str(data.get("concurso") or "").strip()


def _search_lead(data: Dict[str, Any], date_text: str) -> str:
    lottery = dq._display_lottery(data.get("loteria"))
    contest = _contest(data)
    contest_text = f" concurso {contest}" if contest else ""
    today_text = " hoje" if _is_today_br(date_text) else ""
    return f"Resultado da {lottery}{contest_text}{today_text} ({date_text})."


def _title_full(results: Sequence[Dict[str, Any]], date_text: str) -> str:
    primary = _primary(results)
    lottery = dq._display_lottery(primary.get("loteria"))
    contest = _contest(primary)
    contest_text = f" {contest}" if contest else ""
    today_text = " Hoje" if _is_today_br(date_text) else ""
    title = f"Resultado {lottery}{contest_text}{today_text} + Loterias | {date_text}"
    return title[:95]


def _title_short(results: Sequence[Dict[str, Any]], date_text: str) -> str:
    primary = _primary(results)
    lottery = dq._display_lottery(primary.get("loteria"))
    contest = _contest(primary)
    contest_text = f" {contest}" if contest else ""
    today_text = " Hoje" if _is_today_br(date_text) else ""
    return f"Resultado {lottery}{contest_text}{today_text} em 1 Minuto #Shorts"[:95]


def _growth_metadata(results: Sequence[Dict[str, Any]], tipo: str) -> Dict[str, Any]:
    if not results:
        return {"title": "Resultados das Loterias | SimonSports", "description": "", "tags": []}

    date_text = str(results[0].get("data") or "").strip()
    primary = _primary(results)
    names = [dq._display_lottery(item.get("loteria")) for item in results]
    unique_names: List[str] = []
    for name in names:
        if name and name not in unique_names:
            unique_names.append(name)

    if tipo == "completo":
        title = _title_full(results, date_text)
        description_lines = [
            _search_lead(primary, date_text),
            "Resultados oficiais das Loterias Caixa reunidos em um único vídeo no SimonSports.",
            "",
            "RESULTADOS DESTA EDIÇÃO:",
        ]
        for data in results:
            description_lines.append("• " + dq._compact_result(data))
            url = str(data.get("url") or "").strip()
            if url:
                description_lines.append(f"  Detalhes: {url}")
        description_lines.extend([
            "",
            "Acompanhe os próximos resultados no SimonSports: inscreva-se no canal e ative as notificações.",
            "Curta e comente qual concurso você acompanha.",
            f"Outros resultados das Loterias Caixa: {dq.RESULTS_INDEX_URL}",
            "",
            dq.BRAND_LINE,
            dq.PORTAL_DESCRIPTION,
            "Fonte: CAIXA Loterias. Conteúdo informativo.",
            "",
            "#LoteriasCaixa #ResultadosDeHoje #ResultadoOficial #SimonSports",
        ])
        tags: List[str] = [
            "resultados das loterias de hoje",
            "resultado loterias hoje",
            "loterias caixa hoje",
            f"resultados loterias {date_text}",
            "resultado oficial caixa",
            "dezenas sorteadas hoje",
            "Portal SimonSports",
            "SimonSports",
        ]
    else:
        title = _title_short(results, date_text)
        description_lines = [
            _search_lead(primary, date_text),
            "Resumo rápido dos resultados das Loterias Caixa.",
            "",
        ]
        description_lines.extend("• " + dq._compact_result(data) for data in results)
        description_lines.extend([
            "",
            "Veja o vídeo completo no canal SimonSports.",
            "Inscreva-se e ative as notificações para acompanhar os próximos concursos.",
            f"Outros resultados: {dq.RESULTS_INDEX_URL}",
            "Fonte: CAIXA Loterias. Conteúdo informativo.",
            "",
            "#Shorts #LoteriasCaixa #ResultadosDeHoje #SimonSports",
        ])
        tags = [
            "resultados loterias hoje em 1 minuto",
            "resultado loterias hoje",
            "loterias caixa hoje",
            "short loterias",
            "resultado rápido loterias",
            "Portal SimonSports",
            "SimonSports",
            "Shorts",
        ]

    for data in results:
        lottery = dq._display_lottery(data.get("loteria"))
        contest = _contest(data)
        tags.extend([
            lottery,
            f"resultado {lottery}",
            f"resultado {lottery} hoje",
            f"{lottery} hoje",
        ])
        if contest:
            tags.extend([
                f"{lottery} {contest}",
                f"{lottery} concurso {contest}",
                f"resultado {lottery} {contest}",
                f"resultado {lottery} concurso {contest}",
            ])

    # A rotina de upload ainda aplica o sanitizador final; aqui removemos duplicidades
    # mantendo a ordem para privilegiar as consultas mais importantes.
    clean_tags: List[str] = []
    seen = set()
    for tag in tags:
        text = " ".join(str(tag or "").split()).strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        clean_tags.append(text)

    return {
        "title": title,
        "description": "\n".join(description_lines)[:4500],
        "tags": clean_tags[:30],
    }


def _growth_intro_image(results: Sequence[Dict[str, Any]], size: Tuple[int, int]):
    image = dv._gradient(size, top=(8, 119, 190), bottom=(0, 18, 44))
    draw = dv.ImageDraw.Draw(image, "RGBA")
    dv._brand(draw, size)
    width, height = size
    horizontal = width > height
    primary = _primary(results)
    lottery = dq._display_lottery(primary.get("loteria")).upper()
    contest = _contest(primary)
    date_text = str(primary.get("data") or "").strip()

    y = 285 if horizontal else 450
    main = f"{lottery} {contest}".strip()
    draw.text(
        (width / 2, y),
        main,
        font=dv._fit_font(draw, main, width - 150, 92 if horizontal else 70, 34),
        fill="white",
        anchor="mm",
    )
    subtitle = "RESULTADO DE HOJE" if _is_today_br(date_text) else "RESULTADO DO CONCURSO"
    draw.text(
        (width / 2, y + (105 if horizontal else 100)),
        subtitle,
        font=dv._fit_font(draw, subtitle, width - 180, 50 if horizontal else 42, 26),
        fill=(255, 224, 105),
        anchor="mm",
    )
    if date_text:
        draw.text(
            (width / 2, y + (175 if horizontal else 168)),
            date_text,
            font=dv._font(30 if horizontal else 28, True),
            fill=(180, 238, 255),
            anchor="mm",
        )

    other_names: List[str] = []
    primary_key = dq._lottery_key(primary.get("loteria"))
    for item in results:
        if dq._lottery_key(item.get("loteria")) == primary_key:
            continue
        name = dq._display_lottery(item.get("loteria"))
        if name not in other_names:
            other_names.append(name)
    extra = " + ".join(other_names[:4])
    if len(other_names) > 4:
        extra += " + mais"
    extra_text = f"TAMBÉM: {extra}" if extra else "RESULTADO OFICIAL"

    box_top = y + (235 if horizontal else 245)
    box_bottom = box_top + (120 if horizontal else 150)
    draw.rounded_rectangle(
        (100, box_top, width - 100, box_bottom),
        radius=36,
        fill=(0, 18, 42, 230),
        outline=(130, 217, 255),
        width=3,
    )
    draw.text(
        (width / 2, (box_top + box_bottom) / 2),
        extra_text,
        font=dv._fit_font(draw, extra_text, width - 260, 32 if horizontal else 27, 18),
        fill=(180, 238, 255),
        anchor="mm",
    )
    dv._footer(draw, size)
    return image


def _growth_closing_image(results: Sequence[Dict[str, Any]], size: Tuple[int, int]):
    image = dv._gradient(size, top=(8, 95, 165), bottom=(0, 16, 38))
    draw = dv.ImageDraw.Draw(image, "RGBA")
    dv._brand(draw, size)
    width, height = size
    horizontal = width > height
    y = height / 2 - 150
    draw.text(
        (width / 2, y),
        "ACOMPANHE OS PRÓXIMOS RESULTADOS",
        font=dv._fit_font(draw, "ACOMPANHE OS PRÓXIMOS RESULTADOS", width - 150, 58 if horizontal else 47, 25),
        fill="white",
        anchor="mm",
    )
    draw.text(
        (width / 2, y + 105),
        "INSCREVA-SE NO SIMONSPORTS",
        font=dv._fit_font(draw, "INSCREVA-SE NO SIMONSPORTS", width - 180, 48 if horizontal else 39, 23),
        fill=(255, 224, 105),
        anchor="mm",
    )
    draw.rounded_rectangle(
        (150, y + 185, width - 150, y + 305),
        radius=36,
        fill=(0, 119, 193),
        outline=(180, 238, 255),
        width=3,
    )
    draw.text(
        (width / 2, y + 245),
        "ATIVE AS NOTIFICAÇÕES • CURTA • COMENTE",
        font=dv._fit_font(draw, "ATIVE AS NOTIFICAÇÕES • CURTA • COMENTE", width - 360, 32 if horizontal else 27, 18),
        fill="white",
        anchor="mm",
    )
    draw.text(
        (width / 2, y + 390),
        "portalsimonsports.com",
        font=dv._font(30 if horizontal else 27, True),
        fill=(180, 238, 255),
        anchor="mm",
    )
    dv._footer(draw, size)
    return image


# Monkeypatch deliberadamente isolado para permitir rollback simples.
dq._metadata = _growth_metadata
dv._intro_image = _growth_intro_image
dv._closing_image = _growth_closing_image


__all__ = ["_growth_metadata", "_growth_intro_image", "_growth_closing_image"]
