Bot Loteria — Twitter (X) + Multirrede (Versão Vídeo)
​Publica automaticamente os resultados das loterias (Imagens e Vídeos) a partir de uma planilha do Google Sheets.
​Suporta:
​X (Twitter) v2 — multi-contas ✅
​Telegram (Bot API) ✅
​Discord (Webhook) ✅
​Pinterest (API v5) ✅
​Facebook Páginas (Graph API) ✅
​📦 Requisitos
​Python 3.10+
​FFmpeg & ImageMagick (Instalados no sistema para geração de vídeo)
​Credenciais de Service Account do Google (JSON)
​Credenciais das redes via Cofre (Google Sheets)
​🗂️ Estrutura Atualizada
​twitter-loteria-bot/
├── app/
│   └── imaging.py                 # Gerador de Imagens (Pillow)
├── assets/
│   ├── fundos/                    # Fundos para artes
│   └── logos/                     # Logos das loterias
├── output/                        # Artes e Vídeos finais (.png e .mp4)
├── gerador_video.py # [NOVO] Edição de vídeo via MoviePy
├── bot.py                         # Publicador Multirrede (X/FB/TG/Discord/PIN)
├── requirements.txt               # Dependências Python (Atualizado com MoviePy)
└── .github/
└── workflows/
└── publish.yml # CI: Agora instala FFmpeg e gera MP4