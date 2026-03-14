"""
Procesamiento de imágenes y audio con Gemini Vision/Audio.
SDK: google-genai (nuevo).
Estas funciones son llamadas directamente desde main.py (no como tools del agente).
El resultado se inyecta en el mensaje al agente para que arranque el flujo de confirmación.
"""

import os
import json
import re
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"


def _get_client() -> genai.Client:
    return genai.Client(api_key=os.environ["GOOGLE_API_KEY"])


def _limpiar_json(text: str) -> str:
    """Elimina bloques de código markdown si Gemini los agrega."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


# ──────────────────────────────────────────────
# Fotos de tickets / facturas
# ──────────────────────────────────────────────

_PROMPT_TICKET = """
Analizá esta imagen de un ticket o factura y extraé la información en JSON con esta estructura exacta:
{
  "comercio": "nombre del comercio o local (string, o null si no es visible)",
  "fecha": "fecha en formato YYYY-MM-DD (string, o null si no aparece)",
  "monto_total": <número float con el total a pagar, o null>,
  "moneda": "ARS o USD",
  "items": [
    {"descripcion": "...", "monto": 0.0}
  ],
  "notas": "cualquier dato adicional relevante del ticket (string, o null)"
}

Reglas:
- Si el ticket no tiene fecha visible, usar null.
- Si hay ambigüedad en el total (subtotal vs total con impuestos), usar el total final.
- Si la moneda no está explícita, asumir ARS.
- Respondé ÚNICAMENTE con el JSON válido, sin explicaciones ni texto adicional.
"""


def procesar_imagen_ticket(imagen_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Extrae datos estructurados de una foto de ticket/factura usando Gemini Vision.

    Args:
        imagen_bytes: Bytes de la imagen (JPEG, PNG, WEBP).
        mime_type: MIME type de la imagen.

    Returns:
        Dict con: comercio, fecha, monto_total, moneda, items, notas.
        Campos no visibles vienen como None.
    """
    client = _get_client()

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type),
            types.Part(text=_PROMPT_TICKET),
        ],
    )

    try:
        data = json.loads(_limpiar_json(response.text))
    except json.JSONDecodeError:
        logger.warning(f"Gemini Vision devolvió JSON inválido: {response.text[:300]}")
        data = {"error": "No pude extraer datos estructurados de la imagen."}

    return data


# ──────────────────────────────────────────────
# Notas de voz
# ──────────────────────────────────────────────

_PROMPT_AUDIO = """
Escuchá este audio y realizá dos tareas:
1. Transcribí exactamente lo que se dice.
2. Si se menciona algún gasto, extraé los datos financieros.

Respondé ÚNICAMENTE con JSON válido con esta estructura:
{
  "transcripcion": "texto completo del audio",
  "tiene_gasto": true o false,
  "descripcion": "descripción del gasto (string, o null si no hay)",
  "monto": <número float, o null>,
  "moneda": "ARS o USD (o null si no se especifica)",
  "medio_pago": "medio de pago mencionado (o null)",
  "fecha": "fecha en formato YYYY-MM-DD si se menciona (o null)",
  "notas": "cualquier dato adicional relevante (o null)"
}

Reglas:
- Si no se menciona ningún gasto, `tiene_gasto` es false y el resto de campos financieros son null.
- Si la moneda no se especifica, asumir ARS.
- Respondé ÚNICAMENTE con el JSON válido, sin texto adicional.
"""


def procesar_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> dict:
    """
    Transcribe y extrae intención financiera de una nota de voz con Gemini Audio.

    Args:
        audio_bytes: Bytes del archivo de audio.
        mime_type: MIME type del audio. Telegram voice notes son 'audio/ogg'.

    Returns:
        Dict con: transcripcion, tiene_gasto, descripcion, monto, moneda, medio_pago, fecha, notas.
    """
    client = _get_client()

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            types.Part(text=_PROMPT_AUDIO),
        ],
    )

    try:
        data = json.loads(_limpiar_json(response.text))
    except json.JSONDecodeError:
        logger.warning(f"Gemini Audio devolvió JSON inválido: {response.text[:300]}")
        data = {
            "transcripcion": response.text,
            "tiene_gasto": False,
            "error": "No pude estructurar el audio.",
        }

    return data


# ──────────────────────────────────────────────
# Helpers para formatear el resultado como
# mensaje de texto para el agente
# ──────────────────────────────────────────────

def ticket_a_mensaje(datos: dict) -> str:
    """
    Convierte el resultado de procesar_imagen_ticket en un mensaje de texto
    para pasarle al agente como si fuera input del usuario.
    """
    if "error" in datos:
        return f"El usuario mandó una foto de ticket pero no pude extraer los datos: {datos['error']}"

    partes = ["El usuario mandó una foto de ticket. Datos extraídos:"]
    if datos.get("comercio"):
        partes.append(f"- Comercio: {datos['comercio']}")
    if datos.get("monto_total") is not None:
        partes.append(f"- Monto total: {datos['monto_total']} {datos.get('moneda', 'ARS')}")
    if datos.get("fecha"):
        partes.append(f"- Fecha: {datos['fecha']}")
    if datos.get("notas"):
        partes.append(f"- Notas: {datos['notas']}")

    partes.append("\nUsá estos datos para proponer el gasto al usuario siguiendo el flujo normal de confirmación.")
    return "\n".join(partes)


def audio_a_mensaje(datos: dict) -> str:
    """
    Convierte el resultado de procesar_audio en un mensaje de texto
    para pasarle al agente.
    """
    if not datos.get("tiene_gasto"):
        transcripcion = datos.get("transcripcion", "(audio sin transcripción)")
        return f'El usuario mandó un audio que dice: "{transcripcion}". No parece ser un gasto. Respondé en consecuencia.'

    partes = [f'El usuario mandó un audio que dice: "{datos.get("transcripcion", "")}".']
    partes.append("Datos financieros detectados:")
    if datos.get("descripcion"):
        partes.append(f"- Descripción: {datos['descripcion']}")
    if datos.get("monto") is not None:
        partes.append(f"- Monto: {datos['monto']} {datos.get('moneda', 'ARS')}")
    if datos.get("medio_pago"):
        partes.append(f"- Medio de pago: {datos['medio_pago']}")
    if datos.get("fecha"):
        partes.append(f"- Fecha: {datos['fecha']}")

    partes.append("\nUsá estos datos para proponer el gasto al usuario siguiendo el flujo normal de confirmación.")
    return "\n".join(partes)
