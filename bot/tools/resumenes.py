"""
Orquesta la conciliación de resúmenes de tarjeta entre la web y el bot.

No hay API entre los dos: se hablan por Supabase.

  1. La web sube el PDF al bucket `resumenes` e inserta una fila 'pendiente'.
  2. `procesar_pendientes` la lee (parser determinista), la concilia contra los
     gastos y deja cada movimiento con su estado y sus sugerencias.
  3. En la web el usuario elige qué cargar: esos movimientos quedan 'a_cargar'.
  4. `cargar_elegidos` crea los gastos con el mismo `guardar_gasto` de los
     pollers (conversión de dólares incluida) y los vincula al recurrente.

Los gastos los crea siempre el bot, así la lógica de escribir un gasto de
tarjeta vive en un solo lugar.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from bot.db import queries
from bot.tools import recurrentes_matcher as matcher
from bot.tools.conciliacion_resumen import (
    FALTA, IMPUESTO, conciliar, es_candidato, ventana_de_busqueda,
)
from bot.tools.gastos import guardar_gasto, historial_comercio
from bot.tools.resumen_bbva import ResumenInvalido, leer_resumen
from bot.tools.tarjetas import nombre_tarjeta

logger = logging.getLogger(__name__)

INTERVALO = 10  # segundos: la web espera el resultado mirando la fila
CATEGORIA_IMPUESTOS = "Otros"
_FUENTE = "resumen_tarjeta"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────
# 1-2. Procesar un resumen subido
# ──────────────────────────────────────────────

def procesar_resumen(fila: dict) -> None:
    """Lee, concilia y guarda el resultado. Nunca crea gastos."""
    resumen_id = fila["id"]
    try:
        resumen = leer_resumen(queries.descargar_resumen(fila["storage_path"]))
    except ResumenInvalido as e:
        logger.warning("Resumen %s inválido: %s", resumen_id, e)
        queries.actualizar_resumen(resumen_id, {"estado": "error", "error": str(e), "procesado_at": _ahora()})
        return

    tarjeta = queries.tarjeta_por_cuenta(resumen.cuenta)
    if tarjeta is None:
        queries.actualizar_resumen(resumen_id, {
            "estado": "error", "procesado_at": _ahora(),
            "error": f"La cuenta {resumen.cuenta} ({resumen.producto}) no está asociada a ninguna tarjeta.",
        })
        return
    if queries.otro_resumen_con_cierre(resumen_id, tarjeta["id"], resumen.cierre.isoformat()):
        queries.actualizar_resumen(resumen_id, {
            "estado": "error", "procesado_at": _ahora(),
            "error": f"El resumen de {nombre_tarjeta(tarjeta)} con cierre {resumen.cierre:%d/%m/%Y} ya estaba cargado.",
        })
        return

    sufijo = tarjeta["sufijo"]
    desde, hasta = ventana_de_busqueda(resumen)
    gastos = [g for g in queries.gastos_entre(desde.isoformat(), hasta.isoformat()) if es_candidato(g, sufijo)]
    conciliacion = conciliar(resumen, gastos, sufijo)

    filas = []
    for orden, r in enumerate(conciliacion.resultados):
        m = r.movimiento
        fila_mov = {
            "resumen_id": resumen_id, "orden": orden, "seccion": m.seccion,
            "fecha": m.fecha.isoformat(), "descripcion": m.descripcion, "cupon": m.cupon,
            "monto": str(m.monto), "moneda": m.moneda,
            "cuota_actual": m.cuota_actual, "cuotas_total": m.cuotas_total,
            "estado": r.estado, "gasto_id": r.gasto_id,
        }
        if r.estado == FALTA:
            fila_mov.update(_sugerencias(m))
        elif r.estado == IMPUESTO:
            fila_mov["categoria_sugerida"] = CATEGORIA_IMPUESTOS
        filas.append(fila_mov)

    queries.reemplazar_movimientos_resumen(resumen_id, filas)
    queries.actualizar_resumen(resumen_id, {
        "estado": "procesado", "error": None, "procesado_at": _ahora(),
        "tarjeta_id": tarjeta["id"],
        "cierre": resumen.cierre.isoformat(),
        "cierre_anterior": resumen.cierre_anterior.isoformat(),
        "vencimiento": resumen.vencimiento.isoformat(),
        "saldo_actual": {k: str(v) for k, v in resumen.saldo_actual.items()},
        "sin_movimiento": [
            {"id": g["id"], "fecha": g["fecha"], "comercio": g.get("comercio") or g.get("descripcion"),
             "monto": g.get("monto_original"), "moneda": g.get("moneda")}
            for g in conciliacion.sin_movimiento
        ],
    })
    logger.info(
        "Resumen %s procesado: %s cierre %s, %d movimientos",
        resumen_id, nombre_tarjeta(tarjeta), resumen.cierre, len(filas),
    )


def _sugerencias(m) -> dict:
    """
    Recurrente por alias/fuzzy y categoría, sin LLM.

    Si hay recurrente, su categoría manda: es la que eligió el usuario. El
    historial por comercio es un respaldo flojo con estas descripciones
    ("MAPFRE SEGUROS0411417538070-004-000" sugería "Hogar" en vez de la
    "Transporte" del fijo de Mapfre).
    """
    rec = matcher.sugerir_recurrente({
        "comercio": m.descripcion, "monto_original": float(m.monto),
        "moneda": m.moneda, "fecha": m.fecha.isoformat(),
    })
    if rec:
        return {"recurrente_id": rec["id"], "categoria_sugerida": rec.get("categoria")}
    try:
        return {"categoria_sugerida": historial_comercio(m.descripcion).get("categoria_mas_frecuente")}
    except Exception:
        logger.exception("No pude buscar el historial de %r", m.descripcion)
        return {}


# ──────────────────────────────────────────────
# 3-4. Cargar lo que el usuario eligió
# ──────────────────────────────────────────────

def cargar_movimiento(mov: dict) -> None:
    """
    Crea el gasto de un movimiento elegido en la web.

    Idempotente: el gasto lleva `email_message_id = resumen:<id del movimiento>`,
    así que si el proceso muere entre crear el gasto y marcar el movimiento, el
    reintento encuentra el gasto en vez de duplicarlo.
    """
    clave = f"resumen:{mov['id']}"
    existente = queries.gasto_por_email(clave)
    if existente:
        queries.actualizar_movimiento_resumen(mov["id"], {"estado": "cargado", "gasto_id": existente["id"]})
        return

    categoria = mov.get("categoria_sugerida")
    if not categoria:
        queries.actualizar_movimiento_resumen(mov["id"], {"estado": FALTA})
        logger.warning("Movimiento %s sin categoría: vuelve a 'falta'", mov["id"])
        return

    resumen = mov["resumenes_tarjeta"]
    tarjeta = resumen["tarjetas"]
    moneda = mov["moneda"]
    # Una cuota se imprime con la fecha de la compra original; el gasto de la
    # cuota es del período de este resumen.
    fecha = resumen["cierre"] if mov.get("cuota_actual") else mov["fecha"]

    gasto = guardar_gasto(
        descripcion=mov["descripcion"],
        monto=float(mov["monto"]),
        moneda=moneda,
        categoria=categoria,
        medio_pago="credito_usd" if moneda == "USD" else "credito_ars",
        fecha=fecha,
        cuotas=mov.get("cuotas_total") or 1,
        cuota_actual=mov.get("cuota_actual") or 1,
        comercio=mov["descripcion"],
        notas=f"Cargado desde el resumen con cierre {resumen['cierre']}",
        fuente=_FUENTE,
        tarjeta=nombre_tarjeta(tarjeta),
        email_message_id=clave,
    )

    if mov.get("recurrente_id"):
        rec = next((r for r in queries.obtener_recurrentes_activos() if r["id"] == mov["recurrente_id"]), None)
        if rec:
            matcher.confirmar_vinculacion(
                gasto["id"], rec, comercio=mov["descripcion"], guardar_alias=False,
                nuevo_monto=float(mov["monto"]), fecha_pago=fecha,
            )

    queries.actualizar_movimiento_resumen(mov["id"], {"estado": "cargado", "gasto_id": gasto["id"]})
    logger.info("Movimiento %s cargado como gasto %s", mov["id"], gasto["id"])


def procesar_ciclo() -> None:
    for fila in queries.resumenes_pendientes():
        try:
            procesar_resumen(fila)
        except Exception as e:
            logger.exception("Error inesperado procesando el resumen %s", fila["id"])
            queries.actualizar_resumen(fila["id"], {
                "estado": "error", "procesado_at": _ahora(),
                "error": f"Error inesperado al procesarlo ({type(e).__name__}). Revisá los logs del bot.",
            })
    for mov in queries.movimientos_a_cargar():
        try:
            cargar_movimiento(mov)
        except Exception:
            # Queda 'a_cargar' y se reintenta en el ciclo siguiente.
            logger.exception("Error cargando el movimiento %s", mov["id"])


async def loop_resumenes() -> None:
    logger.info("Loop de resúmenes iniciado (cada %ds)", INTERVALO)
    while True:
        try:
            await asyncio.to_thread(procesar_ciclo)
        except Exception:
            logger.exception("Error en el loop de resúmenes")
        await asyncio.sleep(INTERVALO)

