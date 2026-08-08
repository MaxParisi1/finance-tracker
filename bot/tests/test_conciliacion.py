"""
Tests de la elección de factura para un documento suelto.

Lo que se protege: que un comprobante nunca salde la factura equivocada. Ante
duda se pregunta — un pago mal atribuido deja una factura falsamente saldada y
otra falsamente impaga, y eso se descubre meses después.
"""

import pytest

from bot.tools.conciliacion import (
    TOLERANCIA_MINIMA, TOLERANCIA_RELATIVA, ConciliacionAmbigua, elegir_factura,
)


def fac(id_, monto, vto="2026-08-13"):
    return {"id": id_, "monto": monto, "vencimiento": vto, "estado": "pendiente"}


# ──────────────────────────────────────────────
# Caso dominante: una sola pendiente
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_una_sola_pendiente_gana_aunque_el_monto_no_sea_exacto():
    """
    El comprobante de Personal Pay se lee $67.894,00 y la factura dice
    $67.894,40 (centavos perdidos al extraer el PDF). Tiene que vincular igual.
    """
    sel = elegir_factura([fac("f1", 67894.40)], monto=67894.00)
    assert sel.factura["id"] == "f1"
    assert sel.coincide_monto is True


@pytest.mark.unit
def test_una_sola_pendiente_gana_incluso_pagando_con_recargo():
    """Pagar el 2° vencimiento cambia el importe; sigue siendo esa factura."""
    sel = elegir_factura([fac("f1", 13405.84)], monto=13460.24)
    assert sel.factura["id"] == "f1"


@pytest.mark.unit
def test_una_sola_pendiente_gana_sin_monto_legible():
    sel = elegir_factura([fac("f1", 30562.17)], monto=None)
    assert sel.factura["id"] == "f1"
    assert sel.coincide_monto is False


@pytest.mark.unit
def test_monto_muy_distinto_vincula_pero_marca_que_no_coincide():
    """Se vincula (es la única) pero el flag permite avisarle al usuario."""
    sel = elegir_factura([fac("f1", 13405.84)], monto=999999.0)
    assert sel.factura["id"] == "f1"
    assert sel.coincide_monto is False


# ──────────────────────────────────────────────
# Sin facturas pendientes
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_sin_pendientes_no_inventa_una():
    sel = elegir_factura([], monto=13405.84)
    assert sel.factura is None
    assert "no hay facturas pendientes" in sel.motivo


# ──────────────────────────────────────────────
# Varias pendientes
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_varias_pendientes_elige_por_monto():
    """Dos meses impagos de AySA: el comprobante salda el que coincide."""
    sel = elegir_factura(
        [fac("julio", 28160.31), fac("agosto", 30562.17)],
        monto=30562.17,
    )
    assert sel.factura["id"] == "agosto"
    assert sel.coincide_monto is True


@pytest.mark.unit
def test_varias_pendientes_sin_monto_es_ambiguo():
    with pytest.raises(ConciliacionAmbigua, match="no trae monto legible"):
        elegir_factura([fac("a", 100.0), fac("b", 200.0)], monto=None)


@pytest.mark.unit
def test_varias_pendientes_con_montos_casi_iguales_es_ambiguo():
    """Dos facturas a $30.562 y $30.570: no se puede saber cuál se pagó."""
    with pytest.raises(ConciliacionAmbigua, match="varias facturas"):
        elegir_factura([fac("a", 30562.17), fac("b", 30570.00)], monto=30562.17)


@pytest.mark.unit
def test_varias_pendientes_y_ninguna_coincide_es_ambiguo():
    with pytest.raises(ConciliacionAmbigua, match="ninguna"):
        elegir_factura([fac("a", 100.0), fac("b", 200.0)], monto=99999.0)


# ──────────────────────────────────────────────
# Tolerancia
# ──────────────────────────────────────────────

ESPERADO = 30562.17
BORDE = ESPERADO * TOLERANCIA_RELATIVA  # 1528,1085


@pytest.mark.unit
@pytest.mark.parametrize("monto, coincide, caso", [
    (ESPERADO,               True,  "exacto"),
    (ESPERADO - 0.17,        True,  "centavos perdidos al extraer el PDF"),
    (ESPERADO + BORDE - 0.01, True,  "apenas dentro del borde"),
    (ESPERADO + BORDE + 0.01, False, "apenas fuera del borde"),
    (ESPERADO * 1.14,        False, "muy lejos"),
])
def test_borde_de_tolerancia_con_una_sola_pendiente(monto, coincide, caso):
    sel = elegir_factura([fac("f1", ESPERADO)], monto=monto)
    assert sel.coincide_monto is coincide, caso


@pytest.mark.unit
def test_tolerancia_minima_protege_los_montos_chicos():
    """En una factura de $10, el 5% son 50 centavos: el piso de $1 la cubre."""
    sel = elegir_factura([fac("a", 10.0), fac("b", 500.0)], monto=10.0 + TOLERANCIA_MINIMA)
    assert sel.factura["id"] == "a"


# ──────────────────────────────────────────────
# Datos corruptos
# ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("monto_roto", [None, "", "roto"])
def test_factura_con_monto_corrupto_no_rompe(monto_roto):
    sel = elegir_factura([fac("f1", monto_roto)], monto=100.0)
    assert sel.factura["id"] == "f1"
    assert sel.coincide_monto is False


@pytest.mark.unit
def test_factura_corrupta_entre_varias_se_descarta_sin_romper():
    with pytest.raises(ConciliacionAmbigua):
        elegir_factura([fac("rota", None), fac("otra", 999.0)], monto=100.0)
