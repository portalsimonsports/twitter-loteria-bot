# post_video.py — Portal SimonSports — YouTube Multi-Canal (Cofre Only)
# Rev: 2026-07-29 — V10: Short de 30s + vídeo completo horizontal

import datetime as dt
import time
from typing import Any, Dict, List, Optional

from gerador_pacote_v10 import gerar_pacote
from youtube_auth import get_access_token
from youtube_upload import build_watch_url, upload_video


BRAND_LINE = "SimonSports — Simplesmente o Melhor"
PORTAL_DESCRIPTION = (
    "Portal com resultados atualizados das Loterias da Caixa, esportes nacionais e internacionais, "
    "e notícias relevantes do Brasil e do mundo."
)


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
    for group in groups:
        for tag in group:
            key = tag.casefold().strip()
            if key and key not in seen:
                seen.add(key)
                output.append(tag.strip())
    return output[:30]


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
    numbers = str(dados_video.get("numeros") or dados_video.get("descricao") or "").strip()
    prize = str(dados_video.get("premio") or "").strip()
    reference_url = str(dados_video.get("url") or "https://www.portalsimonsports.com/").strip()
    contest_part = f" {contest}" if contest else ""

    common_lines = [
        BRAND_LINE,
        PORTAL_DESCRIPTION,
        "",
        f"Resultado oficial da {lottery}" + (f" — Concurso {contest}." if contest else "."),
    ]
    if draw_date:
        common_lines.append(f"Data do sorteio: {draw_date}.")
    if numbers:
        common_lines.append(f"Números sorteados: {numbers}.")
    if prize:
        common_lines.append(f"Prêmio ou estimativa: {prize}.")
    common_lines.extend([
        "Fonte: CAIXA Loterias.",
        "Conteúdo informativo.",
    ])

    if tipo == "completo":
        title = str(
            dados_video.get("title_completo")
            or dados_video.get("title")
            or f"Resultado completo {lottery}{contest_part} | SimonSports"
        )[:100]
        description = str(dados_video.get("description_completo") or "\n".join(common_lines + ["", f"Mais informações: {reference_url}"]))[:4500]
        tags = [
            "loterias", "resultado oficial", "resultado completo", "resultados de loterias",
            "Caixa Loterias", lottery, f"concurso {contest}" if contest else "concursos",
            "Portal SimonSports", "SimonSports", "Simplesmente o Melhor",
        ]
    else:
        title = str(
            dados_video.get("title_short")
            or f"Resultado {lottery}{contest_part} em 30 segundos #Shorts"
        )[:100]
        description = str(
            dados_video.get("description_short")
            or "\n".join([
                BRAND_LINE,
                f"Confira uma prévia do resultado da {lottery}" + (f", concurso {contest}." if contest else "."),
                "O resultado completo está disponível no canal SimonSports.",
                "Toque no vídeo relacionado exibido no player do Short.",
                "",
                "Fonte: CAIXA Loterias. Conteúdo informativo.",
                "#Shorts #Loterias #Resultados #CaixaLoterias #PortalSimonSports",
            ])
        )[:4500]
        tags = [
            "Shorts", "loterias", "resultado oficial", "resultados de loterias",
            "Caixa Loterias", lottery, f"concurso {contest}" if contest else "concursos",
            "Portal SimonSports", "SimonSports",
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
            _log("DRY_RUN: pulando geração real do pacote V10.")
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
                _log(f"[{account}] Vídeo completo publicado → {build_watch_url(full_id)}")

                short_id = upload_video(
                    access_token=access_token,
                    video_path=pacote["short"],
                    title=short_meta["title"],
                    description=short_meta["description"],
                    tags=short_tags,
                    category_id=category_id,
                    privacy_status=privacy,
                )

            full_url = build_watch_url(full_id)
            short_url = build_watch_url(short_id)
            _log(f"[{account}] Pacote V10 OK | completo={full_url} | Short={short_url}")
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
                "full_url": locals().get("full_url", ""),
                "short_url": "",
                "error": str(error),
            })

        time.sleep(sleep_between_channels)

    published = [result for result in results if result.get("status") == "OK"]
    if published:
        first = published[0]
        mark_value = (
            f"Publicado YOUTUBE V10 em {_ts_br(tz_name)} | "
            f"Completo: {first.get('full_url', '')} | Short: {first.get('short_url', '')} | "
            "Pendente: selecionar o completo como vídeo relacionado no Short"
        )
    else:
        errors = [
            f"{result.get('conta', '')}: {result.get('error', '')}"
            for result in results if result.get("status") == "ERRO"
        ]
        mark_value = f"Falha YOUTUBE V10 em {_ts_br(tz_name)} | " + " | ".join(errors[:2])

    return {
        "ok_any": ok_any,
        "video_path": pacote.get("short", ""),
        "video_paths": pacote,
        "results": results,
        "mark_value": mark_value,
    }
