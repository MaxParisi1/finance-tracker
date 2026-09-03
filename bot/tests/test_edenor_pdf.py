"""
Descarga del PDF de la factura de Edenor.

Lo que se protege acá: que el link se elija por su destino y no por su forma,
que no se pida la factura de otra cuenta, y que el PDF que llega sea el de ESTE
mes. Esto último es lo delicado del servicio: la cuenta de Edenor es la misma
todos los meses, así que el único dato que separa una factura de la anterior es
el importe.

El fixture real (`fixtures/facturas/edenor.pdf`) trae el número de cuenta y el
nombre del titular, así que está en .gitignore: los tests que dependen de él se
saltean fuera de la máquina donde se guardó.
"""

import base64
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.tools.edenor_pdf import (
    EdenorPdfNoDisponible, cuenta_del_token, es_url_de_descarga,
    token_de_url, totales_a_pagar, url_del_pdf, verificar_cuenta,
    verificar_factura,
)

FIXTURES = Path(__file__).parent / "fixtures" / "facturas"

# Los datos de la factura de julio 2026, la del PDF de fixture.
CUENTA = "5255064586"
MONTO_FIXTURE = 13405.84
MONTO_CON_RECARGO = 13460.24   # el del 2° vencimiento, en la misma portada


def _fixture(nombre: str) -> Path:
    ruta = FIXTURES / nombre
    if not ruta.exists():
        pytest.skip(f"falta el fixture {nombre}")
    return ruta


def _token(**payload) -> str:
    """Un JWT de mentira: solo importa que el payload se pueda leer."""
    crudo = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{crudo}.firma"


URL_OK = f"https://edenordigital.com/descarga_de_factura?token={_token(cuenta_id=CUENTA)}"


# ──────────────────────────────────────────────
# Qué link es el de la factura
# ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("url", [
    "https://www.edenordigital.com?utm_source=mailing",      # el portal
    "https://www.edenordigital.com/ingreso",                 # el login
    "https://www.edenor.com/terminos-y-condiciones-factura-digital",
    "https://www.facebook.com/edenoroficial",
    "https://edenordigital.com.evil.io/descarga_de_factura?token=x",
    "http://edenordigital.com/descarga_de_factura?token=x",  # sin https
])
def test_los_otros_destinos_del_mail_no_son_la_factura(url):
    """Todos salen del mismo tracker: lo único que los separa es a dónde van."""
    assert es_url_de_descarga(url) is False


@pytest.mark.unit
def test_la_pagina_de_descarga_si_lo_es():
    assert es_url_de_descarga(URL_OK) is True


@pytest.mark.unit
def test_el_token_se_saca_del_link():
    assert token_de_url(URL_OK) == _token(cuenta_id=CUENTA)


@pytest.mark.unit
def test_un_link_que_no_es_de_descarga_no_llega_a_la_api():
    """token_de_url revalida el destino: es la función que arma el pedido."""
    with pytest.raises(EdenorPdfNoDisponible, match="edenordigital.com"):
        token_de_url("https://evil.example.com/descarga_de_factura?token=x")


@pytest.mark.unit
def test_la_pagina_de_descarga_sin_token_falla_claro():
    with pytest.raises(EdenorPdfNoDisponible, match="token"):
        token_de_url("https://edenordigital.com/descarga_de_factura")


@pytest.mark.unit
def test_el_token_va_escapado_en_la_url_de_la_api():
    assert url_del_pdf("a.b+c/d").endswith("token=a.b%2Bc%2Fd")


# ──────────────────────────────────────────────
# La cuenta del token, antes de descargar
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_lee_la_cuenta_del_payload_del_jwt():
    assert cuenta_del_token(_token(cuenta_id=CUENTA, factura_id="525423006092")) == CUENTA


@pytest.mark.unit
def test_el_token_de_otra_cuenta_se_corta_antes_de_pedir_el_pdf():
    with pytest.raises(EdenorPdfNoDisponible, match="otra|9999"):
        verificar_cuenta(_token(cuenta_id="9999999999"), CUENTA)


