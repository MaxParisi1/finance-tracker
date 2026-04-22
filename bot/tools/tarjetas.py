"""
Lógica de negocio para tarjetas.
Resuelve el medio_pago a partir del sufijo de tarjeta y la moneda del consumo.
Si el sufijo no está registrado, lo crea con tipo=credito y pendiente_clasificacion=True.
"""

import logging

from bot.db.queries import buscar_tarjeta_por_sufijo, insertar_tarjeta

logger = logging.getLogger(__name__)

_MEDIO_PAGO_MAP: dict[tuple[str, str], str] = {
    ("credito", "ARS"): "credito_ars",
    ("credito", "USD"): "credito_usd",
    ("debito", "ARS"): "debito",
    ("debito", "USD"): "debito",
}


def resolver_medio_pago(sufijo: str, moneda: str = "ARS") -> tuple[str, dict]:
    """
    Devuelve (medio_pago, tarjeta_row).
    Si el sufijo no existe lo crea con tipo=credito y pendiente_clasificacion=True.
    """
    tarjeta = buscar_tarjeta_por_sufijo(sufijo)

    if tarjeta is None:
        try:
            tarjeta = insertar_tarjeta({
                "sufijo": sufijo,
                "tipo": "credito",
                "red": "visa",
                "pendiente_clasificacion": True,
            })
        except Exception:
            # Otro proceso insertó el mismo sufijo concurrentemente; buscamos el row existente
            tarjeta = buscar_tarjeta_por_sufijo(sufijo)
            if tarjeta is None:
                raise
        logger.warning("Sufijo de tarjeta no registrado: %s — creado con tipo=credito por default", sufijo)

    tipo = tarjeta.get("tipo", "credito")
    medio_pago = _MEDIO_PAGO_MAP.get((tipo, moneda.upper()), "credito_ars")
    return medio_pago, tarjeta


def nombre_tarjeta(tarjeta: dict) -> str:
    """Devuelve una descripción legible de la tarjeta para guardar en el campo tarjeta del gasto."""
    red = (tarjeta.get("red") or "Visa").capitalize()
    tipo = "Crédito" if tarjeta.get("tipo") == "credito" else "Débito"
    sufijo = tarjeta.get("sufijo", "????")
    nombre = tarjeta.get("nombre")
    if nombre:
        return f"{nombre} {sufijo}"
    return f"{red} {tipo} {sufijo}"
