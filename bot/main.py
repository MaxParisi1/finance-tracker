"""
Entry point del bot de Telegram.
- Si TELEGRAM_WEBHOOK_URL está definida → modo webhook (requiere URL pública)
- Si no está definida → modo polling (es como corre hoy en el VPS y en local)

Este proceso es sobre todo el host de los pollers de Gmail y del loop de
recordatorios (ver start_gmail_polling): tiene que estar corriendo siempre,
aunque nadie le escriba.

Por Telegram el bot es un canal de salida (notificaciones y alertas) más tres
entradas puntuales: los botones de confirmación de recurrentes, el archivado de
facturas en PDF y los comandos. El agente conversacional se eliminó — no se
usaba y era la última atadura a la API de Gemini. Si alguna vez hace falta,
está en el historial: `git show 944b1f3:bot/agent.py`.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from bot.gmail_poller import start_gmail_polling
from bot.tools import recurrentes_matcher as matcher

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ID de Telegram del único usuario autorizado
ALLOWED_USER_ID = int(os.environ["ALLOWED_TELEGRAM_USER_ID"])

def _is_authorized(update: Update) -> bool:
    """Valida que el mensaje provenga del usuario autorizado."""
    return update.effective_user is not None and update.effective_user.id == ALLOWED_USER_ID


# ──────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "¡Hola! Registro tus gastos solo, leyendo los emails del banco.\n\n"
        "Acá te aviso cuando registro uno, cuando algo falla, y te pregunto "
        "si un gasto corresponde a un recurrente.\n\n"
        "Lo único que podés mandarme: el PDF o la foto de una factura o "
        "comprobante de tus servicios fijos, y lo archivo en Drive.\n\n"
        "Para consultar tus gastos, entrá al dashboard web."
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "*Comandos:*\n"
        "/start — Qué hago\n"
        "/help — Esta ayuda\n\n"
        "*Podés enviarme:*\n"
        "• PDF o foto de una factura o comprobante de un servicio fijo\n\n"
        "*Lo que hago solo:*\n"
        "• Registro los gastos que llegan por email del banco\n"
        "• Te aviso si un gasto puede ser un recurrente\n"
        "• Te alerto si un email no se pudo procesar\n\n"
        "Para cargar un gasto a mano o ver reportes, usá el dashboard web.",
        parse_mode="Markdown",
    )


async def sin_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Atiende texto libre y notas de voz, que antes iban al agente conversacional.

    Existe sólo para no quedarse mudo: un bot que ignora lo que le escribís se
    lee como "está roto". Prefiere decir qué sí puede hacer.
    """
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "Ya no entiendo texto libre ni notas de voz: el chat se eliminó porque no se usaba.\n\n"
        "Podés mandarme el PDF o la foto de una factura de un servicio fijo y la archivo.\n"
        "Para todo lo demás, el dashboard web.",
    )


