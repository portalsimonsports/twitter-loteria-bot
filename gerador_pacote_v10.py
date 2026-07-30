"""Compatibilidade com integrações antigas do gerador de vídeos.

A geração ativa está na V18. O vídeo completo mantém dois apresentadores, o Short
usa uma única voz e as modalidades especiais exibem e narram Trevos da Sorte,
Time do Coração e Mês da Sorte. A Loteca utiliza um formato próprio para os 14
jogos, com duração ampliada e interação entre os apresentadores.
"""

from gerador_pacote_v18 import *  # noqa: F401,F403
