"""
Descarga del PDF de la factura de AySA.

La cadena de redirecciones es scraping de un flujo no documentado, así que lo
que se protege acá es que falle ruidosamente: un salto fuera de los dominios de
AySA, una cadena que no termina, o un PDF que no habla de esta factura no
archivan nada.

El fixture real (`fixtures/facturas/aysa.pdf`) trae el número de cuenta y el
nombre, así que está en .gitignore: los tests que dependen de él se saltean
fuera de la máquina donde se guardó.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from bot.tools.aysa_pdf import (
    AysaPdfNoDisponible, resolver_url_pdf, texto_primera_pagina,
    totales_a_pagar, verificar_factura,
)

FIXTURES = Path(__file__).parent / "fixtures" / "facturas"

# Los datos de la factura de julio 2026, la del PDF de fixture.
LSP_FIXTURE = "0111B20261385"
MONTO_FIXTURE = 30562.17
MONTO_CON_RECARGO = 30955.40   # el del 2° vencimiento, en la misma portada

# La cadena real, tal cual la devuelve AySA hoy.
TRACKING = "https://customer27066g.musvc2.net/e/tr?q=TOKEN"
SAP_VIEJO = ("https://aysaovservicehubmfy5t4t2rj.br1.hana.ondemand.com"
             "/AysaOvServiceHub/api/v1/ov/facturadigital/obtenerFD?hash=H")
SAP_NUEVO = ("https://aysa-ov-service-hub-cf-prd.cfapps.br10.hana.ondemand.com"
             "/api/v1/ov/facturadigital/obtenerFD?hash=H")


def _fixture(nombre: str) -> Path:
    ruta = FIXTURES / nombre
    if not ruta.exists():
        pytest.skip(f"falta el fixture {nombre}")
    return ruta


class RespuestaFalsa:
    def __init__(self, status=200, location=None):
        self.status_code = status
        self.headers = {"Location": location} if location else {}

    def close(self):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class GetFalso:
    """requests.get de mentira: registra qué se pidió y devuelve lo encolado."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.pedidos = []

    def __call__(self, url, **kw):
        self.pedidos.append(url)
        assert kw["allow_redirects"] is False, "los saltos se caminan de a uno"
        return self.respuestas.pop(0) if self.respuestas else RespuestaFalsa()


# ──────────────────────────────────────────────
# resolver_url_pdf: la cadena de saltos
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_camina_los_dos_saltos_hasta_el_pdf():
    get = GetFalso(RespuestaFalsa(301, SAP_VIEJO), RespuestaFalsa(303, SAP_NUEVO),
                   RespuestaFalsa(200))
    with patch("requests.get", get):
        assert resolver_url_pdf(TRACKING) == SAP_NUEVO
    assert get.pedidos == [TRACKING, SAP_VIEJO, SAP_NUEVO]


@pytest.mark.unit
def test_un_location_relativo_se_resuelve_contra_el_salto_anterior():
    get = GetFalso(RespuestaFalsa(302, "/api/v1/ov/facturadigital/obtenerFD?hash=H"))
    with patch("requests.get", get):
        url = resolver_url_pdf(TRACKING)
    assert url == "https://customer27066g.musvc2.net/api/v1/ov/facturadigital/obtenerFD?hash=H"


@pytest.mark.unit
def test_el_host_se_valida_antes_de_pedir_nada():
    """
    El link lleva el token de la factura: si el destino no es de AySA, no se le
    pide el archivo NI se le muestra el token.
    """
    get = GetFalso()
    with patch("requests.get", get):
        with pytest.raises(AysaPdfNoDisponible, match="evil.example.com"):
            resolver_url_pdf("https://evil.example.com/factura.pdf")
    assert get.pedidos == []


@pytest.mark.unit
def test_un_salto_fuera_de_los_dominios_de_aysa_se_corta_ahi():
    """Un redirector abierto en el tracking no puede llevarnos a cualquier lado."""
    get = GetFalso(RespuestaFalsa(301, "https://evil.example.com/factura.pdf"))
    with patch("requests.get", get):
        with pytest.raises(AysaPdfNoDisponible, match="evil.example.com"):
            resolver_url_pdf(TRACKING)
    assert get.pedidos == [TRACKING]  # nunca se pidió el destino malicioso


@pytest.mark.unit
def test_no_se_conforma_con_un_dominio_parecido():
    get = GetFalso(RespuestaFalsa(301, "https://aysa.com.ar.evil.io/x.pdf"))
    with patch("requests.get", get):
        with pytest.raises(AysaPdfNoDisponible):
            resolver_url_pdf(TRACKING)


@pytest.mark.unit
def test_un_salto_a_http_pelado_se_rechaza():
    get = GetFalso(RespuestaFalsa(301, "http://oficinavirtual.web.aysa.com.ar/x.pdf"))
    with patch("requests.get", get):
        with pytest.raises(AysaPdfNoDisponible, match="https"):
            resolver_url_pdf(TRACKING)


@pytest.mark.unit
def test_una_cadena_que_no_termina_no_cuelga_al_poller():
    get = GetFalso(*[RespuestaFalsa(302, SAP_VIEJO) for _ in range(10)])
    with patch("requests.get", get):
        with pytest.raises(AysaPdfNoDisponible, match="saltos"):
            resolver_url_pdf(TRACKING)


