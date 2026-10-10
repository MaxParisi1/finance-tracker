"""
Alta y baja de gastos, y el historial por comercio que usa el poller para
categorizar sin gastar una llamada al LLM.
"""

import calendar
import logging
from datetime import date, datetime, timezone, timedelta
from bot.db import queries
from bot.tools.tipo_cambio import convertir_usd_a_ars

logger = logging.getLogger(__name__)


def _siguiente_mes(d: date) -> date:
    """Avanza la fecha exactamente un mes, ajustando el día si es necesario."""
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    ultimo = calendar.monthrange(d.year, d.month + 1)[1]
    return d.replace(month=d.month + 1, day=min(d.day, ultimo))


# ──────────────────────────────────────────────
# Escritura
# ──────────────────────────────────────────────

def guardar_gasto(
    descripcion: str,
    monto: float,
    moneda: str,
    categoria: str,
    medio_pago: str,
    fecha: str | None = None,
    cuotas: int = 1,
    cuota_actual: int = 1,
    comercio: str | None = None,
    notas: str | None = None,
    fuente: str = "telegram_texto",
    tipo_cambio_tipo: str = "oficial",
    tarjeta: str | None = None,
    email_message_id: str | None = None,
) -> dict:
    """
    Guarda un gasto en la base de datos.
    Si la moneda es USD, convierte automáticamente a ARS usando el TC oficial (por defecto).

    Args:
        descripcion: Descripción del gasto.
        monto: Monto en la moneda original.
        moneda: 'ARS' o 'USD'.
        categoria: Categoría del gasto (debe existir en la tabla categorias).
        medio_pago: 'credito_ars', 'credito_usd', 'debito', 'efectivo_ars',
                    'efectivo_usd' o 'transferencia'.
        fecha: Fecha en formato YYYY-MM-DD. Si None, usa hoy.
        cuotas: Total de cuotas (1 si es al contado).
        cuota_actual: Número de cuota actual.
        comercio: Nombre del comercio (opcional).
        notas: Notas adicionales (opcional).
        fuente: Origen del registro.
        tipo_cambio_tipo: 'oficial' (default), 'blue' o 'mep'.

    Returns:
        El registro guardado como dict.
    """
    moneda = moneda.upper()
    if moneda not in ("ARS", "USD"):
        logger.warning("guardar_gasto: moneda inválida=%r", moneda)
        raise ValueError(f"Moneda inválida: '{moneda}'. Usar 'ARS' o 'USD'.")

    _AR = timezone(timedelta(hours=-3))
    fecha_gasto = fecha or datetime.now(_AR).date().isoformat()

    gasto: dict = {
        "fecha": fecha_gasto,
        "descripcion": descripcion,
        "monto_original": monto,
        "moneda": moneda,
        "categoria": categoria,
        "medio_pago": medio_pago,
        "cuotas": cuotas,
        "cuota_actual": cuota_actual,
        "fuente": fuente,
    }

    if comercio:
        gasto["comercio"] = comercio
    if notas:
        gasto["notas"] = notas
    if tarjeta:
        gasto["tarjeta"] = tarjeta
    if email_message_id:
        gasto["email_message_id"] = email_message_id

    if moneda == "USD":
        conversion = convertir_usd_a_ars(monto, tipo_cambio_tipo)
        gasto["monto_ars"] = conversion["monto_ars"]
        gasto["tipo_cambio"] = conversion["tipo_cambio"]
        gasto["tipo_cambio_tipo"] = conversion["tipo_cambio_tipo"]
    else:
        # ARS: monto_ars == monto_original, sin conversión
        gasto["monto_ars"] = monto
        gasto["tipo_cambio"] = 1.0
        gasto["tipo_cambio_tipo"] = "n/a"

    primer_registro = queries.insertar_gasto(gasto)
    logger.info("guardar_gasto ok: %r monto_ars=%s cuotas=%s", descripcion, gasto.get("monto_ars"), cuotas)

    # Auto-generar cuotas 2..N si corresponde
    if cuotas > 1 and cuota_actual == 1:
        fecha_cuota = date.fromisoformat(fecha_gasto)
        for n in range(2, cuotas + 1):
            fecha_cuota = _siguiente_mes(fecha_cuota)
            cuota_extra = {**gasto, "fecha": fecha_cuota.isoformat(), "cuota_actual": n}
            # El índice único de email_message_id solo admite una fila por email;
            # las cuotas siguientes no lo llevan.
            cuota_extra.pop("email_message_id", None)
            queries.insertar_gasto(cuota_extra)

    return primer_registro


def eliminar_gasto(gasto_id: str) -> dict:
    """Elimina un gasto por su UUID. Devuelve confirmación."""
    queries.eliminar_gasto(gasto_id)
    return {"eliminado": True, "id": gasto_id}


# ──────────────────────────────────────────────
# Historial por comercio
# ──────────────────────────────────────────────


def _normalizar_comercio(nombre: str) -> str:
    """
    Intenta encontrar el nombre canónico del comercio comparando contra los comercios conocidos.
    Usa matching por prefijo de palabras (ej: 'BUSE' → 'BUSES').
    Devuelve el nombre canónico si encuentra match, o el original si no.
    """
    import re

    comercios = queries.obtener_comercios()
    if not comercios:
        return nombre

    nombre_lower = nombre.lower()
    palabras_input = [w for w in re.split(r"[\s\-_/,]+", nombre_lower) if len(w) >= 4]

    for comercio in comercios:
        c_lower = comercio.lower()
        # Match directo (substring)
        if c_lower in nombre_lower or nombre_lower in c_lower:
            return comercio
        # Match por prefijo de palabras (ej: "buse" es prefijo de "buses")
        palabras_comercio = [w for w in re.split(r"[\s\-_/,]+", c_lower) if len(w) >= 4]
        for pw in palabras_input:
            for cw in palabras_comercio:
                if cw.startswith(pw) or pw.startswith(cw):
                    return comercio

    return nombre


def historial_comercio(comercio: str) -> dict:
    """
    Busca gastos previos del mismo comercio y devuelve la categoría y medio de pago más frecuentes.
    Normaliza el nombre del comercio contra los conocidos antes de buscar.
    Útil para auto-categorizar sin preguntarle al usuario.
    """
    from collections import Counter

    comercio_normalizado = _normalizar_comercio(comercio)
    if comercio_normalizado != comercio:
        logger.info("historial_comercio: '%s' normalizado a '%s'", comercio, comercio_normalizado)

    gastos = queries.obtener_gastos({"busqueda": comercio_normalizado})

    if not gastos:
        return {"encontrado": False, "comercio": comercio_normalizado}

    categorias = Counter(g["categoria"] for g in gastos if g.get("categoria"))
    medios = Counter(g["medio_pago"] for g in gastos if g.get("medio_pago"))

    return {
        "encontrado": True,
        "comercio": comercio_normalizado,
        "cantidad_gastos": len(gastos),
        "categoria_mas_frecuente": categorias.most_common(1)[0][0] if categorias else None,
        "medio_pago_mas_frecuente": medios.most_common(1)[0][0] if medios else None,
        "ultimo_gasto": gastos[0].get("fecha") if gastos else None,
    }


