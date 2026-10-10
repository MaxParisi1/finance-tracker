"""
Estado del bot que tiene que sobrevivir a un reinicio.

Dos usos:
  - La marca del recordatorio diario, para no reenviarlo en cada deploy.
  - La salud de cada poller y los mails que dejó sin procesar. Eso ya se avisa
    por Telegram, pero un mensaje se pierde chat arriba; guardado, la web lo
    muestra en "Requiere tu atención" hasta que se resuelva.

Nada de acá puede tumbar al bot: si la base falla, se loguea y se sigue con lo
que haya en memoria.
"""

import logging

from bot.db import queries

logger = logging.getLogger(__name__)

__all__ = [
    "CLAVE_RECORDATORIO", "leer", "guardar",
    "empezar_ciclo", "anotar_atascado", "cerrar_ciclo",
]

CLAVE_RECORDATORIO = "recordatorio_diario"

# etiqueta de Gmail → mails que quedaron sin leer en el ciclo en curso
_atascados: dict[str, list[dict]] = {}


def leer(clave: str):
    """Valor guardado, o None si no hay o si la base no respondió."""
    try:
        return queries.leer_estado(clave)
    except Exception:
        logger.exception("No pude leer el estado '%s'", clave)
        return None


def guardar(clave: str, valor) -> bool:
    try:
        queries.guardar_estado(clave, valor)
        return True
    except Exception:
        logger.exception("No pude guardar el estado '%s'", clave)
        return False


def empezar_ciclo(etiqueta: str) -> None:
    _atascados[etiqueta] = []


def anotar_atascado(etiqueta: str, email: dict, motivo: str) -> None:
    """Registra que un mail quedó sin leer para reintentar, y por qué."""
    lista = _atascados.setdefault(etiqueta, [])
    if any(e["id"] == email.get("id") for e in lista):
        return
    lista.append({
        "id": email.get("id"),
        "asunto": (email.get("subject") or "(sin asunto)")[:200],
        "motivo": motivo,
    })


def cerrar_ciclo(etiqueta: str, ok: bool) -> bool:
    """Persiste cómo terminó el ciclo. `ok` False = no se pudo ni consultar Gmail."""
    return guardar(f"poller:{etiqueta}", {"ok": ok, "atascados": _atascados.get(etiqueta, [])})
