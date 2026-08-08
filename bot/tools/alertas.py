"""
Avisos de error por Telegram.

Regla de oro: fallar es aceptable, fallar en silencio no. Cuando un proveedor
cambia el formato de su mail, el parser tiene que romper y avisar con el detalle
suficiente para escribir el fix — no adivinar un número ni tragarse el error.

Dos garantías:
  - Alertar nunca puede tumbar al bot: si Telegram falla, se loguea y sigue.
  - No se spamea: la misma falla no se repite hasta que pase VENTANA_REPETICION.
"""

import logging
import time
import traceback

logger = logging.getLogger(__name__)

__all__ = ["alertar_error", "escapar_md", "resetear_dedup"]

# Cuánto esperar antes de volver a avisar la misma falla. El poller corre cada
# 15 min; sin esto un mail roto generaría 96 mensajes por día.
VENTANA_REPETICION = 6 * 60 * 60  # 6 horas

# clave de falla → timestamp del último aviso
_ultimo_aviso: dict[str, float] = {}

_LIMITE_DETALLE = 400


def escapar_md(texto: str) -> str:
    """Neutraliza el Markdown de Telegram para que un mensaje de error no rompa el envío."""
    texto = (texto or "").replace("*", " ")
    for ch in ("_", "`", "["):
        texto = texto.replace(ch, f"\\{ch}")
    return texto.strip()


def resetear_dedup() -> None:
    """Limpia la memoria de deduplicación (para tests y para reintentos manuales)."""
    _ultimo_aviso.clear()


def _debe_avisar(clave: str, ahora: float) -> bool:
    previo = _ultimo_aviso.get(clave)
    if previo is not None and (ahora - previo) < VENTANA_REPETICION:
        return False
    _ultimo_aviso[clave] = ahora
    return True


def formatear_error(titulo: str, contexto: dict, exc: BaseException | None) -> str:
    """Arma el mensaje. Separado del envío para poder testearlo sin un bot real."""
    lineas = [f"⚠️ *{escapar_md(titulo)}*"]

    for etiqueta, valor in contexto.items():
        if valor is None:
            continue
        lineas.append(f"• {escapar_md(str(etiqueta))}: {escapar_md(str(valor))}")

    if exc is not None:
        detalle = f"{type(exc).__name__}: {exc}"
        if len(detalle) > _LIMITE_DETALLE:
            detalle = detalle[:_LIMITE_DETALLE] + "…"
        lineas.append(f"• Error: {escapar_md(detalle)}")

    lineas.append("_Nada se guardó. Revisá y reintentá cuando esté el fix._")
    return "\n".join(lineas)


async def alertar_error(
    bot,
    chat_id: int,
    *,
    titulo: str,
    contexto: dict | None = None,
    exc: BaseException | None = None,
    clave: str | None = None,
) -> bool:
    """
    Manda un aviso de error por Telegram.

    `clave` identifica la falla para deduplicar; si no se pasa, se deriva del
    título y del tipo de excepción. Devuelve True si el mensaje se envió.
    """
    contexto = contexto or {}
    clave = clave or f"{titulo}:{type(exc).__name__ if exc else '-'}"

    if not _debe_avisar(clave, time.monotonic()):
        logger.info("Alerta '%s' omitida (ya avisada hace poco)", clave)
        return False

    if exc is not None:
        logger.error("%s | %s", titulo, contexto, exc_info=exc)
    else:
        logger.error("%s | %s", titulo, contexto)

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=formatear_error(titulo, contexto, exc),
            parse_mode="Markdown",
        )
        return True
    except Exception:
        # Si ni siquiera se puede avisar, queda el traceback en journalctl.
        logger.exception("No pude enviar la alerta de error:\n%s", traceback.format_exc())
        return False
