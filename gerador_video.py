"""Compatibilidade do gerador de vídeos do Portal SimonSports.

A implementação ativa está em gerador_pacote_v16.py. Cada edição utiliza uma
única voz, alternando Francisca, Thalita e Antônio nos concursos seguintes. A
locução anuncia diretamente as dezenas, sem ordinal, e começa quando o número já
está visível no quadro, mantendo o áudio sem sobreposição.
"""

from gerador_pacote_v16 import *  # noqa: F401,F403
