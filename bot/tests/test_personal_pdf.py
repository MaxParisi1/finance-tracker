"""
Descarga del PDF de la factura de Personal.

Los dos saltos son scraping de un flujo no documentado, así que lo que se
protege acá es que falle ruidosamente: sin salto, con salto a otro dominio, o
con un PDF que no habla del monto del mail, no se archiva nada.

Los fixtures reales (`fixtures/facturas/`) traen el número de cuenta y el
nombre, así que están en .gitignore: los tests que dependen de ellos se saltean
fuera de la máquina donde se guardaron.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from bot.tools.personal_pdf import (
    HOST_PERSONAL, PersonalPdfNoDisponible, extraer_url_pdf, importes,
    texto_primera_pagina, total_a_pagar, verificar_monto,
)

FIXTURES = Path(__file__).parent / "fixtures" / "facturas"

# El monto y el vencimiento de la factura de agosto 2026, la del PDF de fixture.
MONTO_FIXTURE = 72711.49


def _fixture(nombre: str) -> Path:
    ruta = FIXTURES / nombre
    if not ruta.exists():
        pytest.skip(f"falta el fixture {nombre}")
    return ruta


def _html_intermedio(destino: str) -> str:
    """Reproduce la estructura del HTML real: un cartel y el salto por JS."""
    return f"""
    <html><body><h1>Tu Factura</h1><p>Descargando...</p>
    <script>
        let redirected = false;
        function doRedirect() {{
        if (!redirected) {{
            redirected = true;
            location.replace("{destino}");
            }}
        }}
        setTimeout(doRedirect, 5000);
    </script>
    </body></html>
    """


# ──────────────────────────────────────────────
# extraer_url_pdf
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_saca_la_url_del_salto():
    destino = f"https://{HOST_PERSONAL}/facdigital-web/ConsultaPersonal?nroComprobante=ABC%3d%3d"
    assert extraer_url_pdf(_html_intermedio(destino)) == destino


@pytest.mark.unit
def test_desescapa_las_entidades_html():
    destino = f"https://{HOST_PERSONAL}/facdigital-web/ConsultaPersonal?a=1&amp;b=2"
    assert extraer_url_pdf(_html_intermedio(destino)).endswith("?a=1&b=2")


@pytest.mark.unit
def test_sin_salto_falla_con_mensaje_accionable():
    with pytest.raises(PersonalPdfNoDisponible, match="location.replace"):
        extraer_url_pdf("<html><body>Ingresá con tu usuario</body></html>")


@pytest.mark.unit
@pytest.mark.parametrize("html", ["", None])
def test_html_vacio_no_revienta_por_otro_lado(html):
    with pytest.raises(PersonalPdfNoDisponible):
        extraer_url_pdf(html)


@pytest.mark.unit
def test_un_salto_fuera_de_personal_se_rechaza():
    """Sin esta guarda, alterar el HTML intermedio bastaría para colgar de tu
    factura un archivo de cualquier otro lado."""
    malicioso = _html_intermedio("https://evil.example.com/factura.pdf")
    with pytest.raises(PersonalPdfNoDisponible, match="evil.example.com"):
        extraer_url_pdf(malicioso)


@pytest.mark.unit
def test_no_se_conforma_con_un_subdominio_parecido():
    falso = _html_intermedio("https://tufactura.personal.com.ar.evil.io/x.pdf")
    with pytest.raises(PersonalPdfNoDisponible):
        extraer_url_pdf(falso)


@pytest.mark.unit
def test_html_real_de_la_pagina_intermedia():
    html = _fixture("personal_descarga.html").read_text(encoding="utf-8", errors="replace")
    url = extraer_url_pdf(html)
    assert url.startswith(f"https://{HOST_PERSONAL}/facdigital-web/ConsultaPersonal?")
    assert "nroComprobante=" in url


# ──────────────────────────────────────────────
# Verificación del monto
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_lee_el_total_a_pagar_sin_espacios():
    """Así devuelve pdfplumber la portada real de Personal."""
    assert total_a_pagar("TOTALDESERVICIOSDELMES $72.711,49\nTOTALAPAGAR $72.711,49") == 72711.49


@pytest.mark.unit
def test_lee_el_total_a_pagar_con_espacios():
    assert total_a_pagar("TOTAL A PAGAR: $ 1.234,56") == 1234.56


@pytest.mark.unit
def test_sin_la_etiqueta_devuelve_none():
    assert total_a_pagar("Tu saldo total es de $ 72.711,49") is None


@pytest.mark.unit
def test_importes_ignora_el_signo_y_deduplica():
    assert importes("SaldoAnterior $67.894,40\nPagosal13/08 $-67.894,40") == {67894.40}


# ── contra el PDF real ────────────────────────

@pytest.mark.unit
def test_el_pdf_real_pasa_la_verificacion():
    pdf = _fixture("personal.pdf").read_bytes()
    verificar_monto(pdf, MONTO_FIXTURE)  # no levanta


@pytest.mark.unit
def test_el_saldo_anterior_no_alcanza_para_dar_por_bueno_el_pdf():
    """
    El caso que motivó anclar la verificación: la portada de agosto también trae
    el total de julio ($67.894,40) como SaldoAnterior. Con un chequeo laxo, el
    PDF de agosto pasaría por el de julio.
    """
    pdf = _fixture("personal.pdf").read_bytes()
    assert 67894.40 in importes(texto_primera_pagina(pdf))
    with pytest.raises(PersonalPdfNoDisponible, match="TOTAL A PAGAR"):
        verificar_monto(pdf, 67894.40)


@pytest.mark.unit
def test_tolera_la_diferencia_de_un_centavo():
    pdf = _fixture("personal.pdf").read_bytes()
    verificar_monto(pdf, MONTO_FIXTURE + 0.01)


@pytest.mark.unit
def test_no_tolera_mas_que_eso():
    pdf = _fixture("personal.pdf").read_bytes()
    with pytest.raises(PersonalPdfNoDisponible):
        verificar_monto(pdf, MONTO_FIXTURE + 0.50)


# ── portada rediseñada: se degrada, no bloquea ─

@pytest.mark.unit
def test_sin_total_a_pagar_acepta_si_el_monto_figura_en_algun_lado():
    with patch("bot.tools.personal_pdf.texto_primera_pagina",
               return_value="Importe del mes $ 1.000,00"):
        verificar_monto(b"%PDF", 1000.00)


@pytest.mark.unit
def test_sin_total_a_pagar_rechaza_si_el_monto_no_esta():
    with patch("bot.tools.personal_pdf.texto_primera_pagina",
               return_value="Importe del mes $ 1.000,00"):
        with pytest.raises(PersonalPdfNoDisponible, match="otra factura"):
            verificar_monto(b"%PDF", 2500.00)


@pytest.mark.unit
def test_un_pdf_sin_importes_legibles_no_se_da_por_bueno():
    """Si Personal pasara a un PDF escaneado, mejor avisar que archivar a ciegas."""
    with patch("bot.tools.personal_pdf.texto_primera_pagina", return_value=""):
        with pytest.raises(PersonalPdfNoDisponible, match="ningún importe"):
            verificar_monto(b"%PDF", 1000.0)
