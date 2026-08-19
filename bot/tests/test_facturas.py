"""
Tests de los parsers de facturas contra los mails REALES de julio-agosto 2026.

Los .eml de bot/tests/fixtures/emails/ son los mensajes tal cual llegaron. Si un
proveedor cambia el template, estos tests se caen antes de que se cargue un dato
mal en la base.
"""

import email as email_lib
import html as html_lib
import json
import re
from datetime import date
from email import policy
from pathlib import Path

import pytest

from bot.tools.expensas_pdf import (
    ExpensasNoParseable, parsear_fila_unidad, unir_tokens_partidos,
)
from bot.tools.facturas import (
    FacturaIncompleta, FacturaIrrelevante, FacturaNoParseable, parsear_email,
    servicio_de_remitente,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ──────────────────────────────────────────────
# Carga de fixtures (replica lo que hace gmail_reader con un mensaje real)
# ──────────────────────────────────────────────

def _a_texto(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    html = re.sub(r"</?(tr|td|br|p|div|table|span|li|h\d)[^>]*>", "\n", html, flags=re.I)
    texto = html_lib.unescape(re.sub(r"<[^>]+>", " ", html))
    texto = re.sub(r"[ \t\xa0]+", " ", texto)
    return re.sub(r"\n\s*\n+", "\n", texto).strip()


def cargar(nombre: str) -> dict:
    ruta = FIXTURES / "emails" / f"{nombre}.eml"
    msg = email_lib.message_from_string(ruta.read_text(encoding="utf-8", errors="replace"),
                                        policy=policy.default)
    html = plano = ""
    for parte in msg.walk():
        cargatxt = parte.get_payload(decode=True)
        if not cargatxt:
            continue
        texto = cargatxt.decode(parte.get_content_charset() or "utf-8", errors="replace")
        if parte.get_content_type() == "text/html" and not html:
            html = texto
        elif parte.get_content_type() == "text/plain" and not plano:
            plano = texto
    return {
        "from": msg.get("From", ""),
        "subject": msg.get("Subject", ""),
        "html": html,
        "texto": _a_texto(html) if html else plano,
    }


# ──────────────────────────────────────────────
# Ruteo por remitente
# ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("remitente, esperado", [
    ("Edenor <facturadigital@edenor.com>", "edenor"),
    ("MetroGAS Factura Digital <facturadigital@metrogas.com.ar>", "metrogas"),
    ("AySA Digital <avisos@aysadigital.com.ar>", "aysa"),
    ('"Tu Factura Personal" <facturacion@email.personal.com.ar>', "personal"),
    ("Torre Lublin <notificacion@simplesolutions.com.ar>", "consorcio_gallo"),
    ("Alguien <spam@otracosa.com>", None),
    ("", None),
])
def test_servicio_de_remitente(remitente, esperado):
    assert servicio_de_remitente(remitente) == esperado


@pytest.mark.unit
def test_dominio_parecido_no_matchea():
    """'edenor.com.falso.com' no debe rutear a Edenor."""
    assert servicio_de_remitente("x@edenor.com.falso.com") is None


# ──────────────────────────────────────────────
# Parseo de cada factura, contra el mail real
# ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("fixture, servicio, identificador, monto, vencimiento", [
    ("edenor",   "edenor",   "5255064586",       13405.84, date(2026, 8, 5)),
    ("metrogas", "metrogas", "40000507673",       5266.75, date(2026, 8, 14)),
    ("aysa",     "aysa",     "1929557",          30562.17, date(2026, 8, 13)),
    ("personal", "personal", "8100682932410002", 67894.40, date(2026, 8, 4)),
])
def test_parsear_factura(fixture, servicio, identificador, monto, vencimiento):
    f = parsear_email(cargar(fixture))
    assert f.servicio == servicio
    assert f.identificador == identificador
    assert f.monto == pytest.approx(monto)
    assert f.vencimiento == vencimiento


@pytest.mark.unit
def test_edenor_toma_el_primer_vencimiento_no_el_recargado():
    """El mail lista 05/08 a $13.405,84 y un 2° vencimiento a $13.460,24."""
    f = parsear_email(cargar("edenor"))
    assert f.monto == pytest.approx(13405.84)
    assert f.monto != pytest.approx(13460.24)


@pytest.mark.unit
def test_metrogas_extrae_periodo_de_liquidacion():
    f = parsear_email(cargar("metrogas"))
    assert f.periodo_desde == date(2026, 6, 4)
    assert f.periodo_hasta == date(2026, 7, 3)


