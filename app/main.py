# -*- coding: utf-8 -*-
"""
Gerador opcional de imagens a partir da planilha.
- Lê: Loteria | Concurso | Data | Números | URL
- Gera JPGs em ./output (ou IMAGES_OUT_DIR, se definido)
- NÃO publica nada (quem publica é o bot.py)
- Seguro para usar em runner do GitHub Actions ou local.

IMPORTANTE:
- Para cada combinação (loteria, concurso) gera SEMPRE o mesmo
  nome de arquivo: <slug-loteria>-<concurso>.jpg
- Se o arquivo já existir, ele é SOBRESCRITO (não cria -1, -2, ...).
"""

import os
import json
import datetime as dt
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image

from .imaging import gerar_imagem_loteria, _slug  # reaproveita o slug oficial

TZ = pytz.timezone("America/Sao_Paulo")


# --------- Google Sheets ----------
def _google_client():
    sa_raw = os.getenv("GOOGLE_SERVICE_JSON", "").strip()
    if not sa_raw:
        raise RuntimeError("GOOGLE_SERVICE_JSON ausente.")
    try:
        info = json.loads(sa_raw)
    except Exception as e:
        raise RuntimeError(f"GOOGLE_SERVICE_JSON inválido: {e}")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scopes)
    return gspread.authorize(creds)


def _open_ws():
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    sheet_tab = os.getenv("SHEET_TAB", "ImportadosBlogger2").strip()
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID ausente.")
    sh = _google_client().open_by_key(sheet_id)
    return sh.worksheet(sheet_tab)


def _log(msg):
    print(f"[{dt.datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# --------- Execução ----------
def gerar_imagens_automaticamente():
    """
    Lê TODAS as linhas da guia configurada e gera uma imagem para
    cada linha com loteria/números preenchidos.

    Nome do arquivo:
      - Se tiver concurso:  <slug-loteria>-<concurso>.jpg
      - Se NÃO tiver concurso: <slug-loteria>-linha-<n>.jpg

    Saída:
      - Pasta: IMAGES_OUT_DIR (env) ou "output" por padrão.
      - Formato: JPEG (RGB), sobrescrevendo arquivos existentes.
    """
    ws = _open_ws()
    rows = ws.get_all_records()  # usa cabeçalhos da primeira linha

    out_dir = os.getenv("IMAGES_OUT_DIR", "output").strip() or "output"
    os.makedirs(out_dir, exist_ok=True)
    _log(f"Saída de imagens em: {os.path.abspath(out_dir)}")

    geradas = 0
    for i, row in enumerate(rows, start=2):  # i = número real da linha (considerando cabeçalho)
        try:
            loteria = str(row.get("Loteria", "")).strip()
            concurso = str(row.get("Concurso", "")).strip()
            data_br = str(row.get("Data", "")).strip()
            numeros = (
                str(row.get("Números", "")).strip()
                or str(row.get("Numeros", "")).strip()
            )
            url = str(row.get("URL", "")).strip()

            # Ignora linhas vazias/sem conteúdo relevante
            if not loteria or not numeros:
                continue

            _log(f"Gerando imagem L{i}: {loteria} {concurso} ({data_br})")

            # Gera imagem em buffer PNG (função padrão do imaging.py)
            buf = gerar_imagem_loteria(loteria, concurso, data_br, numeros, url)

            # Define nome "limpo" (slug oficial da imaging.py)
            loteria_slug = _slug(loteria) or "loteria"
            if concurso:
                fname = f"{loteria_slug}-{concurso}.jpg"
            else:
                fname = f"{loteria_slug}-linha-{i}.jpg"

            path = os.path.join(out_dir, fname)

            # Converte o buffer (PNG) para JPEG RGB e SALVA (sobrescreve)
            buf.seek(0)
            with Image.open(buf) as im:
                rgb = im.convert("RGB")
                rgb.save(path, "JPEG", quality=95, optimize=True)

            geradas += 1
            _log(f"✅ salva: {path}")

        except Exception as e:
            _log(f"ERRO na linha {i}: {e}")

    _log(f"Concluído. Imagens geradas: {geradas}")


if __name__ == "__main__":
    gerar_imagens_automaticamente()
