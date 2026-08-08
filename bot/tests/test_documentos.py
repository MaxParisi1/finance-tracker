"""
Tests del ruteo de PDFs sueltos.

Los snippets son texto verbatim de los documentos reales de julio-agosto 2026.
Lo que se protege: que un archivo nunca se archive bajo el servicio equivocado.
Ante cualquier ambigüedad el sistema tiene que preguntar, no elegir.
"""

from datetime import date
from unittest.mock import patch

import pytest

from bot.tools.documentos import (
    TIPO_COMPROBANTE, TIPO_FACTURA, DocumentoNoIdentificado, aplanar,
    detectar_tipo, identificar_documento, identificar_servicio,
)

# ── Identificadores tal como quedan en servicios_identificadores ──────────────

def _ident(slug, tipo, valor):
    return {"tipo": tipo, "valor": valor,
            "servicio": {"id": f"srv-{slug}", "slug": slug, "nombre": slug, "activo": True}}


IDENTIFICADORES = [
    _ident("edenor", "cuenta", "5255064586"),
    _ident("metrogas", "cliente", "40000507673"),
    _ident("aysa", "cuenta", "1929557"),
    _ident("personal", "referente", "8100682932410002"),
    _ident("consorcio_gallo", "cbu", "70306020000004521499"),
    _ident("consorcio_gallo", "cuit", "30553713605"),
]

# ── Snippets reales ──────────────────────────────────────────────────────────

FACTURA_EDENOR = """Empresa Distribuidora y Comercializadora Norte S. A. LiquidacióndeServicioPúblico
Cuenta 5 255 064 586
TERESARMUSANTE
Hastael05/08/2026
TOTALAPAGAR $ 13.405,84
2°.Vencimientoconrecargohastael 10/08/2026 $13.460,24"""

COMPROBANTE_EDENOR = """Comprobante de pago
Viernes, 31 de julio de 2026, 20:15.
$ 13.40584
Edenor
N.° de operación de Mercado Pago 171469753516
Número de cuenta 5255064586
Vencimiento 05/ago/2026
Persona que pagó Maximo Parisi
Medio de pago Dinero disponible"""

COMPROBANTE_AYSA = """Comprobante de pago
$ 30.56217
Aysa
Cuenta de servicios 1929557
Vencimiento 13/ago/2026
Medio de pago Dinero disponible"""

COMPROBANTE_TRANSFERENCIA = """06/08/2026 22:08:00
Transferiste a CONS. PROP. GALLO 1636 AL 58
$ 258.198,55
Número de referencia 30179716018260806
Cuenta de origen CA$ 99-629107/7
CBU/CVU del destinatario 0070306020000004521499
CUIT destinatario 30553713605
Motivo y concepto EXPENSAS Expensas 3D"""

COMPROBANTE_PERSONAL = """Fecha: 31/07/2026 - 20:22:35 h
Pagaste $67.894,40
Empresa Personal
Referente de Pago 8100682932410002
Forma de pago Saldo Personal Pay
Nro. de operación Pay 2922128404"""

FACTURA_METROGAS = """LIQUIDACION DE SERVICIOS PÚBLICOS B-0064-70725805
MetroGAS S.A.
Maximo Parisi
Número de cliente 40000507673
Fecha de emisión 03/08/2026"""


# ──────────────────────────────────────────────
# aplanar
# ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("crudo", ["5 255 064 586", "5255064586", "5.255.064.586", "5-255-064-586"])
def test_aplanar_colapsa_todas_las_formas_del_mismo_numero(crudo):
    """Edenor escribe la cuenta espaciada en el PDF y junta en el comprobante."""
    assert "5255064586" in aplanar(crudo)


# ──────────────────────────────────────────────
# Ruteo por identificador
# ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("texto, slug", [
    (FACTURA_EDENOR, "edenor"),
    (COMPROBANTE_EDENOR, "edenor"),
    (COMPROBANTE_AYSA, "aysa"),
    (COMPROBANTE_TRANSFERENCIA, "consorcio_gallo"),
    (COMPROBANTE_PERSONAL, "personal"),
    (FACTURA_METROGAS, "metrogas"),
])
def test_rutea_por_identificador(texto, slug):
    assert identificar_servicio(texto, IDENTIFICADORES)["servicio"]["slug"] == slug


