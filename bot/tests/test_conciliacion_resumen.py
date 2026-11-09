"""
Conciliación de un resumen de tarjeta contra los gastos registrados.

Es una función pura: los casos se arman con el resumen y los gastos tal como
estaban en producción al conciliar los resúmenes de octubre de 2026.
"""

from datetime import date
from decimal import Decimal

import pytest

from bot.tools.conciliacion_resumen import (
    BONIFICACION, COINCIDE, CUOTA_REGISTRADA, FALTA, IMPUESTO, PAGO, PERCEPCION, REINTEGRO,
    conciliar, es_candidato,
)
from bot.tools.resumen_bbva import Movimiento, Resumen


def _mov(fecha, descripcion, monto, moneda="ARS", seccion="consumo", cuota=None, cupon=None):
    actual, total = cuota or (None, None)
    return Movimiento(
        seccion=seccion, fecha=date.fromisoformat(fecha), descripcion=descripcion,
        monto=Decimal(monto), moneda=moneda, cuota_actual=actual, cuotas_total=total, cupon=cupon,
    )


def _resumen(*movimientos):
    return Resumen(
        red="visa", producto="Visa Signature", cuenta="1077662388",
        cierre=date(2026, 10, 22), vencimiento=date(2026, 11, 4), cierre_anterior=date(2026, 9, 24),
        saldo_anterior={}, saldo_actual={}, movimientos=list(movimientos),
    )


def _gasto(id, fecha, monto, comercio, moneda="ARS", tarjeta="Visa Credito 1670", medio_pago="credito_ars"):
    return {"id": id, "fecha": fecha, "monto_original": monto, "moneda": moneda,
            "comercio": comercio, "tarjeta": tarjeta, "medio_pago": medio_pago}


def _estados(conc):
    return [(r.estado, r.gasto_id) for r in conc.resultados]


@pytest.mark.unit
def test_los_debitos_que_no_se_avisaron_quedan_como_faltantes():
    """
    Caso real: desde el 24/07 Payway dejó de avisar los débitos automáticos.
    Mapfre y ACA aparecen en el resumen y no hay ningún gasto que los cubra;
    el consumo avisado del mismo día sí coincide.
    """
    r = _resumen(
        _mov("2026-09-30", "MAPFRE SEGUROS0411417538070-004-000", "117063.23"),
        _mov("2026-10-12", "ACA CUOTA SOCIAL 000000430601088", "34650.00"),
        _mov("2026-09-29", "DISCO SM 022", "146921.83"),
    )
    gastos = [_gasto("disco", "2026-09-29", 146921.83, "Disco Sm 022")]

    assert _estados(conciliar(r, gastos, "1670")) == [(FALTA, None), (FALTA, None), (COINCIDE, "disco")]


@pytest.mark.unit
def test_el_monto_tiene_que_ser_exacto_y_la_moneda_igual():
    r = _resumen(
        _mov("2026-10-14", "GOOGLE *YouTubeP P1p8Hdgx USD 3,00", "3.00", moneda="USD"),
        _mov("2026-10-07", "DLO*PEDIDOSYA PLUS", "4134.00"),
    )
    gastos = [
        _gasto("yt-pesos", "2026-10-14", 3.00, "Google *Youtubepremium", moneda="ARS"),
        _gasto("plus-centavo", "2026-10-07", 4134.01, "Dlo*Pedidosya Plus"),
    ]

    assert _estados(conciliar(r, gastos, "1670")) == [(FALTA, None), (FALTA, None)]


@pytest.mark.unit
def test_la_fecha_del_aviso_puede_correrse_unos_dias():
    r = _resumen(_mov("2026-10-10", "PEDIDOSYA*MCDONALDS R02", "34583.00"))

    cerca = conciliar(r, [_gasto("g", "2026-10-11", 34583.00, "Pedidosya*Mcdonalds R02")], "1670")
    lejos = conciliar(r, [_gasto("g", "2026-10-25", 34583.00, "Pedidosya*Mcdonalds R02")], "1670")

    assert _estados(cerca) == [(COINCIDE, "g")]
    assert _estados(lejos) == [(FALTA, None)]


@pytest.mark.unit
def test_cada_gasto_se_usa_una_sola_vez():
    """Dos viajes de SUBE iguales el mismo día: dos gastos, no uno contado dos veces."""
    r = _resumen(
        _mov("2026-10-07", "SUBE VIAJES - BUSES", "2045.62"),
        _mov("2026-10-07", "SUBE VIAJES - BUSES", "2045.62"),
    )
    uno = [_gasto("a", "2026-10-07", 2045.62, "Sube Viajes - Buses")]

    assert _estados(conciliar(r, uno, "1670")) == [(COINCIDE, "a"), (FALTA, None)]


@pytest.mark.unit
def test_el_nombre_desempata_entre_dos_gastos_del_mismo_monto():
    r = _resumen(_mov("2026-10-06", "DISCO SM 022", "10198.00"))
    gastos = [
        _gasto("otro", "2026-10-06", 10198.00, "Merpago*Liu"),
        _gasto("disco", "2026-10-06", 10198.00, "Disco Sm 022"),
    ]

    assert _estados(conciliar(r, gastos, "1670")) == [(COINCIDE, "disco")]


