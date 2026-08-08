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
from bot.tools.montos import parse_monto_ar
from bot.tools.tarjetas import resolver_medio_pago, nombre_tarjeta
from bot.db.queries import obtener_categorias_activas, existe_gasto_con_email
from bot.tools import recurrentes_matcher as matcher

logger = logging.getLogger(__name__)

POLL_INTERVAL = 900  # 15 minutos

# Ciclos consecutivos fallidos (fetch de Gmail) antes de auto-alertar por Telegram.
ALERT_THRESHOLD = 3  # ~45 min de caída sostenida

# Emails ya notificados como "no procesados" en este proceso, para no spamear
# la misma alerta cada 15 minutos mientras el email siga sin leer.
_emails_alertados: set[str] = set()

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
    """Convierte '14.500,00' → 14500.0. Delega en el parser compartido."""
    return parse_monto_ar(raw)


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
    """
    Usa Gemini para extraer datos de transacción de un email bancario genérico.

    Devuelve None si el email legítimamente no es una transacción.
    Lanza excepción ante un fallo transitorio (cuota/red/JSON inválido): el caller
    debe dejar el email sin leer para reintentarlo y avisar al usuario.
    """
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

    # Un JSON inválido es un fallo transitorio: propagamos para reintentar y avisar,
    # en vez de descartar silenciosamente un gasto real.
    data = json.loads(response.text)
    if not data.get("es_transaccion"):
        return None
    return data


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


async def _intentar_match_recurrente(bot, chat_id: int, gasto: dict) -> None:
    """Post-save: intenta vincular el gasto guardado a un recurrente activo."""
    try:
        candidato = await asyncio.to_thread(matcher.encontrar_candidato_db, gasto)
        if candidato is None:
            return
        comercio = gasto.get("comercio") or gasto.get("descripcion") or ""
        if candidato.metodo in ("alias", "fuzzy", "gemini"):
            await asyncio.to_thread(
                matcher.confirmar_vinculacion,
                gasto["id"], candidato.recurrente, comercio,
                guardar_alias=(candidato.metodo != "alias"),
                nuevo_monto=gasto.get("monto_original"),
                fecha_pago=gasto.get("fecha"),
            )
            rec_esc = _escape_md(candidato.recurrente["descripcion"])
            com_esc = _escape_md(comercio)
            await bot.send_message(
                chat_id=chat_id,
                text=f"🔗 *Recurrente vinculado:* {com_esc} → _{rec_esc}_",
                parse_mode="Markdown",
            )
        else:
            await matcher.solicitar_confirmacion_telegram(bot, chat_id, gasto, candidato)
    except Exception:
        logger.exception("Error al intentar match recurrente para gasto %s", gasto.get("id"))


def _escape_md(text: str) -> str:
    """Escapa caracteres especiales de Markdown de Telegram."""
    text = text.replace("*", " ")
    for ch in ("_", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text.strip()


async def _alertar_email_no_procesado(bot, chat_id: int, email: dict) -> None:
    """Avisa (una sola vez por email) que un email quedó sin procesar por un fallo transitorio."""
    eid = email["id"]
    if eid in _emails_alertados:
        return
    _emails_alertados.add(eid)
    subject = _escape_md(email.get("subject", "(sin asunto)"))
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ *Email sin procesar*\n"
                f"No pude extraer la transacción (error temporal de IA).\n"
                f"• Asunto: {subject}\n"
                f"Quedó sin leer para reintentar en el próximo ciclo."
            ),
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("No pude enviar alerta de email no procesado")


async def poll_gmail_once(bot, chat_id: int) -> bool:
    """
    Revisa la etiqueta Consumos (emails genéricos) y procesa los nuevos.
    Devuelve False si falló el fetch a Gmail (señal de salud del poller).
    """
    try:
        emails = await asyncio.to_thread(get_unread_bank_emails)
    except Exception:
        logger.exception("Error al consultar Gmail (Consumos)")
        return False

    for email in emails:
        try:
            # Idempotencia: si este email ya generó un gasto, solo marcar leído.
            if await asyncio.to_thread(existe_gasto_con_email, email["id"]):
                logger.info("Email %s ya importado; se omite (idempotencia)", email["id"])
                await asyncio.to_thread(mark_as_read, email["id"])
                continue

            try:
                data = await asyncio.to_thread(_parse_email_with_gemini, email)
            except Exception:
                logger.exception("Fallo transitorio parseando email %s (no se marca leído)", email["id"])
                await _alertar_email_no_procesado(bot, chat_id, email)
                continue

            if not data:
                await asyncio.to_thread(mark_as_read, email["id"])
                continue

            gasto_guardado = await asyncio.to_thread(
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
                email_message_id=email["id"],
            )

            await _intentar_match_recurrente(bot, chat_id, gasto_guardado)
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

    return True


