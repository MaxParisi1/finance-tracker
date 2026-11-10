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
    _PERCEPCION_RE, FALTA, IMPUESTO, conciliar, es_candidato, ventana_de_busqueda,
)
from bot.tools.gastos import guardar_gasto, historial_comercio
from bot.tools.resumen_bbva import ResumenInvalido, leer_resumen
from bot.tools.tarjetas import nombre_tarjeta

logger = logging.getLogger(__name__)

INTERVALO = 10  # segundos: la web espera el resultado mirando la fila
CATEGORIA_IMPUESTOS = "Impuestos y comisiones"
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
            # Si el usuario eligió el fijo a mano (no era el sugerido), es una
            # confirmación suya y se aprende como alias: así el mes que viene se
            # vincula solo. Caso real: YouTube pasó a cobrarse como
            # "GOOGLE *YouTubeP P1p8Hdgx" y el fuzzy no llegaba al umbral.
            # Lo que solo aceptó de la sugerencia no se aprende: un fuzzy
            # equivocado se repetiría para siempre.
            sugerido = matcher.sugerir_recurrente({
                "comercio": mov["descripcion"], "monto_original": float(mov["monto"]),
                "moneda": moneda, "fecha": mov["fecha"],
            })
            elegido_a_mano = not sugerido or sugerido["id"] != rec["id"]
            matcher.confirmar_vinculacion(
                gasto["id"], rec, comercio=mov["descripcion"], guardar_alias=elegido_a_mano,
                confirmado_usuario=elegido_a_mano, nuevo_monto=float(mov["monto"]), fecha_pago=fecha,
            )

    queries.actualizar_movimiento_resumen(mov["id"], {"estado": "cargado", "gasto_id": gasto["id"]})
    logger.info("Movimiento %s cargado como gasto %s", mov["id"], gasto["id"])


def cargar_impuestos(filas: list[dict]) -> None:
    """
    Los impuestos y cargos de un resumen van en UN gasto: sellos, IVA e IIBB
    por separado son líneas que no aportan nada. La percepción RG 5617 queda
    afuera (se reintegra) y, si el usuario igual la quiere, va como un
    movimiento suelto.

    Idempotente por resumen y moneda, igual que `cargar_movimiento`.
    """
    resumen = filas[0]["resumenes_tarjeta"]
    tarjeta = resumen["tarjetas"]
    for moneda in sorted({f["moneda"] for f in filas}):
        grupo = [f for f in filas if f["moneda"] == moneda]
        clave = f"resumen:{resumen['id']}:impuestos:{moneda}"
        existente = queries.gasto_por_email(clave)
        if existente:
            gasto_id = existente["id"]
        else:
            total = round(sum(float(f["monto"]) for f in grupo), 2)
            detalle = "; ".join(f"{f['descripcion']} {f['monto']}" for f in grupo)
            gasto_id = guardar_gasto(
                descripcion=f"Impuestos y cargos {nombre_tarjeta(tarjeta)}",
                monto=total,
                moneda=moneda,
                categoria=grupo[0].get("categoria_sugerida") or CATEGORIA_IMPUESTOS,
                medio_pago="credito_usd" if moneda == "USD" else "credito_ars",
                fecha=resumen["cierre"],
                comercio="Impuestos y cargos de la tarjeta",
                notas=f"Resumen con cierre {resumen['cierre']}: {detalle}",
                fuente=_FUENTE,
                tarjeta=nombre_tarjeta(tarjeta),
                email_message_id=clave,
            )["id"]
        for f in grupo:
            queries.actualizar_movimiento_resumen(f["id"], {"estado": "cargado", "gasto_id": gasto_id})
        logger.info("Impuestos del resumen %s cargados en el gasto %s", resumen["id"], gasto_id)


