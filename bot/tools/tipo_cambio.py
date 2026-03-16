"""
Integración con bluelytics.com.ar para obtener tipos de cambio en tiempo real.
Guarda el valor en tipos_cambio_historico para auditoría.
"""

import httpx
from datetime import date
from bot.db import queries


BLUELYTICS_URL = "https://api.bluelytics.com.ar/v2/latest"


def obtener_tipo_cambio(tipo: str = "oficial") -> dict:
    """
    Consulta el tipo de cambio actual desde bluelytics.

    Args:
        tipo: 'oficial', 'blue' o 'mep'

    Returns:
        {
            "tipo": "blue",
            "valor_compra": 1050.0,
            "valor_venta": 1060.0,
            "valor": 1055.0,   # promedio (el que se usa para conversiones)
            "fecha": "2024-01-15"
        }
    """
    tipo = tipo.lower()
    if tipo not in ("oficial", "blue", "mep"):
        raise ValueError(f"Tipo de cambio inválido: '{tipo}'. Usar 'oficial', 'blue' o 'mep'.")

    response = httpx.get(BLUELYTICS_URL, timeout=10)
    response.raise_for_status()
    data = response.json()

    # Mapeo de nombres en la API
    key_map = {
        "oficial": "oficial",
        "blue": "blue",
        "mep": "blue_euro",  # bluelytics no tiene MEP directo; usar blue como fallback
    }
    key = key_map[tipo]
    cotizacion = data.get(key, data["blue"])

    compra = float(cotizacion["value_buy"])
    venta = float(cotizacion["value_sell"])
    promedio = round((compra + venta) / 2, 4)
    hoy = date.today().isoformat()

    # Guardar en histórico (upsert silencioso)
    try:
        queries.insertar_tipo_cambio(hoy, tipo, promedio)
    except Exception:
        pass  # No bloquear si falla el guardado del histórico

    return {
        "tipo": tipo,
        "valor_compra": compra,
        "valor_venta": venta,
        "valor": promedio,
        "fecha": hoy,
    }


def convertir_usd_a_ars(monto_usd: float, tipo: str = "oficial") -> dict:
    """
    Convierte un monto en USD a ARS usando el tipo de cambio indicado.

    Returns:
        {
            "monto_usd": 100.0,
            "monto_ars": 105500.0,
            "tipo_cambio": 1055.0,
            "tipo_cambio_tipo": "blue"
        }
    """
    tc = obtener_tipo_cambio(tipo)
    monto_ars = round(monto_usd * tc["valor"], 2)
    return {
        "monto_usd": monto_usd,
        "monto_ars": monto_ars,
        "tipo_cambio": tc["valor"],
        "tipo_cambio_tipo": tipo,
    }
