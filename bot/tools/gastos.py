"""
Herramientas de escritura y lectura de gastos.
Estas funciones son las que el agente llama como "tools".
"""

import calendar
import logging
from datetime import date, datetime
from bot.db import queries
from bot.tools.tipo_cambio import convertir_usd_a_ars, obtener_tipo_cambio

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
        logger.warning("guardar_gasto: moneda inválida=%r", moneda)
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

    primer_registro = queries.insertar_gasto(gasto)
    logger.info("guardar_gasto ok: %r monto_ars=%s cuotas=%s", descripcion, gasto.get("monto_ars"), cuotas)

    # Auto-generar cuotas 2..N si corresponde
    if cuotas > 1 and cuota_actual == 1:
        fecha_cuota = date.fromisoformat(fecha_gasto)
        for n in range(2, cuotas + 1):
            fecha_cuota = _siguiente_mes(fecha_cuota)
            cuota_extra = {**gasto, "fecha": fecha_cuota.isoformat(), "cuota_actual": n}
            queries.insertar_gasto(cuota_extra)

    return primer_registro


def guardar_multiples_gastos(gastos: list[dict]) -> dict:
    """
    Guarda múltiples gastos en un solo llamado, después de que el usuario confirmó el listado.

    Args:
        gastos: Lista de dicts, cada uno con los mismos campos que guardar_gasto().
                Campos requeridos: descripcion, monto, moneda, categoria, medio_pago.
                Campos opcionales: fecha, cuotas, cuota_actual, comercio, notas, fuente, tipo_cambio_tipo.

    Returns:
        {
            "guardados": int,
            "errores": [{"indice": int, "descripcion": str, "error": str}],
            "ids": [uuid, ...]
        }
    """
    guardados = 0
    errores = []
    ids = []

    for i, g in enumerate(gastos):
        try:
            registro = guardar_gasto(**g)
            guardados += 1
            ids.append(registro.get("id"))
        except Exception as e:
            errores.append({
                "indice": i + 1,
                "descripcion": g.get("descripcion", "?"),
                "error": str(e),
            })

    return {"guardados": guardados, "errores": errores, "ids": ids}


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


def tendencia_gastos(meses: int = 6) -> dict:
    """
    Devuelve la evolución del gasto total en los últimos N meses,
    con variación porcentual mes a mes.

    Returns:
        {
            "meses_analizados": 6,
            "tendencia": [
                {"mes": 10, "anio": 2024, "total_ars": 120000.0, "cantidad_gastos": 35, "variacion_pct": None},
                {"mes": 11, "anio": 2024, "total_ars": 145000.0, "cantidad_gastos": 42, "variacion_pct": 20.8},
                ...
            ]
        }
    """
    hoy = date.today()

    # Construir lista de (mes, anio) para los últimos N meses, del más viejo al más nuevo
    periodos = []
    for i in range(meses - 1, -1, -1):
        mes = hoy.month - i
        anio = hoy.year
        while mes <= 0:
            mes += 12
            anio -= 1
        periodos.append((mes, anio))

    tendencia = []
    for mes, anio in periodos:
        r = resumen_mensual(mes, anio)
        tendencia.append({
            "mes": mes,
            "anio": anio,
            "total_ars": r["total_ars"],
            "cantidad_gastos": r["cantidad_gastos"],
            "variacion_pct": None,
        })

    # Calcular variación mes a mes
    for i in range(1, len(tendencia)):
        prev = tendencia[i - 1]["total_ars"]
        curr = tendencia[i]["total_ars"]
        if prev > 0:
            tendencia[i]["variacion_pct"] = round((curr - prev) / prev * 100, 1)

    return {
        "meses_analizados": meses,
        "tendencia": tendencia,
    }


def top_comercios(mes: int | None = None, anio: int | None = None, limite: int = 10) -> dict:
    """
    Devuelve el ranking de los comercios/descripciones con mayor gasto en un período.

    Args:
        mes:    Mes a analizar (default: mes actual).
        anio:   Año a analizar (default: año actual).
        limite: Cantidad máxima de resultados (default: 10).

    Returns:
        {
            "mes": 3, "anio": 2025,
            "top_comercios": [
                {"nombre": "Carrefour", "total_ars": 45000.0, "cantidad": 5},
                ...
            ]
        }
    """
    hoy = date.today()
    filtros = {
        "mes": mes or hoy.month,
        "anio": anio or hoy.year,
    }

    gastos = queries.obtener_gastos(filtros)

    por_comercio: dict[str, dict] = {}
    for g in gastos:
        nombre = g.get("comercio") or g.get("descripcion") or "Sin descripción"
        if nombre not in por_comercio:
            por_comercio[nombre] = {"nombre": nombre, "total_ars": 0.0, "cantidad": 0}
        por_comercio[nombre]["total_ars"] += g.get("monto_ars") or 0
        por_comercio[nombre]["cantidad"] += 1

    top = sorted(por_comercio.values(), key=lambda x: x["total_ars"], reverse=True)[:limite]
    for item in top:
        item["total_ars"] = round(item["total_ars"], 2)

    return {
        "mes": filtros["mes"],
        "anio": filtros["anio"],
        "top_comercios": top,
    }


def proyeccion_mensual() -> dict:
    """
    Proyecta el gasto total del mes actual basándose en el ritmo de los días transcurridos.

    Returns:
        {
            "mes": 3, "anio": 2025,
            "dias_transcurridos": 13,
            "dias_totales": 31,
            "gastado_hasta_hoy": 85000.0,
            "promedio_diario_ars": 6538.46,
            "proyeccion_fin_de_mes_ars": 202692.0,
            "por_categoria": [...]
        }
    """
    import calendar

    hoy = date.today()
    dias_transcurridos = hoy.day
    dias_totales = calendar.monthrange(hoy.year, hoy.month)[1]

    r = resumen_mensual(hoy.month, hoy.year)
    gastado = r["total_ars"]

    if dias_transcurridos > 0:
        promedio_diario = round(gastado / dias_transcurridos, 2)
        proyectado = round(gastado / dias_transcurridos * dias_totales, 2)
    else:
        promedio_diario = 0.0
        proyectado = 0.0

    return {
        "mes": hoy.month,
        "anio": hoy.year,
        "dias_transcurridos": dias_transcurridos,
        "dias_totales": dias_totales,
        "gastado_hasta_hoy": gastado,
        "promedio_diario_ars": promedio_diario,
        "proyeccion_fin_de_mes_ars": proyectado,
        "por_categoria": r["por_categoria"],
    }