@pytest.mark.unit
def test_un_error_http_no_pasa_por_url_valida():
    """Sin esto, un 500 devolvería la URL como si sirviera y el fallo saldría
    después, disfrazado de 'no es un PDF'."""
    with patch("requests.get", GetFalso(RespuestaFalsa(500))):
        with pytest.raises(RuntimeError, match="HTTP 500"):
            resolver_url_pdf(TRACKING)


# ──────────────────────────────────────────────
# Lectura del total a pagar
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_lee_el_total_sin_espacios_y_con_la_fecha_pegada():
    """Así devuelve pdfplumber la portada real de AySA."""
    texto = ("Vencimiento 10/09/2026 Totalapagar $31.356,27\n"
             "Totalapagarhastael10/09/2026 $31.356,27")
    assert totales_a_pagar(texto) == {31356.27}


@pytest.mark.unit
def test_el_total_con_recargo_no_se_toma_por_el_de_la_factura():
    """
    La portada trae también el importe del 2° vencimiento. Es el único número de
    la página que podría pasar por el total, así que se excluye explícitamente.
    """
    texto = ("Totalapagarhastael13/08/2026 $30.562,17\n"
             "Totalapagarconrecargohastael28/08/2026(2do.Vencimiento) $30.955,40")
    assert totales_a_pagar(texto) == {30562.17}


@pytest.mark.unit
def test_sin_la_etiqueta_no_inventa_ningun_total():
    assert totales_a_pagar("Deudaal 08/08/2026 $ 1.234,56") == set()


# ──────────────────────────────────────────────
# Verificación contra el PDF real
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_el_pdf_real_pasa_la_verificacion():
    pdf = _fixture("aysa.pdf").read_bytes()
    verificar_factura(pdf, LSP_FIXTURE, MONTO_FIXTURE)  # no levanta


@pytest.mark.unit
def test_las_dos_señales_estan_en_la_portada_real():
    """Si AySA rediseña y se pierde una, la verificación se degrada; que se
    pierdan las dos tiene que ser visible acá antes que en producción."""
    texto = texto_primera_pagina(_fixture("aysa.pdf").read_bytes())
    assert LSP_FIXTURE in texto.replace(" ", "")
    assert totales_a_pagar(texto) == {MONTO_FIXTURE}


@pytest.mark.unit
def test_el_pdf_de_otro_mes_se_rechaza_por_la_lsp():
    """El caso que importa: el PDF que llega no es el de la factura del mail."""
    pdf = _fixture("aysa.pdf").read_bytes()
    with pytest.raises(AysaPdfNoDisponible, match="otra factura"):
        verificar_factura(pdf, "0111B23729551", 31356.27)


@pytest.mark.unit
def test_si_la_lsp_coincide_pero_el_importe_no_avisa_del_importe():
    """
    Acá el PDF es el correcto: el que está mal es el monto que se leyó del mail.
    El mensaje tiene que mandarte a mirar eso y no la descarga.
    """
    pdf = _fixture("aysa.pdf").read_bytes()
    with pytest.raises(AysaPdfNoDisponible, match="revisá el importe registrado"):
        verificar_factura(pdf, LSP_FIXTURE, MONTO_CON_RECARGO)


@pytest.mark.unit
def test_tolera_la_diferencia_de_un_centavo():
    verificar_factura(_fixture("aysa.pdf").read_bytes(), LSP_FIXTURE, MONTO_FIXTURE + 0.01)


@pytest.mark.unit
def test_no_tolera_mas_que_eso():
    with pytest.raises(AysaPdfNoDisponible):
        verificar_factura(_fixture("aysa.pdf").read_bytes(), LSP_FIXTURE, MONTO_FIXTURE + 0.50)


# ── portada rediseñada: se degrada, no bloquea ─

@pytest.mark.unit
def test_sin_la_etiqueta_del_total_alcanza_con_la_lsp():
    with patch("bot.tools.aysa_pdf.texto_primera_pagina",
               return_value="LSP 0111B20261385 Importe $ 30.562,17"):
        verificar_factura(b"%PDF", LSP_FIXTURE, MONTO_FIXTURE)


@pytest.mark.unit
def test_sin_la_lsp_alcanza_con_el_total():
    with patch("bot.tools.aysa_pdf.texto_primera_pagina",
               return_value="Totalapagar $30.562,17"):
        verificar_factura(b"%PDF", None, MONTO_FIXTURE)


@pytest.mark.unit
def test_sin_ninguna_de_las_dos_no_se_archiva():
    with patch("bot.tools.aysa_pdf.texto_primera_pagina",
               return_value="Su factura de agua Importe $ 1.000,00"):
        with pytest.raises(AysaPdfNoDisponible, match="no pude verificar"):
            verificar_factura(b"%PDF", None, MONTO_FIXTURE)


@pytest.mark.unit
def test_un_pdf_sin_texto_no_se_da_por_bueno():
    """Si el endpoint devolviera un escaneado o una página de error, mejor avisar
    que archivar a ciegas."""
    with patch("bot.tools.aysa_pdf.texto_primera_pagina", return_value="  \n "):
        with pytest.raises(AysaPdfNoDisponible, match="no pude leer texto"):
            verificar_factura(b"%PDF", LSP_FIXTURE, MONTO_FIXTURE)
