"""
Tarea en background: consulta Gmail cada 5 minutos buscando emails bancarios.
Parsea la transacción con Gemini y la guarda en Supabase automáticamente.
"""

import asyncio
import json
import logging
import os

from google.genai import types

from bot.tools.gmail_reader import get_unread_bank_emails, mark_as_read
from bot.gemini_client import generate_with_fallback
from bot.tools.gastos import guardar_gasto
from bot.db.queries import obtener_categorias_activas

logger = logging.getLogger(__name__)

POLL_INTERVAL = 900  # 15 minutos


def _parse_email_with_gemini(email: dict) -> dict | None:
    """Usa Gemini para extraer datos de transacción de un email bancario."""
    categorias = [c["nombre"] for c in obtener_categorias_activas()]
    categorias_str = ", ".join(categorias) if categorias else "otros"

    prompt = f"""Analizá este email de banco y extraé los datos de la transacción.
Respondé SOLO con un JSON válido con estos campos (o {{"es_transaccion": false}} si no es un email de transacción):

{{
  "es_transaccion": true,
  "descripcion": "descripción del pago",
  "monto": 1234.56,
  "moneda": "ARS",
  "fecha": "YYYY-MM-DD",
  "comercio": "nombre del comercio",
  "medio_pago": "credito_ars",
  "categoria": "categoría estimada",
  "tarjeta": "BBVA Mastercard 3327"
}}

Valores válidos para medio_pago: credito_ars, credito_usd, debito, efectivo_ars, efectivo_usd, transferencia.
Valores válidos para categoria (elegí la más apropiada): {categorias_str}.
Si el monto es 0, igual registralo (puede ser una pre-autorización o pago sin cargo).
Para moneda: si el email dice "USD" usá "USD", sino "ARS".
Para tarjeta: extraé la red (Visa/Mastercard/etc) y los últimos 4 dígitos si están en el email, ej: "BBVA Mastercard 3327".

Email:
De: {email['from']}
Asunto: {email['subject']}
Fecha: {email['date']}
Cuerpo:
{email['body'][:2000]}
"""

    response = generate_with_fallback(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )

    try:
        data = json.loads(response.text)
        if not data.get("es_transaccion"):
            return None
        return data
    except Exception:
        logger.warning(f"No se pudo parsear respuesta de Gemini: {response.text[:200]}")
        return None


async def poll_gmail_once(bot, chat_id: int) -> None:
    """Revisa Gmail una vez y procesa los emails nuevos."""
    try:
        emails = await asyncio.to_thread(get_unread_bank_emails)
    except Exception:
        logger.exception("Error al consultar Gmail")
        return

    for email in emails:
        try:
            data = await asyncio.to_thread(_parse_email_with_gemini, email)

            if not data:
                await asyncio.to_thread(mark_as_read, email["id"])
                continue

            resultado = await asyncio.to_thread(
                guardar_gasto,
                descripcion=data.get("descripcion", "Pago con tarjeta"),
                monto=float(data["monto"]),
                moneda=data.get("moneda", "ARS"),
                categoria=data.get("categoria", "otros"),
                medio_pago=data.get("medio_pago", "credito_ars"),
                fecha=data.get("fecha"),
                comercio=data.get("comercio"),
                fuente="gmail_auto",
                tarjeta=data.get("tarjeta"),
            )

            await asyncio.to_thread(mark_as_read, email["id"])

            moneda_sym = "USD " if data.get("moneda") == "USD" else "$"
            msg = (
                f"\U0001f4e7 *Gasto auto-registrado desde email:*\n"
                f"\u2022 *{data.get('comercio') or data.get('descripcion')}*\n"
                f"\u2022 {moneda_sym}{float(data['monto']):,.2f} \u00b7 {data.get('medio_pago', '').replace('_', ' ')}\n"
                f"\u2022 Categoría: {data.get('categoria')}\n"
                f"\u2022 Fecha: {data.get('fecha')}"
            )
            await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

        except Exception:
            logger.exception(f"Error procesando email {email['id']}")


async def start_gmail_polling(bot, chat_id: int) -> None:
    """Loop eterno de polling de Gmail."""
    logger.info("Gmail poller iniciado (intervalo: 5 minutos)")
    while True:
        await poll_gmail_once(bot, chat_id)
        await asyncio.sleep(POLL_INTERVAL)
