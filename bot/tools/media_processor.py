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
    response = generate_with_fallback(
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

def ticket_a_mensaje(datos: dict) -> str:
    """
    Convierte el resultado de procesar_imagen_ticket en un mensaje de texto
    para pasarle al agente como si fuera input del usuario.
    """
    if "error" in datos:
        return f"El usuario mandó una foto de ticket pero no pude extraer los datos: {datos['error']}"

    tipo = datos.get("tipo", "ticket")
    partes = [f"El usuario mandó una foto de {tipo}. Datos extraídos:"]
    if datos.get("comercio"):
        partes.append(f"- Comercio/Destinatario: {datos['comercio']}")
    if datos.get("monto_total") is not None:
        partes.append(f"- Monto total: {datos['monto_total']} {datos.get('moneda', 'ARS')}")
    if datos.get("fecha"):
        partes.append(f"- Fecha: {datos['fecha']}")
    if datos.get("medio_pago"):
        partes.append(f"- Medio de pago: {datos['medio_pago']}")
    if datos.get("notas"):
        partes.append(f"- Notas: {datos['notas']}")

    partes.append("\nUsá estos datos para proponer el gasto al usuario siguiendo el flujo normal de confirmación.")
    return "\n".join(partes)


# ──────────────────────────────────────────────
# Análisis de comprobantes/facturas para Drive
# ──────────────────────────────────────────────

_PROMPT_COMPROBANTE = """
Sos un asistente que analiza comprobantes y facturas argentinas.

Analizá esta imagen/PDF y extraé la siguiente información en formato JSON:

{
  "tipo": "factura" | "comprobante" | "ticket" | "recibo" | "resumen",
  "comercio": "nombre del emisor o comercio",
  "fecha": "YYYY-MM-DD",
  "monto": número (si está visible, o null),
  "moneda": "ARS" | "USD" | null,
  "categoria_sugerida": "Servicios" | "Salud" | "Impuestos" | "Otros",
  "descripcion": "breve descripción de qué es (ej: 'Factura de luz', 'Cuota obra social')"
}

Reglas:
- Para "tipo": si dice "FACTURA" es factura, si dice "COMPROBANTE DE PAGO" es comprobante, si es un ticket de compra es ticket.
- Para "comercio": normalizar el nombre legible (ej: "EDENOR S.A." → "Edenor", "O.S.D.E." → "OSDE", "Agua y Saneamientos Argentinos" → "AySA").
- Para "categoria_sugerida": Servicios para luz/gas/internet/expensas/teléfono/agua, Salud para médicos/obras sociales/farmacias, Impuestos para AFIP/monotributo/impuestos, Otros para el resto.
- IMPORTANTE — Formato numérico argentino: punto (.) es miles, coma (,) es decimal. $10.600 = 10600, $1.250,50 = 1250.50. Siempre convertí a float sin separadores de miles.
- Si no podés extraer algún campo, usá null.
- FECHA: Para facturas de servicios (luz, gas, agua, internet, teléfono, expensas), usá la fecha de VENCIMIENTO (1er vencimiento), ya que indica el período al que corresponde. Para tickets de compra o comprobantes de pago, usá la fecha de emisión.

Respondé SOLO con el JSON, sin texto adicional.
"""


def analizar_comprobante(archivo_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Analiza un comprobante/factura con Gemini Vision para extraer datos estructurados.
    Se usa tanto para fotos como para PDFs de comprobantes.
    """
    response = generate_with_fallback(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=archivo_bytes, mime_type=mime_type),
            types.Part(text=_PROMPT_COMPROBANTE),
        ],
    )

    try:
        data = json.loads(_limpiar_json(response.text))
    except json.JSONDecodeError:
        logger.warning(f"Gemini Vision devolvió JSON inválido para comprobante: {response.text[:300]}")
        data = {"error": "No pude extraer datos estructurados del comprobante."}

    return data


def comprobante_a_mensaje(datos: dict) -> str:
    """
    Convierte el resultado de analizar_comprobante en un mensaje interno para el agente.
    """
    if "error" in datos:
        return (
            f"El usuario mandó un comprobante/factura pero no pude extraer los datos: {datos['error']}. "
            "Pedile al usuario que confirme manualmente: comercio, fecha y tipo de documento."
        )

    partes = ["El usuario mandó un comprobante/factura para subir a Drive. Datos extraídos:"]
    if datos.get("tipo"):
        partes.append(f"- Tipo: {datos['tipo']}")
    if datos.get("comercio"):
        partes.append(f"- Comercio/Emisor: {datos['comercio']}")
    if datos.get("fecha"):
        partes.append(f"- Fecha: {datos['fecha']}")
    if datos.get("monto") is not None:
        partes.append(f"- Monto: {datos['monto']} {datos.get('moneda') or 'ARS'}")
    if datos.get("categoria_sugerida"):
        partes.append(f"- Categoría sugerida: {datos['categoria_sugerida']}")
    if datos.get("descripcion"):
        partes.append(f"- Descripción: {datos['descripcion']}")

    partes.append(
        "\nEl archivo está listo para subir. Mostrá el resumen al usuario y preguntá si quiere "
        "subirlo a Drive (y opcionalmente guardar el gasto también). "
        "Si confirma la subida, llamá a subir_comprobante_a_drive con los datos."
    )
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
