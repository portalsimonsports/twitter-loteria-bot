# post_video.py — Portal SimonSports — YouTube Multi-Canal (Cofre Only)
# Rev: 2026-07-30 — V17 final: diálogo, engajamento e metadados otimizados

import datetime as dt
import re
import time
import unicodedata
from typing import Any, Dict, List, Optional

from gerador_pacote_v10 import gerar_pacote
from youtube_auth import get_access_token
from youtube_upload import build_watch_url, upload_video


BRAND_LINE = "SimonSports — Simplesmente o Melhor"
PORTAL_DESCRIPTION = (
    "Portal com resultados atualizados das Loterias da Caixa, esportes nacionais e internacionais, "
    "e notícias relevantes do Brasil e do mundo."
)
RESULTS_INDEX_URL = "https://www.portalsimonsports.com/search/label/Loterias%20Caixa?m=1"


def _now_br(tz_name: str = "America/Sao_Paulo") -> dt.datetime:
    try:
        import pytz
        return dt.datetime.now(pytz.timezone(tz_name))
    except Exception:
        return dt.datetime.now()


def _ts_br(tz_name: str = "America/Sao_Paulo") -> str:
    return _now_br(tz_name).strftime("%d/%m/%Y %H:%M")


def _log(*args: Any) -> None:
    print("[YOUTUBE]", *args, flush=True)


def _parse_tags(value: str) -> List[str]:
    if not value:
        return []
    return [tag.strip() for tag in value.replace(";", ",").split(",") if tag.strip()]


def _unique_tags(*groups: List[str]) -> List[str]:
    output: List[str] = []
    seen = set()
    total_chars = 0
    for group in groups:
        for tag in group:
            clean = str(tag or "").strip()
            key = clean.casefold()
            if not clean or key in seen:
                continue
            projected = total_chars + len(clean) + (1 if output else 0)
            if len(output) >= 30 or projected > 480:
                continue
            seen.add(key)
            output.append(clean)
            total_chars = projected
    return output


