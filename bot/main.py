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
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from bot.agent import run_agent, set_pdf_pendiente
from bot.gmail_poller import start_gmail_polling
from bot.tools.media_processor import (
    procesar_imagen_ticket,
    procesar_audio,
    ticket_a_mensaje,
    audio_a_mensaje,
)
from bot.tools.bbva_parser import importar_pdf_bbva
from bot.db.queries import obtener_gastos, cargar_historial_bot, guardar_historial_bot

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
        "También podés mandarme fotos de tickets o notas de voz."
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
        "• Foto de un ticket o factura\n"
        "• Nota de voz\n"
        "• PDF de resumen BBVA",
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


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa fotos de tickets con Gemini Vision."""
    if not _is_authorized(update):
        return

    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Descargar la foto en máxima resolución
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    img_bytes = await file.download_as_bytearray()

    try:
        datos = procesar_imagen_ticket(bytes(img_bytes))
        mensaje_interno = ticket_a_mensaje(datos)
    except Exception as e:
        logger.exception("Error procesando imagen")
        await update.message.reply_text("No pude procesar la imagen. Intentá de nuevo o describí el gasto en texto.")
        return

    history = _get_history(chat_id)
    try:
        response = run_agent(mensaje_interno, history, chat_id=chat_id)
    except Exception:
        logger.exception("Error en el agente (foto)")
        response = "Uy, algo salió mal procesando la foto."

    _add_to_history(chat_id, "user", "[foto de ticket]")
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


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa PDFs del resumen BBVA."""
    if not _is_authorized(update):
        return

    doc = update.message.document
    chat_id = update.effective_chat.id

    # Solo aceptar PDFs
    if doc.mime_type != "application/pdf":
        await update.message.reply_text("Solo proceso archivos PDF (resúmenes BBVA). Para otros archivos, describí el gasto en texto.")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")
    await update.message.reply_text("Recibí el PDF, lo estoy procesando... un momento.")

    file = await context.bot.get_file(doc.file_id)
    pdf_bytes = await file.download_as_bytearray()

    try:
        # Traer gastos recientes para detección de duplicados (últimos 90 días)
        from datetime import date, timedelta
        fecha_desde = (date.today() - timedelta(days=90)).isoformat()
        gastos_existentes = obtener_gastos({"fecha_desde": fecha_desde})

        resultado = importar_pdf_bbva(bytes(pdf_bytes), gastos_existentes)
        set_pdf_pendiente(chat_id, resultado, bytes(pdf_bytes))

    except Exception:
        logger.exception("Error procesando PDF BBVA")
        await update.message.reply_text("No pude procesar el PDF. ¿Es un resumen BBVA? Intentá de nuevo.")
        return

    # Construir mensaje interno para el agente con el resumen
    nuevos = resultado["total_nuevos"]
    duplicados = resultado["total_duplicados"]
    fecha_desde_pdf = resultado.get("fecha_desde") or "?"
    fecha_hasta_pdf = resultado.get("fecha_hasta") or "?"
    metodo = resultado.get("metodo_usado", "texto")

    muestra = resultado["movimientos_nuevos"][:5]
    muestra_txt = "\n".join(
        f"  • {m.get('fecha', '?')} | {m.get('descripcion', '?')} | ${m.get('monto', 0):,.2f} {m.get('moneda', 'ARS')}"
        for m in muestra
    )

    mensaje_interno = (
        f"El usuario mandó un PDF de resumen BBVA. Ya fue procesado (método: {metodo}).\n"
        f"Encontré {nuevos + duplicados} movimientos entre {fecha_desde_pdf} y {fecha_hasta_pdf}.\n"
        f"Nuevos para importar: {nuevos}. Duplicados detectados (se omitirán): {duplicados}.\n\n"
        f"Primeros movimientos nuevos:\n{muestra_txt}\n\n"
        f"Mostrá este resumen al usuario y pedí confirmación explícita para importar. "
        f"Si confirma, llamá a confirmar_importacion_pdf_bbva."
    )

    history = _get_history(chat_id)
    try:
        response = run_agent(mensaje_interno, history, chat_id=chat_id)
    except Exception:
        logger.exception("Error en el agente (PDF)")
        response = "Uy, algo salió mal mostrando el resumen del PDF."

    _add_to_history(chat_id, "user", "[PDF resumen BBVA]")
    _add_to_history(chat_id, "model", response)

    await safe_reply(update.message, response)


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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
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
