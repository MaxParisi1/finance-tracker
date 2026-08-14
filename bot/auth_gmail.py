"""
Script para obtener las credenciales OAuth2 de Gmail por primera vez.
Ejecutar UNA sola vez localmente; es una herramienta de desarrollo, no corre en el servidor.

Requisitos previos:
  pip install google-auth-oauthlib

Uso:
  1. Descargá credentials.json desde Google Cloud Console y ponelo en bot/
  2. Corré: python -m bot.auth_gmail
  3. Se abre el browser para autorizar acceso
  4. Pegá los 3 valores que imprime en bot/.env
  5. Corré `sync-env` para copiarlo al servidor y reiniciar el bot
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file("bot/credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n=== PEGÁ ESTOS VALORES EN bot/.env ===")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print("=======================================")
    print("\nDespués corré `sync-env` para subirlo al servidor y reiniciar el bot.")

    # Guardar también como token.json para testing local
    with open("bot/token.json", "w") as f:
        f.write(creds.to_json())
    print("\ntoken.json guardado para testing local.")


if __name__ == "__main__":
    main()
