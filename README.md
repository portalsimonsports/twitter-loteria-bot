# Bot Loteria — Twitter (X) + Multirrede

Publica automaticamente os resultados das loterias a partir de uma planilha do Google Sheets.
Suporta:
- **X (Twitter) v2** — multi-contas via `create_tweet`
- **Telegram** (Bot API) ✅
- **Discord** (Webhook) ✅
- **Pinterest** (API v5) ✅
- **Facebook Páginas** (Graph API) ✅

> Texto padronizado com **“Confira: <link>”** no topo. Regra de publicação após **22h45 BRT** (configurável).

---

## 📦 Requisitos

- Python **3.10+**
- Credenciais de **Service Account** do Google (JSON) para acesso à planilha
- Credenciais das redes (ver `.env.example` abaixo)

---

## 🗂️ Estrutura

twitter-loteria-bot/
├── app/
│   └── imaging.py                 # Fallback de imagem (Pillow)
├── assets/
│   ├── fundos/                    # fundos/<slug>.jpg  (ex.: mega-sena.jpg)
│   └── logos/                     # logos/<slug>.png   (ex.: mega-sena.png)
├── data/
│   └── to_publish.json            # Fila (gerada pelo GAS)
├── output/                        # Artes finais (geradas pelo render)
├── templates/
│   └── post-instagram.html        # Template HTML/CSS (Opção B 3D)
├── bot.py                         # Publicador (X/Telegram/Discord/Facebook/Pinterest)
├── render.js                      # Gera imagens 1080×1080 com Puppeteer
├── requirements.txt               # Dependências do bot.py
├── package.json                   # Dependências/scripts do render.js
├── .env.exemple                   # Modelo de variáveis
└── .github/
    └── workflows/
        └── publish.yml            # CI: gera imagens e publica
