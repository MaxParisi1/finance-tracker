"""
Script para obtener las credenciales OAuth2 de Google Drive por primera vez.
Ejecutar UNA sola vez localmente.

Usa el mismo credentials.json que Gmail (mismo proyecto de Google Cloud).

Uso:
  1. Asegurate de tener bot/credentials.json
  2. Corré: python -m bot.auth_drive
  3. Se abre el browser para autorizar acceso a Drive
  4. Pegá los valores en bot/.env y corré `sync-env` para subirlos al servidor
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file("bot/credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n=== PEGÁ ESTOS VALORES EN bot/.env ===")
    print(f"DRIVE_REFRESH_TOKEN={creds.refresh_token}")
    print(f"DRIVE_CLIENT_ID={creds.client_id}")
    print(f"DRIVE_CLIENT_SECRET={creds.client_secret}")
    print("=======================================")
    print("\nDespués corré `sync-env` para subirlo al servidor y reiniciar el bot.")


if __name__ == "__main__":
    main()