def aplicar_bonificacion(mov: dict) -> None:
    """
    Resta la bonificación del gasto del consumo que la generó (mismo cupón).

    Si ese consumo todavía no está registrado, la bonificación vuelve a quedar
    para revisar. La marca `[bonif:<id>]` en las notas evita descontarla dos
    veces si el proceso muere entre actualizar el gasto y marcar el movimiento.
    """
    gasto_id = mov.get("gasto_id")
    if not gasto_id:
        origen = queries.movimiento_consumo_por_cupon(mov["resumen_id"], mov.get("cupon"))
        gasto_id = origen.get("gasto_id") if origen and origen.get("estado") in ("cargado", "coincide") else None
    gasto = queries.obtener_gasto_por_id(gasto_id) if gasto_id else None
    if gasto is None:
        queries.actualizar_movimiento_resumen(mov["id"], {"estado": "bonificacion"})
        logger.info("Bonificación %s sin consumo registrado: vuelve a revisar", mov["id"])
        return

    marca = f"[bonif:{mov['id']}]"
    notas = gasto.get("notas") or ""
    if marca not in notas:
        if (gasto.get("moneda") or "ARS").upper() != mov["moneda"]:
            queries.actualizar_movimiento_resumen(mov["id"], {"estado": "bonificacion"})
            logger.warning("Bonificación %s en otra moneda que su consumo: no se aplica", mov["id"])
            return
        nuevo = round(float(gasto["monto_original"]) + float(mov["monto"]), 2)
        tipo_cambio = float(gasto.get("tipo_cambio") or 1)
        nota = f"Bonificación {mov['monto']} del resumen {marca}"
        queries.actualizar_gasto(gasto_id, {
            "monto_original": nuevo,
            "monto_ars": round(nuevo * tipo_cambio, 2),
            "notas": f"{notas}\n{nota}".strip(),
        })
    queries.actualizar_movimiento_resumen(mov["id"], {"estado": "aplicada", "gasto_id": gasto_id})
    logger.info("Bonificación %s aplicada al gasto %s", mov["id"], gasto_id)


def _es_impuesto_agrupable(mov: dict) -> bool:
    return mov["seccion"] == "impuesto" and not _PERCEPCION_RE.match(mov["descripcion"])


def _es_bonificacion(mov: dict) -> bool:
    return mov["seccion"] == "consumo" and float(mov["monto"]) < 0 and mov["descripcion"].upper().startswith("BONIF")


def procesar_ciclo() -> bool:
    """Devuelve True si quedó algún movimiento 'a_cargar' por un error: hay que reintentar pronto."""
    fallo = False
    for fila in queries.resumenes_pendientes():
        try:
            procesar_resumen(fila)
        except Exception as e:
            logger.exception("Error inesperado procesando el resumen %s", fila["id"])
            queries.actualizar_resumen(fila["id"], {
                "estado": "error", "procesado_at": _ahora(),
                "error": f"Error inesperado al procesarlo ({type(e).__name__}). Revisá los logs del bot.",
            })

    elegidos = queries.movimientos_a_cargar()
    impuestos: dict[str, list[dict]] = {}
    bonificaciones: list[dict] = []
    for mov in elegidos:
        if _es_impuesto_agrupable(mov):
            impuestos.setdefault(mov["resumen_id"], []).append(mov)
        elif _es_bonificacion(mov):
            bonificaciones.append(mov)

    # Errores: el movimiento queda 'a_cargar' y se reintenta en el ciclo siguiente.
    for filas in impuestos.values():
        try:
            cargar_impuestos(filas)
        except Exception:
            logger.exception("Error cargando los impuestos del resumen %s", filas[0]["resumen_id"])
            fallo = True
    # Los consumos antes que las bonificaciones: una bonificación necesita el
    # gasto de su consumo, que puede estar cargándose en este mismo ciclo.
    for mov in elegidos:
        if _es_impuesto_agrupable(mov) or _es_bonificacion(mov):
            continue
        try:
            cargar_movimiento(mov)
        except Exception:
            logger.exception("Error cargando el movimiento %s", mov["id"])
            fallo = True
    for mov in bonificaciones:
        try:
            aplicar_bonificacion(mov)
        except Exception:
            logger.exception("Error aplicando la bonificación %s", mov["id"])
            fallo = True
    return fallo


async def loop_resumenes() -> None:
    logger.info("Loop de resúmenes iniciado (cada %ds)", INTERVALO)
    while True:
        try:
            await asyncio.to_thread(procesar_ciclo)
        except Exception:
            logger.exception("Error en el loop de resúmenes")
        await asyncio.sleep(INTERVALO)

