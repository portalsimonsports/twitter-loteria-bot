"""Compatibilidade com integrações antigas do gerador de vídeos.

A geração ativa está na V16. Cada edição utiliza uma única voz, alternando entre
Francisca, Thalita e Antônio nos concursos seguintes. A fala de cada dezena é
sincronizada com o momento em que a bola já está visível no quadro, mantendo o
encaixe automático sem sobreposição.
"""

from gerador_pacote_v16 import *  # noqa: F401,F403
