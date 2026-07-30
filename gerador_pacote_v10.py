"""Compatibilidade com integrações antigas do gerador de vídeos.

A geração ativa está na V17. O vídeo completo utiliza dois apresentadores em
interação natural; cada conjunto de dezenas é lido por uma única voz, sem troca
número a número. O Short permanece com apresentação individual e as vozes são
alternadas automaticamente entre os concursos. Se o diálogo não puder ser
gerado, o vídeo completo usa automaticamente uma única voz aprovada.
"""

from gerador_pacote_v17 import *  # noqa: F401,F403
