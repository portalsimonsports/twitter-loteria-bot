from google_auth_oauthlib.flow import InstalledAppFlow

# O refresh token precisa autorizar tanto upload quanto gerenciamento do canal/Live.
# youtube.upload sozinho NÃO autoriza liveBroadcasts/liveStreams.
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
]

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",
    scopes=SCOPES,
)

# access_type=offline garante refresh token; prompt=consent força o Google a
# emitir um novo refresh token com os novos escopos mesmo se a conta já tiver
# autorizado a aplicação anteriormente.
creds = flow.run_local_server(
    port=0,
    access_type="offline",
    prompt="consent",
)

print("\nESCOPOS AUTORIZADOS:")
for scope in sorted(creds.scopes or SCOPES):
    print("-", scope)

print("\nREFRESH_TOKEN:")
print(creds.refresh_token)
