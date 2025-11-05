# -*- coding: utf-8 -*-
"""
Gerador opcional de imagens a partir da planilha.
- Lê: Loteria | Concurso | Data | Números | URL
- Gera PNGs em ./imagens_geradas
- NÃO publica nada (quem publica é o bot.py)
- Seguro para usar em runner do GitHub Actions ou local
"""

import os
import json
import datetime as dt
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from .imaging import gerar_imagem_loteria

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
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
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
    ws = _open_ws()
    rows = ws.get_all_records()  # usa cabeçalhos da primeira linha
    out_dir = os.getenv("IMAGES_OUT_DIR", "imagens_geradas")
    os.makedirs(out_dir, exist_ok=True)

    geradas = 0
    for i, row in enumerate(rows, start=2):
        try:
            loteria = str(row.get("Loteria", "")).strip()
            concurso = str(row.get("Concurso", "")).strip()
            data_br = str(row.get("Data", "")).strip()
            numeros = str(row.get("Números", "")).strip() or str(row.get("Numeros", "")).strip()
            url = str(row.get("URL", "")).strip()

            if not loteria or not numeros:
                continue

            _log(f"Gerando imagem L{i}: {loteria} {concurso} ({data_br})")
            buf = gerar_imagem_loteria(loteria, concurso, data_br, numeros, url)

            # nome amigável
            loteria_slug = (
                loteria.lower()
                .replace(" ", "-")
                .replace("ç", "c")
                .replace("á", "a")
                .replace("é", "e")
                .replace("í", "i")
                .replace("ó", "o")
                .replace("ú", "u")
                .replace("ã", "a")
                .replace("õ", "o")
            )
            fname = f"{loteria_slug}_{concurso or i}.png"
            path = os.path.join(out_dir, fname)
            with open(path, "wb") as f:
                f.write(buf.read())
            geradas += 1
            _log(f"✅ salva: {path}")
        except Exception as e:
            _log(f"ERRO na linha {i}: {e}")

    _log(f"Concluído. Imagens geradas: {geradas}")

if __name__ == "__main__":
    gerar_imagens_automaticamente()