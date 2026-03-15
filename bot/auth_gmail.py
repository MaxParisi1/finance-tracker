"""
Script para obtener las credenciales OAuth2 de Gmail por primera vez.
Ejecutar UNA sola vez localmente. NO se deploya a Fly.io.

Requisitos previos:
  pip install google-auth-oauthlib

Uso:
  1. Descargá credentials.json desde Google Cloud Console y ponelo en bot/
  2. Corré: python -m bot.auth_gmail
  3. Se abre el browser para autorizar acceso
  4. Copiá los 3 valores que imprime y setealos en Fly.io con:
       fly secrets set GMAIL_REFRESH_TOKEN=... GMAIL_CLIENT_ID=... GMAIL_CLIENT_SECRET=...
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file("bot/credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n=== COPIÁ ESTOS VALORES A FLY.IO SECRETS ===")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print("=============================================")
    print("\nComando para setear en Fly.io (desde la carpeta bot/):")
    print(
        f"fly secrets set "
        f"GMAIL_REFRESH_TOKEN={creds.refresh_token} "
        f"GMAIL_CLIENT_ID={creds.client_id} "
        f"GMAIL_CLIENT_SECRET={creds.client_secret}"
    )

    # Guardar también como token.json para testing local
    with open("bot/token.json", "w") as f:
        f.write(creds.to_json())
    print("\ntoken.json guardado para testing local.")


if __name__ == "__main__":
    main()
