from __future__ import annotations

"""Fila de vídeos das loterias para YouTube.

Fluxo:
1. lê a aba principal do Google Sheets;
2. seleciona linhas com Enfileirado_Videos preenchido e Publicado_Youtube vazio;
3. gera um único MP4 por resultado;
4. envia o mesmo MP4 para todas as contas YouTube cadastradas no Cofre;
5. grava o resumo de publicação na coluna Publicado_Youtube.
"""

import json
import os
import re
import time
import traceback
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from post_video import publicar_video_em_multicanais

TRUE_VALUES = {"1", "true", "sim", "yes", "y", "on", "ok", "enfileirado", "fila", "publicar"}
FALSE_VALUES = {"0", "false", "nao", "não", "no", "n", "off", "cancelado", "cancelada"}


@dataclass(frozen=True)
class Config:
    google_sheet_id: str
    sheet_tab: str
    cofre_sheet_id: str
    cofre_aba_cred: str
    enfileirado_col: str
    publicado_col: str
    max_videos: int
    pausa: float
    dry_run: bool
    timezone: str


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    return _env(name, "true" if default else "false").lower() in TRUE_VALUES


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 1000) -> int:
    try:
        value = int(_env(name, str(default)))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float = 0.0, maximum: float = 3600.0) -> float:
    try:
        value = float(_env(name, str(default)))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def carregar_config() -> Config:
    return Config(
        google_sheet_id=_env("GOOGLE_SHEET_ID", "16NcdSwX6q_EQ2XjS1KNIBe6C3Piq-lCBgA38TMszXCI"),
        sheet_tab=_env("SHEET_TAB", "ImportadosBlogger2"),
        cofre_sheet_id=_env("COFRE_SHEET_ID"),
        cofre_aba_cred=_env("COFRE_ABA_CRED", "Credenciais_Rede"),
        enfileirado_col=_env("ENFILEIRADO_VIDEOS_COL", "Enfileirado_Videos"),
        publicado_col=_env("PUBLICADO_YT_COL", "Publicado_Youtube"),
        max_videos=_env_int("MAX_VIDEOS_RODADA", 10, 1, 50),
        pausa=_env_float("PAUSA_ENTRE_VIDEOS", 2.0, 0.0, 120.0),
        dry_run=_env_bool("DRY_RUN_VIDEOS", False),
        timezone=_env("TZ", "America/Sao_Paulo"),
    )


def _log(*args: Any) -> None:
    print("[VIDEO_QUEUE]", *args, flush=True)


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    replacements = str.maketrans({
        "á": "a", "à": "a", "ã": "a", "â": "a",
        "é": "e", "ê": "e", "í": "i",
        "ó": "o", "ô": "o", "õ": "o",
        "ú": "u", "ç": "c",
    })
    text = text.translate(replacements)
    return re.sub(r"[^a-z0-9]+", "", text)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _norm(value)).strip("-")


def _truthy_queue(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    normalized = _norm(text)
    false_values = {_norm(v) for v in FALSE_VALUES}
    if normalized in false_values:
        return False
    return bool(normalized)


def _empty(value: Any) -> bool:
    return str(value or "").strip() == ""


def _header_map(headers: Sequence[str]) -> Dict[str, int]:
    return {_norm(name): index for index, name in enumerate(headers) if _norm(name)}


def _find_col(headers: Sequence[str], candidates: Iterable[str], required: bool = False) -> Optional[int]:
    normalized = _header_map(headers)
    for candidate in candidates:
        key = _norm(candidate)
        if key in normalized:
            return normalized[key]
    if required:
        raise RuntimeError(f"Coluna obrigatória não encontrada. Esperado um de: {', '.join(candidates)}")
    return None


def _ensure_column(ws: Any, headers: List[str], name: str) -> int:
    existing = _find_col(headers, [name])
    if existing is not None:
        return existing
    col_number = len(headers) + 1
    current_cols = int(getattr(ws, "col_count", len(headers)) or len(headers))
    if current_cols < col_number:
        ws.add_cols(col_number - current_cols)
    ws.update_cell(1, col_number, name)
    headers.append(name)
    _log(f"Coluna criada: {name} ({col_number})")
    return col_number - 1


def _google_client() -> Any:
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
    except ImportError as exc:
        raise RuntimeError("Dependências Google ausentes. Execute pip install -r requirements.txt") from exc

    raw = _env("GOOGLE_SERVICE_JSON")
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_JSON ausente nos secrets do GitHub.")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GOOGLE_SERVICE_JSON inválido: {exc}") from exc

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(info, scopes)
    return gspread.authorize(credentials)