@pytest.mark.unit
def test_rutea_igual_cambiando_la_plataforma_de_pago():
    """
    La garantía central: si un mes pagás AySA por Rapipago en vez de Mercado
    Pago, el ruteo no se rompe, porque la clave es tu cuenta de AySA y no el
    formato del emisor.
    """
    rapipago = """*** RAPIPAGO ***
    PAGO DE SERVICIOS
    AYSA  Cuenta 1929557
    IMPORTE $ 30.562,17
    Comprobante de pago Nro 998877"""
    assert identificar_servicio(rapipago, IDENTIFICADORES)["servicio"]["slug"] == "aysa"


@pytest.mark.unit
def test_encuentra_el_identificador_dentro_de_un_codigo_de_barras():
    """El comprobante de AySA embebe la cuenta en la línea del código de barras."""
    texto = "H6E AYSA MP\n1929557 $$$$$$$$30562,17\n304111202613852608130000305621722000"
    assert identificar_servicio(texto, IDENTIFICADORES)["servicio"]["slug"] == "aysa"


@pytest.mark.unit
def test_documento_desconocido_no_se_rutea():
    with pytest.raises(DocumentoNoIdentificado, match="ningún identificador"):
        identificar_servicio("Factura de Netflix por $9.999,00", IDENTIFICADORES)


@pytest.mark.unit
def test_texto_vacio_falla_claro():
    with pytest.raises(DocumentoNoIdentificado, match="texto"):
        identificar_servicio("", IDENTIFICADORES)


@pytest.mark.unit
def test_si_coinciden_dos_servicios_pregunta_en_vez_de_elegir():
    """Archivar bajo el servicio equivocado es peor que molestar al usuario."""
    mezcla = "Cuenta 5255064586 y tambien cliente 40000507673"
    with pytest.raises(DocumentoNoIdentificado, match="varios servicios"):
        identificar_servicio(mezcla, IDENTIFICADORES)


@pytest.mark.unit
def test_dos_identificadores_del_mismo_servicio_no_son_ambiguos():
    """La transferencia trae CBU y CUIT del consorcio: es un solo servicio."""
    ident = identificar_servicio(COMPROBANTE_TRANSFERENCIA, IDENTIFICADORES)
    assert ident["servicio"]["slug"] == "consorcio_gallo"
    assert ident["valor"] == "70306020000004521499"  # gana el más largo


# ──────────────────────────────────────────────
# Tipo de documento
# ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("texto, tipo", [
    (FACTURA_EDENOR, TIPO_FACTURA),
    (FACTURA_METROGAS, TIPO_FACTURA),
    (COMPROBANTE_EDENOR, TIPO_COMPROBANTE),
    (COMPROBANTE_AYSA, TIPO_COMPROBANTE),
    (COMPROBANTE_TRANSFERENCIA, TIPO_COMPROBANTE),
    (COMPROBANTE_PERSONAL, TIPO_COMPROBANTE),
])
def test_detecta_el_tipo(texto, tipo):
    assert detectar_tipo(texto) == tipo


@pytest.mark.unit
def test_el_nombre_del_archivo_no_influye():
    """
    El PDF que vino nombrado '_factura' era en realidad un comprobante de pago.
    El tipo se decide por el contenido, siempre.
    """
    assert detectar_tipo(COMPROBANTE_PERSONAL) == TIPO_COMPROBANTE


@pytest.mark.unit
def test_documento_sin_marcas_pregunta():
    with pytest.raises(DocumentoNoIdentificado, match="factura o comprobante"):
        detectar_tipo("Hola, esto es una carta cualquiera.")


# ──────────────────────────────────────────────
# identificar_documento (integración de las piezas)
# ──────────────────────────────────────────────

def _con_pdf(texto):
    return [
        patch("bot.tools.documentos.extraer_texto_pdf", return_value=texto),
        patch("bot.tools.documentos.queries.listar_identificadores_servicios",
              return_value=IDENTIFICADORES),
    ]


def _identificar(texto):
    ps = _con_pdf(texto)
    for p in ps:
        p.start()
    try:
        return identificar_documento(b"%PDF-fake")
    finally:
        for p in ps:
            p.stop()


