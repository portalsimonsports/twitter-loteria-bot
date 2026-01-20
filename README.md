Bot Loteria — Twitter (X) + Multirrede (Versão Vídeo)
Publica automaticamente os resultados das loterias (Imagens e Vídeos) a partir de uma planilha do Google Sheets.
Suporta:
X (Twitter) v2 — multi-contas ✅
Telegram (Bot API) ✅
Discord (Webhook) ✅
Pinterest (API v5) ✅
Facebook Páginas (Graph API) ✅
📦 Requisitos
Python 3.10+
FFmpeg & ImageMagick (instalados no sistema para geração de vídeo)
Credenciais de Service Account do Google (JSON)
Credenciais das redes via Cofre (Google Sheets)

Estrutura Atualizada (SEM REMOVER NADA)

twitter-loteria-bot/
├── app/
│   └── imaging.py                 # Gerador de Imagens (Pillow)
│
├── assets/
│   ├── fundos/                    # Fundos para artes
│   └── logos/                     # Logos das loterias
│
├── output/                        # Artes e Vídeos finais (.png e .mp4)
│   ├── images/                    # (Opcional) Imagens finais em PNG
│   └── videos/                    # (Opcional) Vídeos finais em MP4
│
├── gerador_video.py               # [NOVO] Edição e renderização de vídeos via MoviePy
│                                   # Usa FFmpeg e ImageMagick para animações, zoom, fade e exportação MP4
│
├── bot.py                         # Publicador Multirrede:
│                                   # X (Twitter v2 – multi-contas)
│                                   # Telegram (Bot API)
│                                   # Discord (Webhook)
│                                   # Pinterest (API v5)
│                                   # Facebook Páginas (Graph API)
│                                   # Lê dados da planilha e do Cofre
│                                   # Publica imagem e vídeo automaticamente
│
├── requirements.txt               # Dependências Python (Pillow, MoviePy, Tweepy, gspread, etc.)
│
└── .github/
    └── workflows/
        └── publish.yml            # CI/CD:
                                    # - Instala FFmpeg e ImageMagick
                                    # - Instala dependências Python
                                    # - Executa bot.py
                                    # - Gera PNG e MP4 automaticamente
                                    # - Publica nas redes