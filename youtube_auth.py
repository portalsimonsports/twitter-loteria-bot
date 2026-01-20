import requests

def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """
    Troca REFRESH_TOKEN por ACCESS_TOKEN (YouTube Data API via OAuth2).
    """
    url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    r = requests.post(url, data=data, timeout=30)
    r.raise_for_status()
    j = r.json() or {}
    token = (j.get("access_token") or "").strip()
    if not token:
        raise RuntimeError(f"Falha ao obter access_token. Resposta: {j}")
    return token