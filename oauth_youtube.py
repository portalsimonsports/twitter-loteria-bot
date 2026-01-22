from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",  # JSON que você acabou de baixar
    scopes=SCOPES
)

creds = flow.run_local_server(port=0)

print("\nREFRESH_TOKEN:")
print(creds.refresh_token)