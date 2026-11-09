"""
Concilia un resumen de tarjeta contra los gastos ya registrados.

Es una función pura: recibe el resumen parseado y los gastos candidatos, y
devuelve qué pasó con cada movimiento. No escribe nada; lo que se carga lo
decide el usuario en la pantalla de conciliación.

Un movimiento del resumen coincide con un gasto si tienen la misma moneda, el
monto exacto al centavo y una fecha cercana. El nombre del comercio solo
desempata: el aviso y el resumen lo escriben distinto ("Mapfre Seguros Sa"
contra "MAPFRE SEGUROS0411417538070-004-000"). Cada gasto se usa una sola vez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from rapidfuzz import fuzz

from bot.tools.resumen_bbva import Movimiento, Resumen

# Ventana de fechas entre el consumo del resumen y el gasto registrado. El aviso
# lleva la fecha de autorización, que puede quedar unos días antes o después de
# la que imprime el resumen.
DIAS_ANTES = 3
DIAS_DESPUES = 5
# Una cuota se imprime con la fecha de la compra original; el gasto de la cuota
# se registra en el mes en curso. Se la busca dentro del período del resumen.
MARGEN_PERIODO = 7

# Estados de cada movimiento
COINCIDE = "coincide"
FALTA = "falta"
IMPUESTO = "impuesto"
PERCEPCION = "percepcion"          # DB.RG 5617: se reintegra si el saldo en USD se paga en USD
REINTEGRO = "reintegro"            # CR.RG 5617 y otros créditos que no son pagos
PAGO = "pago"                      # pagos del resumen anterior: no son gastos
CUOTA_REGISTRADA = "cuota_registrada"  # cuota de una compra que se registró por el total

_PERCEPCION_RE = re.compile(r"^DB\.?RG\s*5617", re.IGNORECASE)
_REINTEGRO_RE = re.compile(r"^CR\.?RG\s*5617", re.IGNORECASE)


@dataclass(frozen=True)
class Resultado:
    movimiento: Movimiento
    estado: str
    gasto_id: str | None = None


@dataclass(frozen=True)
class Conciliacion:
    resultados: list[Resultado]
    # Gastos de la tarjeta con fecha dentro del período que no aparecen en el
    # resumen: un reverso, o algo que entra en el resumen siguiente.
    sin_movimiento: list[dict]


def es_de_la_tarjeta(g: dict, sufijo: str) -> bool:
    """
    El campo `tarjeta` se escribió de varias formas a lo largo del tiempo
    ("BBVA Visa 1670", "Visa Credito 1670", "Visa Crédito 1670"); lo estable
    son los últimos cuatro dígitos.
    """
    return re.search(rf"\b{re.escape(sufijo)}$", (g.get("tarjeta") or "").strip()) is not None


def es_candidato(g: dict, sufijo: str) -> bool:
    """De esta tarjeta, o de crédito sin tarjeta asignada (planes de cuotas)."""
    if es_de_la_tarjeta(g, sufijo):
        return True
    return not g.get("tarjeta") and (g.get("medio_pago") or "").startswith("credito")


def _clasificar(m: Movimiento) -> str | None:
    """Estado de los movimientos que no se buscan entre los gastos."""
    if m.seccion == "pago":
        return REINTEGRO if _REINTEGRO_RE.match(m.descripcion) else PAGO
    if m.seccion == "impuesto":
        return PERCEPCION if _PERCEPCION_RE.match(m.descripcion) else IMPUESTO
    return None


def _monto(g: dict) -> Decimal:
    return Decimal(str(g.get("monto_original") or 0)).quantize(Decimal("0.01"))


def _fecha(g: dict) -> date:
    return date.fromisoformat(str(g["fecha"])[:10])


def _normalizar(texto: str) -> str:
    texto = re.sub(r"\bC\.\d{2}/\d{2}\b", " ", texto.lower())
    texto = re.sub(r"[^a-z0-9 ]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _ventana(m: Movimiento, r: Resumen) -> tuple[date, date]:
    if m.cuota_actual:
        return r.cierre_anterior - timedelta(days=MARGEN_PERIODO), r.cierre + timedelta(days=MARGEN_PERIODO)
    return m.fecha - timedelta(days=DIAS_ANTES), m.fecha + timedelta(days=DIAS_DESPUES)


def _candidatos(m: Movimiento, r: Resumen, gastos: list[dict], usados: set[str]) -> list[dict]:
    desde, hasta = _ventana(m, r)
    return [
        g for g in gastos
        if g["id"] not in usados
        and (g.get("moneda") or "ARS").upper() == m.moneda
        and _monto(g) == m.monto
        and desde <= _fecha(g) <= hasta
    ]


def _compra_en_cuotas(m: Movimiento, gastos: list[dict]) -> dict | None:
    """
    El gasto registrado por el TOTAL de la compra de la que esta línea es una cuota.

    Caso real: el aviso de "MODOQRI*ANTONIO LU" llegó por $60.997,99 y el
    resumen lo cobra en 3 cuotas de $20.332,67 (la primera) y $20.332,66. El
    redondeo de cada cuota deja unos centavos de diferencia contra el total.
    La cuota lleva la fecha de la compra original, así que esa fecha es la que
    se busca.
    """
    if not m.cuota_actual or not m.cuotas_total or m.cuotas_total < 2:
        return None
    total = m.monto * m.cuotas_total
    tolerancia = Decimal("0.01") * m.cuotas_total
    desde, hasta = m.fecha - timedelta(days=DIAS_ANTES), m.fecha + timedelta(days=DIAS_DESPUES)
    opciones = [
        g for g in gastos
        if (g.get("moneda") or "ARS").upper() == m.moneda
        and abs(_monto(g) - total) <= tolerancia
        and desde <= _fecha(g) <= hasta
    ]
    return max(opciones, key=lambda g: _puntaje(m, g)) if opciones else None


def _puntaje(m: Movimiento, g: dict) -> tuple:
    """Mayor es mejor: primero el nombre, después la cercanía de la fecha."""
    nombre = fuzz.token_set_ratio(_normalizar(m.descripcion), _normalizar(g.get("comercio") or g.get("descripcion") or ""))
    return (nombre, -abs((_fecha(g) - m.fecha).days))


def conciliar(resumen: Resumen, gastos: list[dict], sufijo: str) -> Conciliacion:
    """
    `gastos` son los candidatos: los de esta tarjeta y los de crédito sin
    tarjeta asignada (los planes de cuotas se registran así).

    Se asigna primero a los movimientos con menos candidatos, para que uno
    ambiguo no le robe el gasto a uno que solo tiene esa opción.
    """
    estados: dict[int, Resultado] = {}
    pendientes: list[int] = []
    for i, m in enumerate(resumen.movimientos):
        fijo = _clasificar(m)
        if fijo:
            estados[i] = Resultado(m, fijo)
        else:
            pendientes.append(i)

    usados: set[str] = set()
    opciones = {i: _candidatos(resumen.movimientos[i], resumen, gastos, usados) for i in pendientes}
    for i in sorted(pendientes, key=lambda i: (len(opciones[i]), i)):
        m = resumen.movimientos[i]
        libres = [g for g in opciones[i] if g["id"] not in usados]
        if not libres:
            compra = _compra_en_cuotas(m, [g for g in gastos if g["id"] not in usados])
            if compra:
                usados.add(compra["id"])
                estados[i] = Resultado(m, CUOTA_REGISTRADA, gasto_id=compra["id"])
            else:
                estados[i] = Resultado(m, FALTA)
            continue
        elegido = max(libres, key=lambda g: _puntaje(m, g))
        usados.add(elegido["id"])
        estados[i] = Resultado(m, COINCIDE, gasto_id=elegido["id"])

    # Solo los que son de ESTA tarjeta: un gasto sin tarjeta asignada no se
    # puede atribuir a ningún resumen, y aparecería sobrando en todos.
    desde, hasta = resumen.cierre_anterior + timedelta(days=1), resumen.cierre
    sin_movimiento = [
        g for g in gastos
        if g["id"] not in usados and desde <= _fecha(g) <= hasta
        and es_de_la_tarjeta(g, sufijo)
    ]
    return Conciliacion([estados[i] for i in range(len(resumen.movimientos))], sin_movimiento)


def ventana_de_busqueda(resumen: Resumen) -> tuple[date, date]:
    """Rango de fechas de gastos que hay que traer para conciliar este resumen."""
    fechas = [m.fecha for m in resumen.movimientos] + [resumen.cierre_anterior]
    return min(fechas) - timedelta(days=MARGEN_PERIODO), resumen.cierre + timedelta(days=MARGEN_PERIODO)
