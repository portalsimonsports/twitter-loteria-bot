"""Compatibilidade do gerador de vídeos do Portal SimonSports.

A implementação ativa está em gerador_pacote_v13.py. Cada edição utiliza uma
única voz, alternando Francisca, Thalita e Antônio nos concursos seguintes.
O método executar retorna o Short, enquanto gerar_pacote também produz o vídeo
completo horizontal de 150 segundos.
"""

from gerador_pacote_v13 import *  # noqa: F401,F403
