"""
Tarea en background: consulta Gmail cada 15 minutos buscando emails bancarios.
- Etiqueta "Consumos": emails genéricos (BBVA, Mastercard, etc.) parseados con Gemini.
- Etiqueta "Consumos_visa": notificaciones Prisma/Visa; medio_pago resuelto por sufijo de tarjeta.
"""

import asyncio
import json
import logging
import re

from google.genai import types

from bot.tools.gmail_reader import get_unread_bank_emails, mark_as_read, LABEL_NAME_VISA
from bot.gemini_client import generate_with_fallback
from bot.tools.gastos import guardar_gasto, historial_comercio
from bot.tools.tarjetas import resolver_medio_pago, nombre_tarjeta
from bot.db.queries import obtener_categorias_activas

logger = logging.getLogger(__name__)

POLL_INTERVAL = 900  # 15 minutos

# Patrón para emails de Prisma (Visa).
# Ancla en "$ monto en el establecimiento" para ser agnóstico al tipo
# ("consumo", "débito automático", etc.)
_PRISMA_RE = re.compile(
    r"(?:U\$S|\$)\s*([\d.,]+)\s+en\s+el\s+establecimiento\s+(.+?)\s+,"  # monto + comercio (ARS: "$ X" o USD: "U$S X")
    r".*?el\s+d[ií]a\s+(\d{2}/\d{2}/\d{4})"                             # fecha DD/MM/YYYY
    r".*?finalizada\s+en\s+(\d{4})",                                      # sufijo
    re.IGNORECASE | re.DOTALL,
)

# Palabras que indican que la transacción fue rechazada y no debe registrarse
_PRISMA_DENIED_KEYWORDS = ("denegad", "fallid", "no pudo ser procesad", "fue rechazad")


def _is_prisma_denied(body: str) -> bool:
    lower = body.lower()
    return any(kw in lower for kw in _PRISMA_DENIED_KEYWORDS)


def _parse_monto_argentino(raw: str) -> float:
    """Convierte '14.500,00' → 14500.0"""
    return float(raw.replace(".", "").replace(",", "."))


def _parse_prisma_email(email: dict) -> dict | None:
    """
    Parsea un email de notificación Prisma/Visa con regex.
    Retorna None con reason="denied" si la transacción fue rechazada.
    Retorna None con reason="no_match" si el formato no reconoce.
    Retorna el dict de campos si es una transacción válida.
    """
    body = email.get("body", "")

    if _is_prisma_denied(body):
        logger.info("Email Prisma ignorado (transacción denegada): %s", email.get("subject"))
        return {"_denied": True}

    match = _PRISMA_RE.search(body)
    if not match:
        logger.warning(
            "Email de Consumos_visa no matchó el patrón Prisma: %s | body[:300]: %r",
            email.get("subject"),
            body[:300],
        )
        return None

    monto_raw, comercio, fecha_raw, sufijo = match.groups()
    monto = _parse_monto_argentino(monto_raw)

    dia, mes, anio = fecha_raw.split("/")
    fecha = f"{anio}-{mes}-{dia}"

    moneda = "USD" if "usd" in body.lower() or "u$s" in body.lower() else "ARS"

    return {
        "monto": monto,
        "moneda": moneda,
        "comercio": comercio.strip().title(),
        "fecha": fecha,
        "sufijo": sufijo,
    }


def _parse_email_with_gemini(email: dict) -> dict | None:
    """Usa Gemini para extraer datos de transacción de un email bancario genérico."""
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


