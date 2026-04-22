"""
Cliente Gmail API.
Se autentica con un refresh token guardado en variables de entorno (sin archivos locales).
"""

import base64
import logging
import os
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
LABEL_NAME = "Consumos"
LABEL_NAME_VISA = "Consumos_visa"


def _get_credentials() -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def get_unread_bank_emails(label_name: str = LABEL_NAME) -> list[dict]:
    """Devuelve los emails no leídos de la etiqueta indicada."""
    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    labels_result = service.users().labels().list(userId="me").execute()
    label_id = next(
        (l["id"] for l in labels_result.get("labels", []) if l["name"].lower() == label_name.lower()),
        None,
    )

    if not label_id:
        logger.warning(f"Etiqueta '{label_name}' no encontrada en Gmail")
        return []

    result = service.users().messages().list(
        userId="me",
        labelIds=[label_id, "UNREAD"],
        maxResults=10,
    ).execute()

    emails = []
    for msg_ref in result.get("messages", []):
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        body = _extract_body(msg["payload"])

        emails.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body,
        })

    return emails


def mark_as_read(message_id: str) -> None:
    """Marca un mensaje de Gmail como leído."""
    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()


def _extract_body(payload: dict) -> str:
    """Extrae el texto del cuerpo de un mensaje Gmail (prefiere text/plain, fallback HTML)."""
    plain = _find_part(payload, "text/plain")
    if plain:
        return plain

    html = _find_part(payload, "text/html")
    if html:
        # Reemplaza elementos de bloque con saltos de línea antes de quitar tags
        html = re.sub(r"</?(tr|td|br|p|div|table|span)[^>]*>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\n[ \t]*\n+", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    return ""


def _find_part(payload: dict, mime_type: str) -> str:
    """Busca recursivamente una parte con el MIME type dado y devuelve su texto decodificado."""
    if payload.get("mimeType") == mime_type:
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        result = _find_part(part, mime_type)
        if result:
            return result

    return ""