@pytest.mark.unit
def test_aysa_extrae_numero_de_factura():
    """El N° de LSP aparece igual en el mail y en el PDF: es el join exacto."""
    assert parsear_email(cargar("aysa")).nro_factura == "0111B20261385"


@pytest.mark.unit
def test_aysa_normaliza_ceros_a_la_izquierda():
    """El mail dice 000001929557 y el PDF 1929557: deben normalizar al mismo id."""
    assert parsear_email(cargar("aysa")).identificador == "1929557"


@pytest.mark.unit
def test_expensas_devuelve_los_links_al_pdf():
    """El mail de expensas no trae monto: señaliza que hay que bajar el PDF."""
    with pytest.raises(FacturaIncompleta) as exc:
        parsear_email(cargar("consorcio_gallo"))
    urls = exc.value.pdf_urls
    assert len(urls) == 2
    assert all(u.startswith("https://simplesolutionscloud.s3.") for u in urls)


@pytest.mark.unit
def test_remitente_desconocido_falla_ruidosamente():
    """Nunca adivinar: un remitente no registrado es un error explícito."""
    with pytest.raises(FacturaNoParseable):
        parsear_email({"from": "x@desconocido.com", "subject": "", "texto": "", "html": ""})


@pytest.mark.unit
def test_formato_cambiado_falla_en_vez_de_inventar():
    """Si Edenor rediseña el mail, el parser tiene que romper, no devolver basura."""
    roto = cargar("edenor")
    roto["texto"] = "Hola, tu factura ya está disponible. Saludos."
    with pytest.raises(FacturaNoParseable):
        parsear_email(roto)


# ──────────────────────────────────────────────
# Expensas: fila de la unidad funcional
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_unir_tokens_partidos():
    """El PDF parte '258.198,55' en '2' + '58.198,55' con ~3pt de separación."""
    palabras = [
        {"text": "2",         "x0": 955.2, "x1": 958.2},
        {"text": "58.198,55", "x0": 958.5, "x1": 1000.0},
    ]
    assert unir_tokens_partidos(palabras) == ["258.198,55"]


@pytest.mark.unit
def test_tokens_separados_no_se_unen():
    """Dos columnas distintas están a más de 20pt: no deben fusionarse."""
    palabras = [
        {"text": "9.200,00", "x0": 847.9, "x1": 890.0},
        {"text": "0,01",     "x0": 925.4, "x1": 940.0},
    ]
    assert unir_tokens_partidos(palabras) == ["9.200,00", "0,01"]


@pytest.mark.unit
def test_fila_uf255_da_el_total_correcto():
    """Verificado contra el comprobante de transferencia al consorcio."""
    fila = json.loads((FIXTURES / "expensas_uf255_fila.json").read_text(encoding="utf-8"))
    assert parsear_fila_unidad(fila, "255") == pytest.approx(258198.55)


@pytest.mark.unit
def test_fila_de_otra_unidad_es_rechazada():
    fila = json.loads((FIXTURES / "expensas_uf255_fila.json").read_text(encoding="utf-8"))
    with pytest.raises(ExpensasNoParseable):
        parsear_fila_unidad(fila, "306")


@pytest.mark.unit
def test_total_que_no_cierra_es_rechazado():
    """Si la aritmética no da, el parser no debe devolver un número dudoso."""
    fila = [
        {"text": "255",       "x0": 16.3,  "x1": 30.0},
        {"text": "100,00",    "x0": 100.0, "x1": 140.0},
        {"text": "200,00",    "x0": 200.0, "x1": 240.0},
        {"text": "999.999,99", "x0": 300.0, "x1": 360.0},
    ]
    with pytest.raises(ExpensasNoParseable):
        parsear_fila_unidad(fila, "255")


# ──────────────────────────────────────────────
# Mails reenviados desde otra casilla
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_reenvio_automatico_de_gmail_preserva_el_ruteo():
    """El reenvío automático mantiene el From: original: no cambia nada."""
    email = cargar("edenor")
    assert parsear_email(email).servicio == "edenor"


@pytest.mark.unit
def test_remitente_alternativo_rescata_el_ruteo():
    """Si el From: quedó reescrito, se busca el emisor en Reply-To y afines."""
    email = cargar("edenor")
    email["from"] = "Mi Otra Casilla <yo@gmail.com>"
    email["remitentes_alternativos"] = ["facturadigital@edenor.com"]
    assert parsear_email(email).servicio == "edenor"


@pytest.mark.unit
def test_sin_ningun_remitente_conocido_falla_con_ese_mensaje():
    """El mensaje exacto importa: el poller lo usa para decidir el fallback."""
    email = cargar("edenor")
    email["from"] = "yo@gmail.com"
    with pytest.raises(FacturaNoParseable, match="remitente no registrado"):
        parsear_email(email)