async def poll_visa_once(bot, chat_id: int) -> bool:
    """
    Revisa la etiqueta Consumos_visa (notificaciones Prisma) y procesa los nuevos.
    Devuelve False si falló el fetch a Gmail (señal de salud del poller).
    """
    try:
        emails = await asyncio.to_thread(get_unread_bank_emails, LABEL_NAME_VISA)
    except Exception:
        logger.exception("Error al consultar Gmail (Consumos_visa)")
        return False

    for email in emails:
        try:
            # Idempotencia: si este email ya generó un gasto, solo marcar leído.
            if await asyncio.to_thread(existe_gasto_con_email, email["id"]):
                logger.info("Email Visa %s ya importado; se omite (idempotencia)", email["id"])
                await asyncio.to_thread(mark_as_read, email["id"])
                continue

            parsed = await asyncio.to_thread(_parse_prisma_email, email)

            if parsed is None:
                # Formato desconocido: notificar (una sola vez) y NO marcar como leído
                # para revisión manual.
                if email["id"] not in _emails_alertados:
                    _emails_alertados.add(email["id"])
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

            gasto_guardado = await asyncio.to_thread(
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
                email_message_id=email["id"],
            )

            await _intentar_match_recurrente(bot, chat_id, gasto_guardado)
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

    return True


async def start_gmail_polling(bot, chat_id: int) -> None:
    """Arranca los loops de polling en paralelo."""
    from bot.facturas_poller import LABEL_NAME_FACTURAS, poll_facturas_once
    from bot.tools.recordatorios import loop_recordatorios

    logger.info("Gmail pollers iniciados (intervalo: %ds)", POLL_INTERVAL)
    await asyncio.gather(
        _loop_poll(bot, chat_id, poll_gmail_once, "Consumos"),
        _loop_poll(bot, chat_id, poll_visa_once, "Consumos_visa"),
        _loop_poll(bot, chat_id, poll_facturas_once, LABEL_NAME_FACTURAS),
        loop_recordatorios(bot, chat_id),
    )


async def _safe_alert(bot, chat_id: int, texto: str) -> None:
    """Envía una alerta de estado sin dejar que un fallo de red tumbe el loop."""
    try:
        await bot.send_message(chat_id=chat_id, text=texto, parse_mode="Markdown")
    except Exception:
        logger.exception("No pude enviar alerta de estado del poller")


async def _loop_poll(bot, chat_id: int, poll_fn, nombre: str) -> None:
    """
    Corre poll_fn en loop. Cuenta ciclos consecutivos fallidos y auto-alerta por
    Telegram al superar ALERT_THRESHOLD (dead-man's switch), avisando también al recuperar.
    """
    fallos = 0
    alertado = False
    while True:
        try:
            ok = await poll_fn(bot, chat_id)
        except Exception:
            logger.exception("Error inesperado en poller %s", nombre)
            ok = False

        if ok:
            if alertado:
                await _safe_alert(bot, chat_id, f"✅ Poller *{nombre}* recuperado.")
                alertado = False
            fallos = 0
        else:
            fallos += 1
            if fallos >= ALERT_THRESHOLD and not alertado:
                minutos = fallos * POLL_INTERVAL // 60
                await _safe_alert(
                    bot, chat_id,
                    f"⚠️ Poller *{nombre}* falló {fallos} ciclos seguidos (~{minutos} min).\n"
                    f"Revisá el token de Gmail, la cuota de Gemini o los logs del servidor.",
                )
                alertado = True

        await asyncio.sleep(POLL_INTERVAL)
