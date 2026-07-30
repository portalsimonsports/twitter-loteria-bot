"""Compatibilidade com integrações antigas do gerador de vídeos.

A geração ativa está na V15. Cada edição utiliza uma única voz, alternando entre
Francisca, Thalita e Antônio nos concursos seguintes. A locução é encaixada
automaticamente nos intervalos disponíveis, sem sobreposição e sem interromper a
geração do Short quando uma fala precisa de pequeno ajuste de velocidade.
"""

from gerador_pacote_v15 import *  # noqa: F401,F403
