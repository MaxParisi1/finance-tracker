"""
Parser del resumen de tarjeta de BBVA.

Lo que se protege: que un resumen solo se acepte si cierra al centavo con sus
propios totales, y que cualquier cosa que no se sepa leer lo rechace entero en
vez de cargar datos a medias.

Los PDFs reales traen nombre, dirección y número de cuenta, así que viven en
`resumenes/` en la raíz (ignorada por git) y los tests que los usan se saltean
fuera de la máquina donde están. El resto arma un resumen sintético con las
mismas posiciones de columna que el real.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from bot.tools.resumen_bbva import (
    LineaPdf, Palabra, ResumenInvalido, leer_resumen, parsear,
)

RESUMENES = Path(__file__).resolve().parents[2] / "resumenes"

# Borde derecho de las columnas en el PDF real (portada y detalle).
X_ARS_PORTADA, X_USD_PORTADA = 490.1, 574.3
X_ARS, X_USD = 501.7, 574.2


def _real(nombre: str):
    ruta = RESUMENES / nombre
    if not ruta.exists():
        pytest.skip(f"falta el resumen real {nombre}")
    return leer_resumen(ruta.read_bytes())


# ──────────────────────────────────────────────
# Resúmenes reales
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_visa_octubre_cierra_y_trae_los_debitos_que_no_se_avisaron():
    """
    Caso real: desde el 24/07 Payway dejó de mandar los avisos de débito
    automático. El resumen de la Visa que cerró el 22/10 es la única fuente
    donde aparecen Mapfre, la cuota de ACA y YouTube Premium.
    """
    r = _real("20261024.pdf")

    assert (r.red, r.cuenta) == ("visa", "1077662388")
    assert (r.cierre_anterior, r.cierre, r.vencimiento) == (date(2026, 9, 24), date(2026, 10, 22), date(2026, 11, 4))
    assert r.saldo_actual == {"ARS": Decimal("1724355.55"), "USD": Decimal("3.00")}
    assert len([m for m in r.movimientos if m.seccion == "consumo"]) == 45

    por_cupon = {m.cupon: m for m in r.movimientos if m.cupon}
    assert por_cupon["004212"].descripcion.startswith("MAPFRE SEGUROS")
    assert por_cupon["004212"].monto == Decimal("117063.23")
    assert por_cupon["000001"].descripcion.startswith("ACA CUOTA SOCIAL")
    youtube = por_cupon["074201"]
    assert (youtube.monto, youtube.moneda) == (Decimal("3.00"), "USD")


@pytest.mark.unit
def test_visa_octubre_cuotas_y_bonificaciones():
    r = _real("20261024.pdf")
    por_cupon = {m.cupon: m for m in r.movimientos if m.cupon and m.monto > 0}

    meli = por_cupon["605002"]
    assert (meli.fecha, meli.cuota_actual, meli.cuotas_total) == (date(2026, 2, 3), 9, 18)
    bonificaciones = [m for m in r.movimientos if m.descripcion.startswith("BONIF.")]
    assert [m.monto for m in bonificaciones] == [Decimal("-12003.73"), Decimal("-12000.12")]


@pytest.mark.unit
def test_mastercard_el_monto_en_la_descripcion_no_es_un_importe():
    """'ANTHROPIC* CLAUDE SUB USD 20,00' repite el importe en el texto; la moneda sale de la columna."""
    r = _real("20261031.pdf")

    claude = next(m for m in r.movimientos if m.descripcion.startswith("ANTHROPIC"))
    assert (claude.monto, claude.moneda, claude.cupon) == (Decimal("20.00"), "USD", "399229")
    assert claude.descripcion == "ANTHROPIC* CLAUDE SUB USD 20,00"


@pytest.mark.unit
def test_mastercard_septiembre_cierra_con_los_impuestos():
    r = _real("20261003.pdf")

    impuestos = [m for m in r.movimientos if m.seccion == "impuesto"]
    assert sum(m.monto for m in impuestos) == Decimal("67216.11")
    assert all(m.fecha == date(2026, 10, 1) for m in impuestos)


# ──────────────────────────────────────────────
# Resumen sintético (mismas columnas que el real)
# ──────────────────────────────────────────────

def _l(texto: str, ars: str | None = None, usd: str | None = None, *, portada: bool = False) -> LineaPdf:
    palabras = [Palabra(t, 60.0 + 30 * i) for i, t in enumerate(texto.split())]
    xa, xu = (X_ARS_PORTADA, X_USD_PORTADA) if portada else (X_ARS, X_USD)
    if ars is not None:
        palabras.append(Palabra(ars, xa))
    if usd is not None:
        palabras.append(Palabra(usd, xu))
    return LineaPdf(1, tuple(palabras))


def _encabezado(portada: bool = False) -> LineaPdf:
    xa, xu = (X_ARS_PORTADA, X_USD_PORTADA) if portada else (X_ARS, X_USD)
    return LineaPdf(1, (Palabra("FECHA", 80), Palabra("PESOS", xa), Palabra("DÓLARES", xu)))


def _sintetico(consumo_ars: str = "1.000,00", con_impuesto: bool = True, extra: list | None = None):
    return [
        _l("Tarjeta de crédito Visa Signature"),
        _l("cuenta 1077662388"),
        _l("CIERRE ACTUAL VENCIMIENTO ACTUAL SALDO ACTUAL $"),
        _l("22-Oct-26 04-Nov-26"),
        _encabezado(portada=True),
        _l("SALDO ANTERIOR", "500,00", "20,00", portada=True),
        _l("SALDO ACTUAL", "1.012,00", "5,00", portada=True),
        _l("CIERRE ANTERIOR VENCIMIENTO ANTERIOR PRÓXIMO CIERRE"),
        _l("24-Sep-26 05-Oct-26 19-Nov-26 03-Dic-26"),
        _l("DETALLE"),
        _l("Sus pagos y ajustes realizados"),
        _encabezado(),
        _l("29-Sep-26 SU PAGO EN PESOS", "-500,00"),
        _l("29-Sep-26 SU PAGO EN USD", None, "-20,00"),
        _l("Consumos Maximo Parisi"),
        _encabezado(),
        _l("30-Sep-26 MAPFRE SEGUROS 004212", consumo_ars),
        _l("12-Oct-26 ANTHROPIC* CLAUDE SUB USD 5,00 399229", None, "5,00"),
        *(extra or []),
        _l("TOTAL CONSUMOS DE MAXIMO PARISI", "1.000,00", "5,00"),
        _l("Impuestos, cargos e intereses"),
        _encabezado(),
        *([_l("22-Oct-26 IMPUESTO DE SELLOS $", "12,00")] if con_impuesto else []),
        _l("SALDO ACTUAL", "1.012,00", "5,00"),
        _l("Legales y avisos"),
    ]


@pytest.mark.unit
def test_sintetico_valido():
    r = parsear(_sintetico())
    assert [(m.seccion, m.monto, m.moneda) for m in r.movimientos] == [
        ("pago", Decimal("-500.00"), "ARS"),
        ("pago", Decimal("-20.00"), "USD"),
        ("consumo", Decimal("1000.00"), "ARS"),
        ("consumo", Decimal("5.00"), "USD"),
        ("impuesto", Decimal("12.00"), "ARS"),
    ]
    assert r.movimientos[2].cupon == "004212"
    assert r.movimientos[3].descripcion == "ANTHROPIC* CLAUDE SUB USD 5,00"


@pytest.mark.unit
def test_un_consumo_mal_leido_rechaza_el_resumen():
    with pytest.raises(ResumenInvalido, match="consumos de MAXIMO PARISI en ARS"):
        parsear(_sintetico(consumo_ars="1.000,01"))


@pytest.mark.unit
def test_un_impuesto_perdido_rechaza_el_resumen():
    with pytest.raises(ResumenInvalido, match="no da el saldo actual"):
        parsear(_sintetico(con_impuesto=False))


@pytest.mark.unit
def test_una_linea_con_importe_que_no_se_entiende_rechaza_el_resumen():
    """Un formato nuevo del banco no se ignora en silencio."""
    with pytest.raises(ResumenInvalido, match="no sé leer"):
        parsear(_sintetico(extra=[_l("REINTEGRO PROMO SIN FECHA", "0,00")]))


@pytest.mark.unit
def test_sin_portada_no_hay_resumen():
    lineas = [l for l in _sintetico() if not l.texto.startswith("cuenta")]
    with pytest.raises(ResumenInvalido, match="cuenta"):
        parsear(lineas)