async def _archivar_documento_servicio(
    update: Update, file_bytes: bytes, mime_type: str
) -> None:
    """
    Identifica el documento por el número de cuenta que lleva adentro, lo
    concilia contra la factura abierta y lo archiva en Drive.

    Todo determinístico: si no reconoce el documento no adivina ni escala a un
    modelo, avisa y no hace nada.
    """
    import asyncio

    from bot.tools.archivado import archivar_documento
    from bot.tools.conciliacion import ConciliacionAmbigua
    from bot.tools.documentos import DocumentoNoIdentificado, identificar_documento
    from bot.tools.montos import formatear_monto_ar

    try:
        doc_ident = await asyncio.to_thread(identificar_documento, file_bytes)
    except DocumentoNoIdentificado as e:
        await update.message.reply_text(
            f"No reconocí este documento: {e}\n\n"
            f"Solo proceso facturas y comprobantes de tus servicios fijos "
            f"(los identifico por el número de cuenta que traen adentro).",
        )
        return
    except Exception:
        logger.exception("Error identificando el documento")
        await update.message.reply_text("No pude leer el archivo. Probá de nuevo.")
        return

    try:
        resultado = await asyncio.to_thread(
            archivar_documento, doc_ident, file_bytes, mime_type
        )
    except ConciliacionAmbigua as e:
        await update.message.reply_text(
            f"Es un documento de *{doc_ident.servicio['nombre']}*, pero no supe a qué "
            f"factura corresponde: {e}\nNo archivé nada.",
            parse_mode="Markdown",
        )
        return
    except Exception:
        logger.exception("Error archivando documento de servicio fijo")
        await update.message.reply_text(
            "Reconocí el documento pero falló el archivado. No quedó guardado; probá de nuevo."
        )
        return

    lineas = [
        f"📎 *{resultado.tipo.capitalize()} archivada*" if resultado.tipo == "factura"
        else "📎 *Comprobante archivado*",
        f"• *{resultado.servicio}*",
    ]
    if resultado.factura:
        lineas.append(f"• ${formatear_monto_ar(float(resultado.factura['monto']))}")
        lineas.append(f"• Vence: {resultado.factura['vencimiento']}")
    if resultado.gasto:
        lineas.append("• Gasto registrado y factura saldada ✅")
    lineas.append(f"• Drive: {resultado.archivo.get('drive_folder_path', '')}")
    if resultado.aviso:
        lineas.append(f"⚠️ {resultado.aviso}")

    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Procesa documentos de los servicios fijos, de forma 100% determinística.

    Un PDF se identifica por el número de cuenta que lleva adentro, se concilia
    contra la factura abierta y se archiva en Drive. Sin LLM y sin preguntas.
    Lo que no se reconoce se rechaza con un mensaje claro: preferimos no hacer
    nada antes que archivar algo en el lugar equivocado.
    """
    if not _is_authorized(update):
        return

    doc = update.message.document
    chat_id = update.effective_chat.id
    mime_type = doc.mime_type or ""

    aceptados = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
    if mime_type not in aceptados:
        await update.message.reply_text(
            "Puedo procesar PDFs e imágenes de facturas y comprobantes de tus servicios fijos."
        )
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")

    file = await context.bot.get_file(doc.file_id)
    file_bytes = await file.download_as_bytearray()

    await _archivar_documento_servicio(update, bytes(file_bytes), mime_type)


# ──────────────────────────────────────────────
# Callbacks de recurrentes
# ──────────────────────────────────────────────

async def match_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    texto = await matcher.procesar_callback(query)
    await query.edit_message_text(text=texto, parse_mode="Markdown")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

import asyncio


async def _run() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    webhook_url = os.environ.get("TELEGRAM_WEBHOOK_URL")

    app = Application.builder().token(token).build()

    # Registrar handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CallbackQueryHandler(match_callback_handler, pattern=r"^mr:"))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    # Lo único que el bot procesa de entrada son documentos y los botones de
    # recurrentes. El resto contesta qué sí puede hacer, en vez de ignorarlo.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, sin_chat_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, sin_chat_handler))

    if webhook_url:
        logger.info(f"Iniciando en modo webhook: {webhook_url}")
        async with app:
            await app.start()
            await app.updater.start_webhook(
                listen="0.0.0.0",
                port=int(os.environ.get("PORT", 8080)),
                webhook_url=webhook_url,
                url_path=token,
            )
            if os.environ.get("GMAIL_REFRESH_TOKEN"):
                asyncio.create_task(start_gmail_polling(app.bot, ALLOWED_USER_ID))
            await asyncio.Event().wait()
            await app.updater.stop()
            await app.stop()
    else:
        logger.info("Iniciando en modo polling (desarrollo local)")
        async with app:
            await app.start()
            await app.updater.start_polling()
            if os.environ.get("GMAIL_REFRESH_TOKEN"):
                asyncio.create_task(start_gmail_polling(app.bot, ALLOWED_USER_ID))
            await asyncio.Event().wait()
            await app.updater.stop()
            await app.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
