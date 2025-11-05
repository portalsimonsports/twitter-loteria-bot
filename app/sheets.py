import gspread
import datetime
import pytz
from oauth2client.service_account import ServiceAccountCredentials

def conectar_planilha(google_service_json, sheet_id, sheet_tab):
    """Conecta ao Google Sheets e retorna a aba"""
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = ServiceAccountCredentials.from_json_keyfile_dict(google_service_json, escopo)
    cliente = gspread.authorize(credenciais)
    planilha = cliente.open_by_key(sheet_id)
    return planilha.worksheet(sheet_tab)

def buscar_linhas_para_publicar(sheet, coluna_publicados="H"):
    """Lê linhas da planilha e retorna somente as ainda não publicadas"""
    dados = sheet.get_all_records()
    linhas_publicar = []
    for linha in dados:
        if not linha.get(coluna_publicados):
            linhas_publicar.append(linha)
    return linhas_publicar