@pytest.mark.unit
def test_comprobante_de_mercado_pago_completo():
    doc = _identificar(COMPROBANTE_EDENOR)
    assert doc.servicio["slug"] == "edenor"
    assert doc.tipo == TIPO_COMPROBANTE
    # $ 13.40584 → Mercado Pago pierde la coma; los 2 últimos son centavos.
    assert doc.monto == pytest.approx(13405.84)
    assert doc.fecha == date(2026, 8, 5)


@pytest.mark.unit
def test_transferencia_de_expensas_completa():
    doc = _identificar(COMPROBANTE_TRANSFERENCIA)
    assert doc.servicio["slug"] == "consorcio_gallo"
    assert doc.tipo == TIPO_COMPROBANTE
    assert doc.monto == pytest.approx(258198.55)


@pytest.mark.unit
def test_factura_de_edenor_toma_el_primer_monto_no_el_recargado():
    doc = _identificar(FACTURA_EDENOR)
    assert doc.tipo == TIPO_FACTURA
    assert doc.monto == pytest.approx(13405.84)


@pytest.mark.unit
def test_pdf_escaneado_sin_texto_pide_otra_via():
    with patch("bot.tools.documentos.extraer_texto_pdf", return_value="   "):
        with pytest.raises(DocumentoNoIdentificado, match="escaneo"):
            identificar_documento(b"%PDF-fake")


@pytest.mark.unit
def test_documento_sin_monto_no_inventa_uno():
    """Sin monto legible, el campo queda en None y el bot pregunta."""
    doc = _identificar("Comprobante de pago\nCuenta de servicios 1929557\nsin importes")
    assert doc.monto is None
    assert doc.servicio["slug"] == "aysa"


# ──────────────────────────────────────────────
# Fechas: no agarrar la basura del pie de página
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_ignora_el_inicio_de_actividades_de_la_empresa():
    """
    Bug real: la factura de AySA arrancaba dando 2006-03-21 y la de MetroGAS
    2092-12-28, porque la primera fecha del PDF es el 'Inicio de actividades'.
    """
    texto = """AguaySaneamientosArgentinosS.A.
    CUITNº30-70956507-5
    Iniciodeactividades: 21/03/2006
    Cuentade Servicios 1929557
    Vencimiento 13/08/2026 Totalapagar $30.562,17"""
    doc = _identificar(texto)
    assert doc.fecha == date(2026, 8, 13)


@pytest.mark.unit
def test_fecha_de_dos_digitos_del_siglo_pasado_se_descarta():
    """MetroGAS: 'Inicio Actividades: 28/12/92' se expandía a 2092."""
    texto = """LIQUIDACION DE SERVICIOS PÚBLICOS
    Inicio Actividades: 28/12/92
    Número de cliente 40000507673
    Vencimiento 14/08/2026"""
    assert _identificar(texto).fecha == date(2026, 8, 14)


@pytest.mark.unit
def test_sin_fecha_plausible_devuelve_none():
    texto = "Comprobante de pago\nCuenta de servicios 1929557\nemitido el 01/01/1990"
    assert _identificar(texto).fecha is None


@pytest.mark.unit
def test_prefiere_la_fecha_etiquetada_sobre_la_primera_del_texto():
    texto = """Comprobante de pago
    Impreso el 02/08/2026
    Número de cuenta 5255064586
    Vencimiento 05/08/2026"""
    assert _identificar(texto).fecha == date(2026, 8, 5)


# ──────────────────────────────────────────────
# Límite conocido: centavos partidos por el renderer
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_centavos_en_linea_aparte_quedan_fuera_del_monto():
    """
    Límite conocido y aceptado. El comprobante de Personal Pay dibuja los
    centavos en tipografía chica y pdfplumber los emite en OTRA línea, antes del
    monto. Se lee $67.894 en vez de $67.894,40.

    No se corrige adivinando: la conciliación compara contra el monto de la
    factura abierta con tolerancia y toma ese como autoritativo.
    """
    texto = """Fecha: 31/07/2026 - 20:22:35 h
    40
    Pagaste $67.894
    Referente de Pago 8100682932410002
    Forma de pago Saldo Personal Pay"""
    doc = _identificar(texto)
    assert doc.monto == pytest.approx(67894.00)
    assert abs(doc.monto - 67894.40) < 1.0  # dentro de la tolerancia de conciliación