def _load_cofre(client: Any, cfg: Config):
    if not cfg.cofre_sheet_id:
        raise RuntimeError("COFRE_SHEET_ID ausente nas Variables/Secrets do GitHub.")

    ws = client.open_by_key(cfg.cofre_sheet_id).worksheet(cfg.cofre_aba_cred)
    values = ws.get_all_values()
    if not values:
        raise RuntimeError(f"Aba do Cofre vazia: {cfg.cofre_aba_cred}")

    headers = values[0]
    rede_i = _find_col(headers, ["Rede"], required=True)
    conta_i = _find_col(headers, ["Conta", "Canal", "Perfil"])
    chave_i = _find_col(headers, ["Chave", "Campo", "Nome"], required=True)
    valor_i = _find_col(headers, ["Valor", "Credencial", "Token"], required=True)

    creds_rows: List[Dict[str, str]] = []
    creds_rc: Dict[Tuple[str, str, str], str] = {}

    for row in values[1:]:
        def cell(index: Optional[int]) -> str:
            return str(row[index] if index is not None and index < len(row) else "").strip()

        rede = cell(rede_i).upper()
        conta = cell(conta_i).upper()
        chave = cell(chave_i).upper()
        valor = cell(valor_i)
        if rede and chave and valor:
            creds_rows.append({"rede": rede, "conta": conta, "chave": chave, "valor": valor})
            creds_rc[(rede, conta, chave)] = valor

    cache = {"creds_rows": creds_rows, "creds_rc": creds_rc}

    def cofre_get(rede: str, chave: str, conta: Optional[str] = None, default: str = "") -> str:
        rede_u = str(rede or "").strip().upper()
        chave_u = str(chave or "").strip().upper()
        conta_u = str(conta or "").strip().upper()
        if conta_u:
            value = creds_rc.get((rede_u, conta_u, chave_u), "")
            if value:
                return value
        value = creds_rc.get((rede_u, "", chave_u), "")
        if value:
            return value
        for (r, c, k), value in creds_rc.items():
            if r == rede_u and k == chave_u and value and (not conta_u or c == conta_u):
                return value
        return default

    return cache, cofre_get


def _parse_product(product: str, contest_value: str = "") -> Tuple[str, str]:
    product = str(product or "").strip()
    contest_value = str(contest_value or "").strip()
    if contest_value:
        return product or "Loteria", contest_value
    match = re.match(r"^(.*?)(?:\s+[-–—]?\s*)(\d{2,})$", product)
    if match:
        return match.group(1).strip(" -–—") or "Loteria", match.group(2)
    return product or "Loteria", ""


def _extract_numbers(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"^n[uú]meros?\s*:\s*", "", text, flags=re.I).strip()


def _asset_path(folder: str, loteria: str, extensions: Sequence[str]) -> str:
    slug = _slug(loteria)
    aliases = {
        "megasena": "mega-sena",
        "maismilionaria": "mais-milionaria",
        "diadesorte": "dia-de-sorte",
        "duplasena": "dupla-sena",
        "supersete": "super-sete",
        "loteriafederal": "loteria-federal",
    }
    slug = aliases.get(slug, slug)
    for extension in extensions:
        path = os.path.join("assets", folder, f"{slug}.{extension}")
        if os.path.exists(path):
            return path
    return ""