@pytest.mark.unit
def test_slug_explicito_saltea_el_ruteo_por_remitente():
    """Vía que usa el poller cuando identifica el servicio por número de cuenta."""
    email = cargar("edenor")
    email["from"] = "desconocido@gmail.com"
    assert parsear_email(email, slug="edenor").monto == pytest.approx(13405.84)


@pytest.mark.unit
def test_slug_inexistente_falla_claro():
    with pytest.raises(FacturaNoParseable, match="no hay parser"):
        parsear_email(cargar("edenor"), slug="inventado")


@pytest.mark.unit
def test_personal_tolera_el_prefijo_fwd_en_el_asunto():
    """Personal parsea desde el asunto, y el reenvío le antepone 'Fwd:'."""
    email = cargar("personal")
    email["subject"] = "Fwd: " + email["subject"]
    f = parsear_email(email)
    assert f.monto == pytest.approx(67894.40)
    assert f.vencimiento == date(2026, 8, 4)


# ──────────────────────────────────────────────
# Ruido del mismo remitente (promos, avisos)
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_la_promo_de_personal_no_se_confunde_con_una_factura():
    """
    Personal manda promos desde facturacion@email.personal.com.ar, el mismo
    remitente que la factura. Sin esta distinción cada promo sería una falsa
    alarma por Telegram — y las falsas alarmas hacen que dejes de leer las reales.
    """
    with pytest.raises(FacturaIrrelevante):
        parsear_email(cargar("personal_promo"))


@pytest.mark.unit
def test_la_promo_trae_montos_señuelo_que_no_deben_tomarse():
    """El cuerpo dice $4.000, $2.000 y $6.000: ninguno es una factura."""
    promo = cargar("personal_promo")
    assert "6.000" in promo["subject"] or "6.000" in promo["texto"]
    with pytest.raises(FacturaIrrelevante):
        parsear_email(promo)


@pytest.mark.unit
def test_la_factura_real_de_personal_sigue_pasando():
    """La contracara: el marcador no puede descartar la factura verdadera."""
    assert parsear_email(cargar("personal")).monto == pytest.approx(67894.40)


@pytest.mark.unit
@pytest.mark.parametrize("fixture", ["edenor", "metrogas", "aysa"])
def test_ningun_aviso_real_queda_descartado_por_los_marcadores(fixture):
    """Un falso negativo descartaría una factura en silencio: el error caro."""
    assert parsear_email(cargar(fixture)) is not None


@pytest.mark.unit
def test_expensas_sigue_señalando_que_hay_que_bajar_el_pdf():
    with pytest.raises(FacturaIncompleta):
        parsear_email(cargar("consorcio_gallo"))


@pytest.mark.unit
def test_mail_generico_de_un_remitente_conocido_se_descarta():
    generico = {"from": "Edenor <facturadigital@edenor.com>",
                "subject": "Cortes programados en tu zona",
                "texto": "Te informamos que habrá un corte el martes.", "html": ""}
    with pytest.raises(FacturaIrrelevante):
        parsear_email(generico)


@pytest.mark.unit
def test_ante_la_duda_se_procesa_y_falla_ruidosamente():
    """
    Criterio: si aparece un marcador pero el formato cambió, tiene que ser
    FacturaNoParseable (alerta), no FacturaIrrelevante (silencio).
    """
    ambiguo = {"from": "Edenor <facturadigital@edenor.com>",
               "subject": "Novedades", "texto": "TOTAL A PAGAR proximamente", "html": ""}
    with pytest.raises(FacturaNoParseable):
        parsear_email(ambiguo)


@pytest.mark.unit
def test_aviso_del_consorcio_no_es_factura():
    """
    Regresión: el logo del mail del consorcio vive en el MISMO bucket S3 que los
    PDFs de expensas, así que el marcador por substring daba positivo en cualquier
    aviso (ascensor, cortes de agua). El mail entraba al parser, no encontraba
    ningún href y alertaba cada 15 minutos como si el formato se hubiera roto.

    Fixture real: "Aviso: Ascensor de servicio" — trae el logo del bucket y ni un
    solo href a un PDF.
    """
    with pytest.raises(FacturaIrrelevante):
        parsear_email(cargar("consorcio_gallo_aviso"))


@pytest.mark.unit
def test_expensas_reales_siguen_pasando_el_filtro():
    """La contracara: el mail de expensas de verdad no puede quedar afuera."""
    with pytest.raises(FacturaIncompleta) as exc:
        parsear_email(cargar("consorcio_gallo"))
    assert exc.value.pdf_urls, "tienen que salir los links a los PDFs"
