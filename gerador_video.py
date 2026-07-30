"""Compatibilidade do gerador de vídeos do Portal SimonSports.

A implementação ativa está em gerador_pacote_v15.py. Cada edição utiliza uma
única voz, alternando Francisca, Thalita e Antônio nos concursos seguintes. A
locução anuncia diretamente as dezenas e ajusta automaticamente cada fala ao
intervalo disponível, impedindo sobreposição sem abortar a geração do vídeo.
"""

from gerador_pacote_v15 import *  # noqa: F401,F403