def _row_to_video_data(row: Sequence[str], headers: Sequence[str]) -> Dict[str, Any]:
    def pick(*names: str) -> str:
        idx = _find_col(headers, names)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx] or "").strip()

    product = pick("Produto", "Loteria", "Modalidade", "Jogo")
    contest_raw = pick("Concurso", "Numero_Concurso", "Número do Concurso")
    loteria, concurso = _parse_product(product, contest_raw)
    numbers = _extract_numbers(pick("Numeros", "Números", "Descricao", "Descrição", "Resultado"))
    data = pick("Data", "Data_Sorteio", "Data do Sorteio")
    url = pick("URL", "Link", "URL_Publicacao", "URL Blogger")
    premio = pick("Premio", "Prêmio", "Estimativa", "Premio_Estimado", "Prêmio estimado")
    image_path = pick("Imagem_Path", "Caminho_Imagem", "Arquivo_Imagem")

    if image_path and not os.path.exists(image_path):
        image_path = ""
    if not image_path:
        image_path = _asset_path("fundos", loteria, ["jpg", "jpeg", "png", "webp"])

    return {
        "loteria": loteria,
        "concurso": concurso,
        "numeros": numbers,
        "data": data,
        "url": url,
        "premio": premio,
        "imagem_path": image_path,
        "logo_path": _asset_path("logos", loteria, ["png", "webp", "jpg"]),
        "duracao": _env_float("DURACAO_VIDEO", 8.0, 4.0, 30.0),
        "title": f"Resultado {loteria} — Concurso {concurso}".strip(" —"),
        "description": (
            f"Resultado da {loteria} — Concurso {concurso}.\n"
            f"Números sorteados: {numbers}.\n"
            + (f"Data: {data}.\n" if data else "")
            + (f"Confira os detalhes: {url}\n" if url else "")
            + "\nPortal SimonSports — conteúdo informativo sobre resultados de loterias."
        ),
    }


def _validate_video_data(data: Mapping[str, Any]) -> None:
    missing = [name for name in ("loteria", "numeros") if not str(data.get(name) or "").strip()]
    if missing:
        raise RuntimeError(f"Dados insuficientes para gerar vídeo: {', '.join(missing)}")


def processar_fila() -> int:
    cfg = carregar_config()
    _log(f"Início | aba={cfg.sheet_tab} | max={cfg.max_videos} | dry_run={cfg.dry_run} | publicado={cfg.publicado_col}")

    client = _google_client()
    cofre_cache, cofre_get = _load_cofre(client, cfg)
    ws = client.open_by_key(cfg.google_sheet_id).worksheet(cfg.sheet_tab)
    values = ws.get_all_values()
    if not values:
        _log("Aba principal vazia.")
        return 0

    headers = list(values[0])
    queue_idx = _ensure_column(ws, headers, cfg.enfileirado_col)
    published_idx = _ensure_column(ws, headers, cfg.publicado_col)

    candidates: List[Tuple[int, Sequence[str]]] = []
    for sheet_row, row in enumerate(values[1:], start=2):
        queue_value = row[queue_idx] if queue_idx < len(row) else ""
        published_value = row[published_idx] if published_idx < len(row) else ""
        if _truthy_queue(queue_value) and _empty(published_value):
            candidates.append((sheet_row, row))

    if not candidates:
        _log("Nenhum vídeo pendente na fila.")
        return 0

    _log(f"Pendentes encontrados: {len(candidates)}; processando até {cfg.max_videos}.")
    successes = 0

    for sheet_row, row in candidates[: cfg.max_videos]:
        try:
            data = _row_to_video_data(row, headers)
            _validate_video_data(data)
            _log(f"Linha {sheet_row}: {data['loteria']} concurso {data['concurso'] or '-'}")

            result = publicar_video_em_multicanais(
                data,
                cofre_get,
                cofre_cache,
                dry_run=cfg.dry_run,
                sleep_between_channels=max(0.5, min(cfg.pausa, 15.0)),
                tz_name=cfg.timezone,
            )

            if result.get("ok_any"):
                if cfg.dry_run:
                    _log(f"Linha {sheet_row}: DRY RUN concluído; planilha não alterada.")
                else:
                    ws.update_cell(sheet_row, published_idx + 1, str(result.get("mark_value") or "Publicado YOUTUBE"))
                    successes += 1
                    _log(f"Linha {sheet_row}: publicada e marcada na planilha.")
            else:
                _log(f"Linha {sheet_row}: nenhuma publicação concluída. {result.get('mark_value', '')}")

        except Exception as exc:
            _log(f"Linha {sheet_row}: ERRO: {exc}")
            traceback.print_exc()

        time.sleep(cfg.pausa)

    _log(f"Fim | publicações confirmadas: {successes}")
    return successes


def main() -> None:
    processar_fila()


if __name__ == "__main__":
    main()