@pytest.mark.unit
def test_la_cuenta_del_token_tolera_los_ceros_a_la_izquierda():
    verificar_cuenta(_token(cuenta_id="0" + CUENTA), CUENTA)  # no levanta


@pytest.mark.unit
@pytest.mark.parametrize("token", ["", "no-es-un-jwt", "a.###.c", _token(otra_cosa=1)])
def test_un_token_ilegible_no_bloquea_la_descarga(token):
    """El formato es de ellos y puede cambiar; la verificación que manda es la
    del PDF, así que acá alcanza con el warning."""
    assert cuenta_del_token(token) is None
    verificar_cuenta(token, CUENTA)  # no levanta


# ──────────────────────────────────────────────
# Lectura del total a pagar
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_lee_el_total_sin_espacios():
    """Así devuelve pdfplumber la portada real de Edenor."""
    assert totales_a_pagar("TOTALAPAGAR $ 14.574,69") == {14574.69}


@pytest.mark.unit
def test_el_total_con_recargo_no_se_toma_por_el_de_la_factura():
    texto = ("TOTALAPAGAR $ 14.574,69\n"
             "TOTALAPAGARCONRECARGO $ 14.633,82")
    assert totales_a_pagar(texto) == {14574.69}


# ──────────────────────────────────────────────
# Verificación contra el PDF real
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_el_pdf_real_pasa_la_verificacion():
    verificar_factura(_fixture("edenor.pdf").read_bytes(), CUENTA, MONTO_FIXTURE)


@pytest.mark.unit
def test_el_pdf_de_otra_cuenta_se_rechaza():
    pdf = _fixture("edenor.pdf").read_bytes()
    with pytest.raises(EdenorPdfNoDisponible, match="otro cliente"):
        verificar_factura(pdf, "9999999999", MONTO_FIXTURE)


@pytest.mark.unit
def test_el_pdf_de_otro_mes_se_rechaza_por_el_importe():
    """
    El caso que importa en Edenor: la cuenta coincide igual —es la misma todos
    los meses—, así que si el importe no se chequeara, la factura de julio
    pasaría por la de agosto sin que nadie se entere.
    """
    pdf = _fixture("edenor.pdf").read_bytes()
    with pytest.raises(EdenorPdfNoDisponible, match="otra factura"):
        verificar_factura(pdf, CUENTA, 14574.69)


@pytest.mark.unit
def test_el_total_con_recargo_del_pdf_real_tampoco_lo_da_por_bueno():
    pdf = _fixture("edenor.pdf").read_bytes()
    with pytest.raises(EdenorPdfNoDisponible, match="otra factura"):
        verificar_factura(pdf, CUENTA, MONTO_CON_RECARGO)


@pytest.mark.unit
def test_tolera_la_diferencia_de_un_centavo():
    verificar_factura(_fixture("edenor.pdf").read_bytes(), CUENTA, MONTO_FIXTURE + 0.01)


# ── portada rediseñada: se degrada, pero el importe sigue siendo obligatorio ──

@pytest.mark.unit
def test_sin_la_etiqueta_del_total_alcanza_con_que_el_importe_figure():
    with patch("bot.tools.edenor_pdf.texto_primera_pagina",
               return_value="Cuenta 5 255 064 586 Importe del mes $ 13.405,84"):
        verificar_factura(b"%PDF", CUENTA, MONTO_FIXTURE)


@pytest.mark.unit
def test_la_cuenta_sola_nunca_alcanza():
    """Es lo que separa a Edenor de AySA: la cuenta no distingue un mes de otro."""
    with patch("bot.tools.edenor_pdf.texto_primera_pagina",
               return_value="Cuenta 5 255 064 586 Importe del mes $ 99.999,99"):
        with pytest.raises(EdenorPdfNoDisponible, match="otra factura"):
            verificar_factura(b"%PDF", CUENTA, MONTO_FIXTURE)


@pytest.mark.unit
def test_un_pdf_sin_texto_no_se_da_por_bueno():
    with patch("bot.tools.edenor_pdf.texto_primera_pagina", return_value="  \n "):
        with pytest.raises(EdenorPdfNoDisponible, match="no pude leer texto"):
            verificar_factura(b"%PDF", CUENTA, MONTO_FIXTURE)