@pytest.mark.unit
def test_la_cuota_de_un_plan_se_busca_en_el_periodo_y_no_en_la_fecha_de_compra():
    """La cuota 9/18 se imprime con la fecha de la compra (03/02); el gasto de la cuota es del 03/10."""
    r = _resumen(_mov("2026-02-03", "MERPAGO*MERCADOLIBRE C.09/18", "37856.72", cuota=(9, 18)))
    plan = [_gasto("cuota", "2026-10-03", 37856.72, "Mercado Libre", tarjeta=None)]

    assert _estados(conciliar(r, plan, "1670")) == [(COINCIDE, "cuota")]


@pytest.mark.unit
def test_la_cuota_de_una_compra_registrada_por_el_total_no_falta():
    """
    Caso real: el aviso de MODOQRI*ANTONIO LU llegó por $60.997,99 y el resumen
    lo cobra en 3 cuotas de $20.332,67 / $20.332,66. No hay que cargar la cuota:
    la compra ya está registrada entera.
    """
    r = _resumen(_mov("2026-09-10", "MODOQRI*ANTONIO LU C.01/03", "20332.67", cuota=(1, 3)))
    compra = [_gasto("total", "2026-09-10", 60997.99, "modoqri*ANTONIO LU", tarjeta="BBVA Mastercard 3327")]

    conc = conciliar(r, compra, "3327")

    assert _estados(conc) == [(CUOTA_REGISTRADA, "total")]
    assert conc.sin_movimiento == []


@pytest.mark.unit
def test_pagos_impuestos_y_percepciones_no_se_buscan_entre_los_gastos():
    """
    La percepción RG 5617 (30% sobre consumos en dólares) se reintegra en el
    resumen siguiente como CR.RG 5617 si el saldo en USD se paga en dólares:
    se separa de los impuestos para que no se cargue como un costo más.
    """
    r = _resumen(
        _mov("2026-09-29", "SU PAGO EN PESOS", "-1532984.65", seccion="pago"),
        _mov("2026-10-05", "CR.RG 5617 30% M", "-1368.94", seccion="pago"),
        _mov("2026-10-22", "IMPUESTO DE SELLOS $", "20462.41", seccion="impuesto"),
        _mov("2026-10-22", "DB.RG 5617 30% ( 4578,00 )", "1373.40", seccion="impuesto"),
    )

    assert [e for e, _ in _estados(conciliar(r, [], "1670"))] == [PAGO, REINTEGRO, IMPUESTO, PERCEPCION]


@pytest.mark.unit
def test_registrado_sin_movimiento_solo_incluye_los_de_esta_tarjeta():
    """
    Los planes de cuotas se registran sin tarjeta: no se pueden atribuir a
    ningún resumen, y antes aparecían sobrando en el de la Mastercard.
    """
    r = _resumen()
    gastos = [
        _gasto("sin-tarjeta", "2026-10-03", 37856.72, "Mercado Libre", tarjeta=None),
        _gasto("ea-cero", "2026-10-01", 0.0, "EA *ELECTRONIC ART"),
        _gasto("de-otra", "2026-10-01", 500.0, "Algo", tarjeta="BBVA Mastercard 3327"),
    ]

    assert [g["id"] for g in conciliar(r, gastos, "1670").sin_movimiento] == ["ea-cero"]


@pytest.mark.unit
def test_candidatos_por_tarjeta():
    assert es_candidato({"tarjeta": "BBVA Visa 1670"}, "1670")
    assert es_candidato({"tarjeta": "Visa Crédito 1670"}, "1670")
    assert es_candidato({"tarjeta": None, "medio_pago": "credito_ars"}, "1670")
    assert not es_candidato({"tarjeta": None, "medio_pago": "transferencia"}, "1670")
    assert not es_candidato({"tarjeta": "BBVA Visa 9854"}, "1670")
    assert not es_candidato({"tarjeta": "BBVA Visa 16701"}, "1670")


@pytest.mark.unit
def test_la_bonificacion_se_descuenta_del_consumo_con_el_mismo_cupon():
    """
    Caso real: "BONIF. CONSUMO OPENPAY*MILAGRANJAS" (-$12.003,73) lleva el
    cupón 001015, el mismo del consumo de $45.076. No es un gasto aparte: se
    resta del consumo, que ya estaba registrado.
    """
    r = _resumen(
        _mov("2026-09-29", "OPENPAY*MILAGRANJAS", "45076.00", cupon="001015"),
        _mov("2026-09-29", "BONIF. CONSUMO OPENPAY*MILAGRANJAS", "-12003.73", cupon="001015"),
    )
    gastos = [_gasto("milagranjas", "2026-09-29", 45076.00, "Openpay*Milagranjas")]

    conc = conciliar(r, gastos, "1670")

    assert _estados(conc) == [(COINCIDE, "milagranjas"), (BONIFICACION, "milagranjas")]
    assert conc.resultados[1].aplica_a == 0


@pytest.mark.unit
def test_la_bonificacion_de_un_consumo_que_falta_espera_a_ese_consumo():
    r = _resumen(
        _mov("2026-10-20", "OPENPAY*MILAGRANJAS", "48290.25", cupon="000446"),
        _mov("2026-10-20", "BONIF. CONSUMO OPENPAY*MILAGRANJAS", "-12000.12", cupon="000446"),
    )

    conc = conciliar(r, [], "1670")

    assert _estados(conc) == [(FALTA, None), (BONIFICACION, None)]
    assert conc.resultados[1].aplica_a == 0


@pytest.mark.unit
def test_una_bonificacion_sin_consumo_del_mismo_cupon_queda_para_revisar():
    r = _resumen(_mov("2026-10-20", "BONIF. CONSUMO ALGO", "-500.00", cupon="999999"))
    assert _estados(conciliar(r, [], "1670")) == [(FALTA, None)]
