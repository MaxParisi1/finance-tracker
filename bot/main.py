"""
Entry point del bot de Telegram.
- Si TELEGRAM_WEBHOOK_URL está definida → modo webhook (producción en Railway)
- Si no está definida → modo polling (desarrollo local)
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

from bot.agent import run_agent
from bot.gmail_poller import start_gmail_polling
from bot.tools import recurrentes_matcher as matcher
from bot.tools.media_processor import procesar_audio, audio_a_mensaje
from bot.db.queries import cargar_historial_bot, guardar_historial_bot

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ID de Telegram del único usuario autorizado
ALLOWED_USER_ID = int(os.environ["ALLOWED_TELEGRAM_USER_ID"])

# Historial de conversación: cache en memoria + persistencia en Supabase
# Estructura: { chat_id: [{"role": "user"|"model", "parts": ["..."]}] }
_conversation_history: dict[int, list[dict]] = {}

MAX_HISTORY_TURNS = 20


async def safe_reply(message, text: str) -> None:
    """Intenta enviar con Markdown; si Telegram rechaza, envía como texto plano."""
    try:
        await message.reply_text(text, parse_mode="Markdown")
    except Exception:
        await message.reply_text(text)


def _is_authorized(update: Update) -> bool:
    """Valida que el mensaje provenga del usuario autorizado."""
    return update.effective_user is not None and update.effective_user.id == ALLOWED_USER_ID


def _get_history(chat_id: int) -> list[dict]:
    """Devuelve historial desde cache en memoria; si no existe, carga desde DB."""
    if chat_id not in _conversation_history:
        try:
            _conversation_history[chat_id] = cargar_historial_bot(chat_id)
        except Exception:
            _conversation_history[chat_id] = []
    return _conversation_history[chat_id]


def _add_to_history(chat_id: int, role: str, text: str) -> None:
    if chat_id not in _conversation_history:
        _conversation_history[chat_id] = []
    _conversation_history[chat_id].append({"role": role, "parts": [text]})
    if len(_conversation_history[chat_id]) > MAX_HISTORY_TURNS * 2:
        _conversation_history[chat_id] = _conversation_history[chat_id][-MAX_HISTORY_TURNS * 2:]
    # Persistir en Supabase (best-effort)
    try:
        guardar_historial_bot(chat_id, _conversation_history[chat_id])
    except Exception:
        pass


# ──────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "¡Hola! Soy tu asistente de finanzas personales.\n\n"
        "Podés decirme cosas como:\n"
        "• \"Gasté 15000 pesos en el super con débito\"\n"
        "• \"¿Cuánto gasté en restós este mes?\"\n"
        "• \"¿Cuánto está el dólar blue?\"\n\n"
        "También podés mandarme notas de voz, o el PDF de una factura o comprobante\n"
        "de tus servicios fijos y lo archivo solo."
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "*Comandos disponibles:*\n"
        "/start — Mensaje de bienvenida\n"
        "/help — Esta ayuda\n"
        "/reset — Limpiar historial de conversación\n\n"
        "*Podés enviarme:*\n"
        "• Texto libre describiendo un gasto\n"
        "• Nota de voz\n"
        "• PDF de factura o comprobante de un servicio fijo",
        parse_mode="Markdown",
    )


async def reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    chat_id = update.effective_chat.id
    _conversation_history.pop(chat_id, None)
    await update.message.reply_text("Historial limpiado. Empezamos de cero.")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler principal para mensajes de texto."""
    if not _is_authorized(update):
        return

    user_text = update.message.text
    chat_id = update.effective_chat.id

    # Indicador de "escribiendo..."
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    history = _get_history(chat_id)

    try:
        response = run_agent(user_text, history, chat_id=chat_id)
    except Exception as e:
        logger.exception("Error en el agente")
        response = "Uy, algo salió mal. Intentá de nuevo en un momento."

    _add_to_history(chat_id, "user", user_text)
    _add_to_history(chat_id, "model", response)

    await safe_reply(update.message, response)


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa notas de voz con Gemini Audio."""
    if not _is_authorized(update):
        return

    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Telegram envía voice notes como OGG/OPUS
    voice = update.message.voice or update.message.audio
    file = await context.bot.get_file(voice.file_id)
    audio_bytes = await file.download_as_bytearray()

    mime_type = "audio/ogg" if update.message.voice else "audio/mpeg"

    try:
        datos = procesar_audio(bytes(audio_bytes), mime_type=mime_type)
        mensaje_interno = audio_a_mensaje(datos)
    except Exception:
        logger.exception("Error procesando audio")
        await update.message.reply_text("No pude procesar el audio. Intentá de nuevo o escribí el gasto.")
        return

    history = _get_history(chat_id)
    try:
        response = run_agent(mensaje_interno, history, chat_id=chat_id)
    except Exception:
        logger.exception("Error en el agente (audio)")
        response = "Uy, algo salió mal procesando el audio."

    _add_to_history(chat_id, "user", f"[audio: {datos.get('transcripcion', '...')}]")
    _add_to_history(chat_id, "model", response)

    await safe_reply(update.message, response)


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
    app.add_handler(CommandHandler("reset", reset_handler))
    app.add_handler(CallbackQueryHandler(match_callback_handler, pattern=r"^mr:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))

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
