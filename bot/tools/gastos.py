"""
Herramientas de escritura y lectura de gastos.
Estas funciones son las que el agente llama como "tools".
"""

from datetime import date, datetime
from bot.db import queries
from bot.tools.tipo_cambio import convertir_usd_a_ars, obtener_tipo_cambio


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
    tipo_cambio_tipo: str = "blue",
) -> dict:
    """
    Guarda un gasto en la base de datos.
    Si la moneda es USD, convierte automáticamente a ARS usando el TC blue (por defecto).

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
        tipo_cambio_tipo: 'blue' (default), 'oficial' o 'mep'.

    Returns:
        El registro guardado como dict.
    """
    moneda = moneda.upper()
    if moneda not in ("ARS", "USD"):
        raise ValueError(f"Moneda inválida: '{moneda}'. Usar 'ARS' o 'USD'.")

    fecha_gasto = fecha or date.today().isoformat()

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

    return queries.insertar_gasto(gasto)


def guardar_gasto_recurrente(
    descripcion: str,
    monto: float,
    moneda: str,
    frecuencia: str,
    dia_del_mes: int,
    categoria: str,
    medio_pago: str,
) -> dict:
    """
    Registra un gasto recurrente (suscripción, expensa, etc.).

    Args:
        frecuencia: 'mensual', 'anual' o 'semanal'.
        dia_del_mes: Día del mes en que vence (1-31).
    """
    from datetime import timedelta

    moneda = moneda.upper()
    hoy = date.today()

    # Calcular próximo vencimiento
    try:
        proximo = date(hoy.year, hoy.month, dia_del_mes)
        if proximo < hoy:
            if hoy.month == 12:
                proximo = date(hoy.year + 1, 1, dia_del_mes)
            else:
                proximo = date(hoy.year, hoy.month + 1, dia_del_mes)
    except ValueError:
        # día inválido para ese mes (ej: 31 en febrero); usar último día del mes
        import calendar
        ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
        proximo = date(hoy.year, hoy.month, min(dia_del_mes, ultimo_dia))

    recurrente = {
        "descripcion": descripcion,
        "monto_original": monto,
        "moneda": moneda,
        "categoria": categoria,
        "medio_pago": medio_pago,
        "frecuencia": frecuencia,
        "dia_del_mes": dia_del_mes,
        "proximo_vencimiento": proximo.isoformat(),
    }

    return queries.insertar_recurrente(recurrente)


def editar_gasto(gasto_id: str, campos_a_modificar: dict) -> dict:
    """
    Edita uno o más campos de un gasto existente.

    Args:
        gasto_id: UUID del gasto a editar.
        campos_a_modificar: Dict con los campos a cambiar, ej: {"categoria": "Transporte"}.
    """
    # Si se modifica el monto o la moneda, recalcular monto_ars
    if "monto" in campos_a_modificar or "moneda" in campos_a_modificar:
        gasto_actual = queries.obtener_gasto_por_id(gasto_id)
        if not gasto_actual:
            raise ValueError(f"No se encontró el gasto con id: {gasto_id}")

        monto = campos_a_modificar.get("monto", gasto_actual["monto_original"])
        moneda = campos_a_modificar.get("moneda", gasto_actual["moneda"]).upper()

        if "monto" in campos_a_modificar:
            campos_a_modificar["monto_original"] = campos_a_modificar.pop("monto")

        if moneda == "USD":
            conversion = convertir_usd_a_ars(monto)
            campos_a_modificar["monto_ars"] = conversion["monto_ars"]
            campos_a_modificar["tipo_cambio"] = conversion["tipo_cambio"]
            campos_a_modificar["tipo_cambio_tipo"] = conversion["tipo_cambio_tipo"]
        else:
            campos_a_modificar["monto_ars"] = monto
            campos_a_modificar["tipo_cambio"] = 1.0
            campos_a_modificar["tipo_cambio_tipo"] = "n/a"

    return queries.actualizar_gasto(gasto_id, campos_a_modificar)


def eliminar_gasto(gasto_id: str) -> dict:
    """Elimina un gasto por su UUID. Devuelve confirmación."""
    queries.eliminar_gasto(gasto_id)
    return {"eliminado": True, "id": gasto_id}


# ──────────────────────────────────────────────
# Lectura y consulta
# ──────────────────────────────────────────────

def consultar_gastos(filtros: dict | None = None) -> dict:
    """
    Devuelve gastos filtrados con totales.

    filtros admitidos: mes, anio, categoria, medio_pago, moneda,
                       fecha_desde, fecha_hasta
    """
    filtros = filtros or {}
    gastos = queries.obtener_gastos(filtros)

    total_ars = sum(g.get("monto_ars") or 0 for g in gastos)

    return {
        "cantidad": len(gastos),
        "total_ars": round(total_ars, 2),
        "gastos": gastos,
    }


def resumen_mensual(mes: int, anio: int) -> dict:
    """
    Devuelve el total gastado en el mes agrupado por categoría.

    Returns:
        {
            "mes": 1,
            "anio": 2024,
            "total_ars": 150000.0,
            "por_categoria": [
                {"categoria": "Alimentación", "total_ars": 50000.0, "cantidad": 8},
                ...
            ]
        }
    """
    resultado = consultar_gastos({"mes": mes, "anio": anio})
    gastos = resultado["gastos"]

    por_cat: dict[str, dict] = {}
    for g in gastos:
        cat = g.get("categoria") or "Sin categoría"
        if cat not in por_cat:
            por_cat[cat] = {"categoria": cat, "total_ars": 0.0, "cantidad": 0}
        por_cat[cat]["total_ars"] += g.get("monto_ars") or 0
        por_cat[cat]["cantidad"] += 1

    por_categoria = sorted(
        [{"categoria": k, "total_ars": round(v["total_ars"], 2), "cantidad": v["cantidad"]}
         for k, v in por_cat.items()],
        key=lambda x: x["total_ars"],
        reverse=True,
    )

    return {
        "mes": mes,
        "anio": anio,
        "total_ars": resultado["total_ars"],
        "cantidad_gastos": resultado["cantidad"],
        "por_categoria": por_categoria,
    }


def comparar_meses(mes1: int, anio1: int, mes2: int, anio2: int) -> dict:
    """Compara los totales y distribución de categorías entre dos meses."""
    r1 = resumen_mensual(mes1, anio1)
    r2 = resumen_mensual(mes2, anio2)

    diferencia = round(r2["total_ars"] - r1["total_ars"], 2)
    variacion_pct = (
        round((diferencia / r1["total_ars"]) * 100, 1) if r1["total_ars"] else 0
    )

    return {
        "mes1": r1,
        "mes2": r2,
        "diferencia_ars": diferencia,
        "variacion_porcentual": variacion_pct,
    }


def gastos_recurrentes_activos() -> dict:
    """Devuelve los gastos recurrentes activos con su próximo vencimiento."""
    recurrentes = queries.obtener_recurrentes_activos()
    return {
        "cantidad": len(recurrentes),
        "recurrentes": recurrentes,
    }