def _enriquecer_prisma(parsed: dict) -> dict:
    """
    Enriquece los datos parseados de un email Prisma con campos que requieren inteligencia.
    Primero intenta con el historial local (sin costo). Si el comercio es nuevo, llama a Gemini
    para obtener categoria, descripcion y notas en un único request.
    Devuelve un dict con: categoria, descripcion, notas.
    """
    comercio = parsed["comercio"]

    # Intento 1: historial local (gratis)
    try:
        hist = historial_comercio(comercio)
        if hist.get("encontrado") and hist.get("categoria_mas_frecuente"):
            return {
                "categoria": hist["categoria_mas_frecuente"],
                "descripcion": comercio,
                "notas": None,
            }
    except Exception:
        logger.warning("historial_comercio falló para '%s', continuando con Gemini", comercio)

    # Intento 2: Gemini con contexto completo — aprovechamos el call para todo
    categorias = [c["nombre"] for c in obtener_categorias_activas()]
    categorias_str = ", ".join(categorias) if categorias else "Otros"

    prompt = f"""Analizá este consumo con tarjeta Visa y completá los campos faltantes.

Datos ya conocidos:
- Comercio: {comercio}
- Monto: {parsed['monto']} {parsed['moneda']}
- Fecha: {parsed['fecha']}

Respondé SOLO con un JSON:
{{
  "categoria": "categoría de la lista",
  "descripcion": "descripción clara y concisa del gasto (ej: 'Almuerzo en El Chulenguito')",
  "notas": "dato útil si aplica, o null (ej: 'débito automático', 'peaje', etc.)"
}}

Categorías válidas: {categorias_str}."""

    try:
        response = generate_with_fallback(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        data = json.loads(response.text)
        return {
            "categoria": data.get("categoria", "Otros"),
            "descripcion": data.get("descripcion") or comercio,
            "notas": data.get("notas") or None,
        }
    except Exception:
        logger.warning("Gemini falló al enriquecer email Prisma de %s", comercio)
        return {"categoria": "Otros", "descripcion": comercio, "notas": None}


def _escape_md(text: str) -> str:
    """Escapa caracteres especiales de Markdown de Telegram."""
    text = text.replace("*", " ")
    for ch in ("_", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text.strip()


async def poll_gmail_once(bot, chat_id: int) -> None:
    """Revisa la etiqueta Consumos (emails genéricos) y procesa los nuevos."""
    try:
        emails = await asyncio.to_thread(get_unread_bank_emails)
    except Exception:
        logger.exception("Error al consultar Gmail (Consumos)")
        return

    for email in emails:
        try:
            data = await asyncio.to_thread(_parse_email_with_gemini, email)

            if not data:
                await asyncio.to_thread(mark_as_read, email["id"])
                continue

            await asyncio.to_thread(
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
            comercio_esc = _escape_md(str(data.get("comercio") or data.get("descripcion") or ""))
            msg = (
                f"\U0001f4e7 *Gasto auto-registrado desde email:*\n"
                f"• *{comercio_esc}*\n"
                f"• {moneda_sym}{float(data['monto']):,.2f} · {data.get('medio_pago', '').replace('_', ' ')}\n"
                f"• Categoría: {data.get('categoria')}\n"
                f"• Fecha: {data.get('fecha')}"
            )
            await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

        except Exception:
            logger.exception(f"Error procesando email {email['id']}")


async def poll_visa_once(bot, chat_id: int) -> None:
    """Revisa la etiqueta Consumos_visa (notificaciones Prisma) y procesa los nuevos."""
    try:
        emails = await asyncio.to_thread(get_unread_bank_emails, LABEL_NAME_VISA)
    except Exception:
        logger.exception("Error al consultar Gmail (Consumos_visa)")
        return

    for email in emails:
        try:
            parsed = await asyncio.to_thread(_parse_prisma_email, email)

            if parsed is None:
                # Formato desconocido: notificar y NO marcar como leído para revisión manual
                subject = _escape_md(email.get("subject", "(sin asunto)"))
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⚠️ *Email Visa sin parsear*\n"
                        f"No reconocí el formato de un email en Consumos\\_visa.\n"
                        f"• Asunto: {subject}\n"
                        f"Revisalo manualmente en Gmail."
                    ),
                    parse_mode="Markdown",
                )
                continue

            if parsed.get("_denied"):
                # Transacción denegada: marcar como leído y seguir
                await asyncio.to_thread(mark_as_read, email["id"])
                continue

            sufijo = parsed["sufijo"]
            moneda = parsed["moneda"]

            medio_pago, tarjeta_row = await asyncio.to_thread(resolver_medio_pago, sufijo, moneda)
            tarjeta_nombre = nombre_tarjeta(tarjeta_row)

            enriquecido = await asyncio.to_thread(_enriquecer_prisma, parsed)

            await asyncio.to_thread(
                guardar_gasto,
                descripcion=enriquecido["descripcion"],
                monto=parsed["monto"],
                moneda=moneda,
                categoria=enriquecido["categoria"],
                medio_pago=medio_pago,
                fecha=parsed["fecha"],
                comercio=parsed["comercio"],
                notas=enriquecido["notas"],
                fuente="gmail_visa",
                tarjeta=tarjeta_nombre,
            )

            await asyncio.to_thread(mark_as_read, email["id"])

            pendiente = tarjeta_row.get("pendiente_clasificacion", False)
            moneda_sym = "USD " if moneda == "USD" else "$"
            comercio_esc = _escape_md(parsed["comercio"])
            msg = (
                f"\U0001f4e7 *Gasto Visa auto-registrado:*\n"
                f"• *{comercio_esc}*\n"
                f"• {moneda_sym}{parsed['monto']:,.2f} · {medio_pago.replace('_', ' ')}\n"
                f"• Tarjeta: {_escape_md(tarjeta_nombre)}\n"
                f"• Categoría: {enriquecido['categoria']}\n"
                f"• Fecha: {parsed['fecha']}"
            )
            if pendiente:
                msg += f"\n⚠️ Tarjeta {sufijo} sin clasificar (se usó crédito por default)"
            await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

        except Exception:
            logger.exception(f"Error procesando email Visa {email['id']}")


async def start_gmail_polling(bot, chat_id: int) -> None:
    """Arranca los dos loops de polling en paralelo."""
    logger.info("Gmail pollers iniciados (intervalo: %ds)", POLL_INTERVAL)
    await asyncio.gather(
        _loop_poll(bot, chat_id, poll_gmail_once),
        _loop_poll(bot, chat_id, poll_visa_once),
    )


async def _loop_poll(bot, chat_id: int, poll_fn) -> None:
    while True:
        await poll_fn(bot, chat_id)
        await asyncio.sleep(POLL_INTERVAL)
