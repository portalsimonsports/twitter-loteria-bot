import re
import unicodedata

CORES_LOTERIAS = {
    "mega-sena": "#206069",
    "quina": "#4B0082",
    "lotofácil": "#DD4A91",
    "lotomania": "#FF8C00",
    "timemania": "#00A650",
    "dupla sena": "#8B0000",
    "federal": "#8B4513",
    "dia de sorte": "#FFD700",
    "super sete": "#FF4500",
    "loteca": "#38761d",
}

LOGOS_LOTERIAS = {
    "mega-sena": "https://loterias.caixa.gov.br/Site/Imagens/loterias/megasena.png",
    "quina": "https://loterias.caixa.gov.br/Site/Imagens/loterias/quina.png",
    "lotofácil": "https://loterias.caixa.gov.br/Site/Imagens/loterias/lotofacil.png",
    "lotomania": "https://loterias.caixa.gov.br/Site/Imagens/loterias/lotomania.png",
    "timemania": "https://loterias.caixa.gov.br/Site/Imagens/loterias/timemania.png",
    "dupla sena": "https://loterias.caixa.gov.br/Site/Imagens/loterias/duplasena.png",
    "federal": "https://loterias.caixa.gov.br/Site/Imagens/loterias/federal.png",
    "dia de sorte": "https://loterias.caixa.gov.br/Site/Imagens/loterias/diadesorte.png",
    "super sete": "https://loterias.caixa.gov.br/Site/Imagens/loterias/supersete.png",
    "loteca": "https://loterias.caixa.gov.br/Site/Imagens/loterias/loteca.png",
}

NUMEROS_POR_LOTERIA = {
    "mega-sena": 6, "quina": 5, "lotofácil": 15, "lotomania": 20,
    "timemania": 10, "dupla sena": 6, "federal": 5, "dia de sorte": 7,
    "super sete": 7, "loteca": 14,
}

def norm_key(name: str) -> str:
    n = unicodedata.normalize('NFD', str(name or '').strip().lower())
    n = ''.join(c for c in n if unicodedata.category(c) != 'Mn')
    n = n.replace('mega sena', 'mega-sena')
    n = n.replace('lotofacil', 'lotofácil')
    n = n.replace('duplasena', 'dupla sena')
    n = re.sub(r'\s+', ' ', n).strip()
    return n