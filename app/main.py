import os
import json
import datetime
import pytz
from .sheets import conectar_planilha, buscar_linhas_para_publicar
from .imaging import gerar_imagem_loteria

def gerar_imagens_automaticamente():
    tz = pytz.timezone("America/Sao_Paulo")
    agora = datetime.datetime.now(tz)
    print(f"[{agora.strftime('%H:%M:%S')}] Iniciando geração de imagens...")

    google_json_str = os.getenv("GOOGLE_SERVICE_JSON")
    if not google_json_str:
        raise ValueError("GOOGLE_SERVICE_JSON não definido.")

    google_json = json.loads(google_json_str)
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    sheet_tab = os.getenv("SHEET_TAB", "ImportadosBlogger2")

    aba = conectar_planilha(google_json, sheet_id, sheet_tab)
    linhas = buscar_linhas_para_publicar(aba)

    pasta_saida = "imagens_geradas"
    os.makedirs(pasta_saida, exist_ok=True)

    for linha in linhas:
        loteria = linha.get("Loteria")
        concurso = linha.get("Concurso")
        data = linha.get("Data")
        numeros = linha.get("Números")
        url = linha.get("URL")

        if not loteria or not numeros:
            continue

        print(f"Gerando imagem: {loteria} {concurso} ({data})")
        buffer = gerar_imagem_loteria(loteria, concurso, data, numeros, url)

        caminho = os.path.join(pasta_saida, f"{loteria}_{concurso}.png")
        with open(caminho, "wb") as f:
            f.write(buffer.read())

        print(f"✅ Imagem salva: {caminho}")

if __name__ == "__main__":
    gerar_imagens_automaticamente()