def _text_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _hashtag(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    compact = re.sub(r"[^A-Za-z0-9]+", "", ascii_text)
    return f"#{compact}" if compact else "#Loterias"


def _cofre_get_safe(cofre_get_fn, rede: str, chave: str, conta: Optional[str] = None, default: str = "") -> str:
    value = (cofre_get_fn(rede, chave, conta=conta, default="") or "").strip()
    if value:
        return value
    return (cofre_get_fn(rede, chave, default=default) or "").strip()


def listar_contas_youtube(cofre_cache: Dict[str, Any]) -> List[str]:
    creds_rc = cofre_cache.get("creds_rc", {}) or {}
    accounts = set()
    for (network, account, key), value in creds_rc.items():
        if (network or "").strip().upper() == "YOUTUBE" and (key or "").strip().upper() == "REFRESH_TOKEN" and value:
            accounts.add((account or "").strip())
    return sorted(account for account in accounts if account)


def _metadata(dados_video: Dict[str, Any], tipo: str) -> Dict[str, Any]:
    lottery = str(dados_video.get("loteria") or "Loteria").strip()
    contest = str(dados_video.get("concurso") or "").strip()
    draw_date = str(dados_video.get("data") or "").strip()
    numbers = _text_value(dados_video.get("numeros") or dados_video.get("descricao") or "")
    numbers = re.sub(r"^n[uú]meros?\s*:\s*", "", numbers, flags=re.I).strip()
    prize = _text_value(dados_video.get("premio") or "")
    reference_url = str(dados_video.get("url") or "https://www.portalsimonsports.com/").strip()
    contest_part = f" {contest}" if contest else ""
    contest_phrase = f", concurso {contest}" if contest else ""
    lottery_hashtag = _hashtag(lottery)

    keyword_tags = [
        f"resultado {lottery}",
        f"{lottery} hoje",
        f"resultado {lottery} hoje",
        f"{lottery} concurso {contest}" if contest else f"concurso {lottery}",
        f"resultado {lottery} concurso {contest}" if contest else f"resultado oficial {lottery}",
        "resultado loteria hoje",
        "loterias Caixa hoje",
        "dezenas sorteadas",
        "resultado oficial Caixa",
        "conferir resultado loteria",
        "sorteio Caixa",
        "Loterias Caixa",
        "Portal SimonSports",
        "SimonSports",
    ]

    if tipo == "completo":
        title = str(
            dados_video.get("title_completo")
            or f"Resultado {lottery}{contest_part} — Dezenas Oficiais | SimonSports"
        )[:100]

        default_description = [
            f"Resultado oficial da {lottery}{contest_phrase}. Confira todas as dezenas sorteadas e faça a sua conferência.",
        ]
        if numbers:
            default_description.append(f"Dezenas sorteadas: {numbers}.")
        if draw_date:
            default_description.append(f"Data do sorteio: {draw_date}.")
        if prize:
            default_description.append(f"Prêmio ou estimativa: {prize}.")
        default_description.extend([
            "",
            "Comente quantas dezenas apareceram no seu jogo, deixe o like, compartilhe e inscreva-se no canal.",
            "",
            f"Resultado completo e informações desta edição: {reference_url}",
            f"Outros resultados da {lottery} e das Loterias Caixa: {RESULTS_INDEX_URL}",
            "",
            BRAND_LINE,
            PORTAL_DESCRIPTION,
            "Fonte: CAIXA Loterias. Conteúdo informativo.",
            "",
            f"{lottery_hashtag} #LoteriasCaixa #ResultadoOficial #PortalSimonSports #SimonSports",
        ])
        description = str(dados_video.get("description_completo") or "\n".join(default_description))[:4500]
        tags = keyword_tags + [
            "resultado completo",
            "resultados de loterias",
            "números sorteados",
            "Simplesmente o Melhor",
        ]
    else:
        title = str(
            dados_video.get("title_short")
            or f"Resultado {lottery}{contest_part} Hoje #Shorts"
        )[:100]

        default_description = [
            f"Resultado da {lottery}{contest_phrase}. Confira as dezenas sorteadas neste Short.",
            "O vídeo completo está disponível no canal SimonSports.",
            "Toque no vídeo relacionado exibido no player do Short.",
            "",
            f"Resultado e informações: {reference_url}",
            f"Outros resultados das Loterias Caixa: {RESULTS_INDEX_URL}",
            "",
            "Comente, curta, compartilhe e inscreva-se para acompanhar os próximos resultados.",
            "Fonte: CAIXA Loterias. Conteúdo informativo.",
            "",
            f"#Shorts {lottery_hashtag} #LoteriasCaixa #PortalSimonSports",
        ]
        description = str(dados_video.get("description_short") or "\n".join(default_description))[:4500]
        tags = keyword_tags + [
            "Shorts",
            "short de loteria",
            "resultado em 30 segundos",
            "resultado rápido",
        ]

    return {"title": title, "description": description, "tags": tags}


def publicar_video_em_multicanais(
    dados_video: Dict[str, Any],
    cofre_get_fn,
    cofre_cache: Dict[str, Any],
    *,
    dry_run: bool = False,
    sleep_between_channels: float = 1.0,
    tz_name: str = "America/Sao_Paulo",
) -> Dict[str, Any]:
    accounts = listar_contas_youtube(cofre_cache)
    if not accounts:
        message = "Nenhuma conta YOUTUBE com REFRESH_TOKEN no Cofre. Pulando."
        _log(message)
        return {
            "ok_any": False,
            "video_path": "",
            "video_paths": {},
            "results": [],
            "mark_value": f"Sem contas YOUTUBE no Cofre em {_ts_br(tz_name)}",
        }

    try:
        if dry_run:
            pacote = {
                "short": "DRYRUN_short_resultado_30s.mp4",
                "completo": "DRYRUN_video_completo_resultado.mp4",
                "base": "",
            }
            _log("DRY_RUN: pulando geração real do pacote V17.")
        else:
            pacote = gerar_pacote(dados_video)
    except Exception as error:
        _log("Erro ao gerar pacote de vídeos:", error)
        return {
            "ok_any": False,
            "video_path": "",
            "video_paths": {},
            "results": [],
            "mark_value": f"Erro ao gerar pacote de vídeos: {error}",
        }

    full_meta = _metadata(dados_video, "completo")
    short_meta = _metadata(dados_video, "short")
    results: List[Dict[str, Any]] = []
    ok_any = False

    for account in accounts:
        full_url = ""
        short_url = ""
        client_id = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "CLIENT_ID", conta=account)
        client_secret = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "CLIENT_SECRET", conta=account)
        refresh_token = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "REFRESH_TOKEN", conta=account)

        if not (client_id and client_secret and refresh_token):
            _log(f"[{account}] Credenciais incompletas (CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN).")
            results.append({
                "conta": account, "status": "ERRO", "full_url": "", "short_url": "",
                "error": "Credenciais incompletas",
            })
            continue

        privacy = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "PRIVACY_STATUS", conta=account, default="public") or "public"
        category_id = _cofre_get_safe(cofre_get_fn, "YOUTUBE", "CATEGORY_ID", conta=account, default="24") or "24"
        custom_tags = _parse_tags(_cofre_get_safe(cofre_get_fn, "YOUTUBE", "TAGS", conta=account, default=""))
        full_tags = _unique_tags(custom_tags, full_meta["tags"])
        short_tags = _unique_tags(custom_tags, short_meta["tags"])

        try:
            if dry_run:
                full_id = f"DRYRUN_FULL_{account.replace(' ', '_')}"
                short_id = f"DRYRUN_SHORT_{account.replace(' ', '_')}"
            else:
                access_token = get_access_token(client_id, client_secret, refresh_token)
                full_id = upload_video(
                    access_token=access_token,
                    video_path=pacote["completo"],
                    title=full_meta["title"],
                    description=full_meta["description"],
                    tags=full_tags,
                    category_id=category_id,
                    privacy_status=privacy,
                )
                full_url = build_watch_url(full_id)
                _log(f"[{account}] Vídeo completo publicado → {full_url}")

                short_id = upload_video(
                    access_token=access_token,
                    video_path=pacote["short"],
                    title=short_meta["title"],
                    description=short_meta["description"],
                    tags=short_tags,
                    category_id=category_id,
                    privacy_status=privacy,
                )

            full_url = full_url or build_watch_url(full_id)
            short_url = build_watch_url(short_id)
            _log(f"[{account}] Pacote V17 OK | completo={full_url} | Short={short_url}")
            ok_any = True
            results.append({
                "conta": account,
                "status": "OK",
                "full_id": full_id,
                "full_url": full_url,
                "short_id": short_id,
                "short_url": short_url,
                "error": "",
            })
        except Exception as error:
            _log(f"[{account}] ERRO no pacote:", error)
            results.append({
                "conta": account,
                "status": "ERRO",
                "full_url": full_url,
                "short_url": short_url,
                "error": str(error),
            })

        time.sleep(sleep_between_channels)

    published = [result for result in results if result.get("status") == "OK"]
    if published:
        first = published[0]
        mark_value = (
            f"Publicado YOUTUBE V17 em {_ts_br(tz_name)} | "
            f"Completo: {first.get('full_url', '')} | Short: {first.get('short_url', '')} | "
            "Pendente: selecionar o completo como vídeo relacionado no Short"
        )
    else:
        errors = [
            f"{result.get('conta', '')}: {result.get('error', '')}"
            for result in results if result.get("status") == "ERRO"
        ]
        mark_value = f"Falha YOUTUBE V17 em {_ts_br(tz_name)} | " + " | ".join(errors[:2])

    return {
        "ok_any": ok_any,
        "video_path": pacote.get("short", ""),
        "video_paths": pacote,
        "results": results,
        "mark_value": mark_value,
    }
