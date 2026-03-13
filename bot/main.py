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

from bot.agent import run_agent

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ID de Telegram del único usuario autorizado
ALLOWED_USER_ID = int(os.environ["ALLOWED_TELEGRAM_USER_ID"])

# Historial de conversación en memoria (por chat_id)
# Estructura: { chat_id: [{"role": "user"|"model", "parts": ["..."]}] }
_conversation_history: dict[int, list[dict]] = {}

MAX_HISTORY_TURNS = 20  # Máximo de turnos a mantener en memoria


def _is_authorized(update: Update) -> bool:
    """Valida que el mensaje provenga del usuario autorizado."""
    return update.effective_user is not None and update.effective_user.id == ALLOWED_USER_ID


def _get_history(chat_id: int) -> list[dict]:
    return _conversation_history.get(chat_id, [])


def _add_to_history(chat_id: int, role: str, text: str) -> None:
    if chat_id not in _conversation_history:
        _conversation_history[chat_id] = []
    _conversation_history[chat_id].append({"role": role, "parts": [text]})
    # Recortar historial para no crecer infinitamente (conservar los últimos N turnos)
    if len(_conversation_history[chat_id]) > MAX_HISTORY_TURNS * 2:
        _conversation_history[chat_id] = _conversation_history[chat_id][-MAX_HISTORY_TURNS * 2:]


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
        response = run_agent(user_text, history)
    except Exception as e:
        logger.exception("Error en el agente")
        response = "Uy, algo salió mal. Intentá de nuevo en un momento."

    # Actualizar historial
    _add_to_history(chat_id, "user", user_text)
    _add_to_history(chat_id, "model", response)

    await update.message.reply_text(response, parse_mode="Markdown")


async def unknown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para tipos de mensaje no soportados aún (foto, audio, documento)."""
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "Ese tipo de mensaje todavía no está soportado, pero pronto va a estarlo. "
        "Por ahora mandame texto."
    )


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
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.AUDIO | filters.VOICE | filters.Document.ALL,
        unknown_handler,
    ))

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
            await asyncio.Event().wait()
            await app.updater.stop()
            await app.stop()
    else:
        logger.info("Iniciando en modo polling (desarrollo local)")
        async with app:
            await app.start()
            await app.updater.start_polling()
            await asyncio.Event().wait()
            await app.updater.stop()
            await app.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
