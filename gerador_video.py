"""Compatibilidade do gerador de vídeos do Portal SimonSports.

A implementação ativa está em gerador_pacote_v17.py. O vídeo completo utiliza
dois apresentadores em diálogo natural, sem alternância entre as dezenas. O
Short utiliza uma única voz. As quatro vozes aprovadas são alternadas de forma
automática entre os concursos, com fallback individual se a dupla não puder ser
gerada.
"""

from gerador_pacote_v17 import *  # noqa: F401,F403
