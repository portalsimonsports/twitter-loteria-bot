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

