"""
Tests de parse_monto_ar / parse_fecha_ar contra valores REALES extraídos de las
facturas y comprobantes de julio-agosto 2026. Cada caso documenta su origen.
"""

import pytest
from datetime import date

from bot.tools.montos import (
    MontoInvalido, formatear_monto_ar, montos_en_texto, parse_fecha_ar, parse_monto_ar,
)


@pytest.mark.unit
@pytest.mark.parametrize("token, esperado, origen", [
    # Formato AR estándar (mails de factura)
    ("$13.405,84",    13405.84,  "mail Edenor · TOTAL A PAGAR"),
    ("$ 5.266,75",     5266.75,  "mail MetroGAS"),
    ("$67.894,40",    67894.40,  "mail Personal · Total a pagar"),
    ("$30.562,17",    30562.17,  "PDF AySA · Total a pagar"),
    # Sin separador de miles
    ("$ 30562,17",    30562.17,  "mail AySA · Importe"),
    ("$$$$$$$$30562,17", 30562.17, "AySA · línea de código de barras"),
    # Mercado Pago: pierde la coma decimal
    ("$ 13.40584",    13405.84,  "comprobante MP Edenor"),
    ("$ 30.56217",    30562.17,  "comprobante MP AySA"),
    ("$ 5.26675",      5266.75,  "comprobante MP MetroGAS"),
    # Expensas: el PDF parte el número en dos tokens
    ("2 58.198,55",  258198.55,  "PDF unidades · Total UF 255"),
    ("2 45.378,91",  245378.91,  "PDF unidades · Saldo mes anterior"),
    ("$ 258.198,55", 258198.55,  "comprobante transferencia consorcio"),
    # Componentes de la fila de expensas (validan la aritmética)
    ("44.614,42",     44614.42,  "PDF unidades · gastos del mes"),
    ("204.384,12",   204384.12,  "PDF unidades · gastos"),
    ("248.998,54",   248998.54,  "PDF unidades · expensa del mes"),
    ("9.200,00",       9200.00,  "PDF unidades · fondo gas"),
    ("0,01",              0.01,  "PDF unidades · ajuste"),
    # Ceros y negativos
    ("$ 0,00",            0.00,  "mail MetroGAS · deuda anterior"),
    ("-4.000,01",     -4000.01,  "PDF Personal · descuento"),
    ("$-66.490,60",  -66490.60,  "PDF Personal · pagos"),
    # Miles legítimos sin decimales (no debe activarse la regla de centavos)
    ("13.405",        13405.0,   "miles sin decimales"),
    ("1.083.739",   1083739.0,   "tres grupos de miles"),
])
def test_parse_monto_ar(token, esperado, origen):
    assert parse_monto_ar(token) == pytest.approx(esperado), origen


@pytest.mark.unit
def test_expensas_uf255_cierra_aritmeticamente():
    """
    La fila de la UF 255 se autovalida: si la suma no cierra, el parser leyó mal
    alguna columna y no debe escribir en la DB.
    """
    gastos_a = parse_monto_ar("44.614,42")
    gastos_b = parse_monto_ar("204.384,12")
    expensa = parse_monto_ar("248.998,54")
    fondo_gas = parse_monto_ar("9.200,00")
    ajuste = parse_monto_ar("0,01")
    total = parse_monto_ar("2 58.198,55")

    assert gastos_a + gastos_b == pytest.approx(expensa)
    assert expensa + fondo_gas + ajuste == pytest.approx(total)
    # Y coincide con lo efectivamente transferido al consorcio.
    assert total == pytest.approx(parse_monto_ar("$ 258.198,55"))


@pytest.mark.unit
@pytest.mark.parametrize("token, esperado, origen", [
    ("05/08/2026", date(2026, 8, 5),  "mail Edenor · vencimiento"),
    ("14/08/2026", date(2026, 8, 14), "mail MetroGAS · vencimiento"),
    ("13/08/2026", date(2026, 8, 13), "mail AySA · vencimiento"),
    ("04/08/2026", date(2026, 8, 4),  "mail Personal · vencimiento"),
    ("10/08/2026", date(2026, 8, 10), "PDF expensas · vencimiento"),
    ("13/ago/2026", date(2026, 8, 13), "comprobante MP AySA"),
    ("05/ago/2026", date(2026, 8, 5),  "comprobante MP Edenor"),
    ("14/ago/2026", date(2026, 8, 14), "comprobante MP MetroGAS"),
    ("31/07/2026", date(2026, 7, 31), "comprobante Personal Pay · fecha de pago"),
])
def test_parse_fecha_ar(token, esperado, origen):
    assert parse_fecha_ar(token) == esperado, origen


@pytest.mark.unit
def test_montos_en_texto_no_fusiona_montos_contiguos():
    """Edenor muestra 1er y 2do vencimiento juntos: hay que quedarse con el primero."""
    linea = "Hasta el 05/08/2026 $ 13.405,84   2° vencimiento 10/08/2026 $13.460,24"
    assert montos_en_texto(linea)[0] == pytest.approx(13405.84)


@pytest.mark.unit
@pytest.mark.parametrize("basura", ["", "   ", "sin numeros", "$", None])
def test_tokens_invalidos_levantan_excepcion(basura):
    """Nunca devolver un valor inventado: es preferible fallar y pedir confirmación."""
    with pytest.raises(MontoInvalido):
        parse_monto_ar(basura)


@pytest.mark.unit
@pytest.mark.parametrize("valor, esperado", [
    (13405.84,  "13.405,84"),
    (258198.55, "258.198,55"),
    (5266.75,   "5.266,75"),
    (0.0,       "0,00"),
    (0.01,      "0,01"),
    (-4000.01,  "-4.000,01"),
    (1083739.5, "1.083.739,50"),
])
def test_formatear_monto_ar(valor, esperado):
    """Python formatea al revés ('{:,.2f}' → '13,405.84'): hay que invertir."""
    assert formatear_monto_ar(valor) == esperado


@pytest.mark.unit
@pytest.mark.parametrize("texto", ["13.405,84", "258.198,55", "0,01", "-4.000,01"])
def test_formatear_y_parsear_son_inversos(texto):
    assert formatear_monto_ar(parse_monto_ar(texto)) == texto
