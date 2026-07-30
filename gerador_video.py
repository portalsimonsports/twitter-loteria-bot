"""Compatibilidade do gerador de vídeos do Portal SimonSports.

A implementação ativa está em gerador_pacote_v14.py. Cada edição utiliza uma
única voz, alternando Francisca, Thalita e Antônio nos concursos seguintes.
A locução anuncia diretamente as dezenas e mede a duração real de cada fala
para impedir sobreposição. O método executar retorna o Short, enquanto
`gerar_pacote` também produz o vídeo completo horizontal de 165 segundos.
"""

from gerador_pacote_v14 import *  # noqa: F401,F403
