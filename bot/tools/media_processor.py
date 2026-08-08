"""
Procesamiento de imágenes y audio con Gemini Vision/Audio.
SDK: google-genai (nuevo).
Estas funciones son llamadas directamente desde main.py (no como tools del agente).
El resultado se inyecta en el mensaje al agente para que arranque el flujo de confirmación.
"""

import json
import re
import logging
from google.genai import types

from bot.gemini_client import generate_with_fallback

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"


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
Analizá esta imagen. Puede ser un ticket de compra, una factura, o un comprobante de transferencia/pago (ej: Mercado Pago, banco, billetera virtual).

IMPORTANTE — Formato numérico argentino:
- El punto (.) es separador de MILES. Ejemplo: $10.600 = diez mil seiscientos (10600), NO 10.6.
- La coma (,) es separador decimal. Ejemplo: $1.250,50 = mil doscientos cincuenta con cincuenta centavos.
- Siempre convertí el monto a un número float sin separadores de miles. $10.600 → 10600.0

Extraé la información en JSON con esta estructura exacta:
{
  "tipo": "ticket" | "transferencia" | "factura",
  "comercio": "nombre del comercio, destinatario o local (string, o null si no es visible)",
  "fecha": "fecha en formato YYYY-MM-DD (string, o null si no aparece)",
  "monto_total": <número float SIN separadores de miles — ver regla arriba, o null>,
  "moneda": "ARS o USD",
  "medio_pago": "transferencia | efectivo | tarjeta | null — según lo que muestre la imagen",
  "items": [
    {"descripcion": "...", "monto": 0.0}
  ],
  "notas": "cualquier dato adicional relevante (string, o null)"
}

Reglas:
- Si no tiene fecha visible, usar null.
- Si hay ambigüedad en el total (subtotal vs total con impuestos), usar el total final.
- Si la moneda no está explícita, asumir ARS.
- Para comprobantes de transferencia: comercio = nombre del destinatario, medio_pago = "transferencia".
- Respondé ÚNICAMENTE con el JSON válido, sin explicaciones ni texto adicional.
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
    response = generate_with_fallback(
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
