"""
Tests del poller de facturas.

El invariante que se protege: un mail SOLO se marca como leído si quedó
resuelto. Si algo falla, el mail sigue sin leer y llega un aviso — así ninguna
factura se pierde en silencio, que es el modo de falla más caro de todos.
"""

import asyncio
import email as email_lib
from dataclasses import replace
from datetime import date
from email import policy
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.facturas_poller import (
    descargar_factura_aysa, descargar_factura_edenor, descargar_factura_personal,
    descargar_factura_consorcio, descargar_pdf, pdf_de_factura, poll_facturas_once,
    procesar_email_factura, resolver_expensas,
)
from bot.tools.alertas import resetear_dedup
from bot.tools.expensas_pdf import ExpensasNoParseable, FilaUnidad
from bot.tools.facturas import FacturaIncompleta, FacturaNoParseable, FacturaParseada
from bot.tools.facturas_service import (
    FacturaSospechosa, ResultadoRegistro, ServicioDesconocido,
)

MAIL = {"id": "msg-1", "from": "Edenor <facturadigital@edenor.com>",
        "subject": "Tu factura esta disponible", "body": "cuerpo", "html": "<p>cuerpo</p>"}

PARSEADA = FacturaParseada(servicio="edenor", identificador="5255064586",
                           monto=13405.84, vencimiento=date(2026, 8, 5))

SERVICIO = {"id": "srv-edenor", "slug": "edenor", "nombre": "Edenor"}


def resultado(ya_existia=False, factura_id="fac-1", servicio=SERVICIO):
    return ResultadoRegistro(factura={"id": factura_id}, ya_existia=ya_existia,
                             servicio=servicio)


class BotFalso:
    def __init__(self):
        self.mensajes = []

    async def send_message(self, **kw):
        self.mensajes.append(kw)


@pytest.fixture(autouse=True)
def _limpiar():
    resetear_dedup()
    yield
    resetear_dedup()


def correr(coro):
    return asyncio.run(coro)


def _patches(parsear=None, registrar=None, marcar=None):
    return [
        patch("bot.facturas_poller.parsear_facturas",
              **({"side_effect": parsear} if isinstance(parsear, Exception)
                 else {"return_value": parsear if isinstance(parsear, tuple)
                       else (parsear or PARSEADA,)})),
        patch("bot.facturas_poller.registrar_factura",
              **({"side_effect": registrar} if isinstance(registrar, (Exception, list))
                 else {"return_value": registrar or resultado()})),
        patch("bot.facturas_poller.mark_as_read",
              **({"side_effect": marcar} if isinstance(marcar, Exception) else {})),
    ]


class Ctx:
    def __init__(self, **kw):
        self._p = _patches(**kw)

    def __enter__(self):
        self.parsear, self.registrar, self.marcar = [p.start() for p in self._p]
        return self

    def __exit__(self, *a):
        for p in self._p:
            p.stop()


# ──────────────────────────────────────────────
# Camino feliz
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_factura_nueva_se_registra_marca_leido_y_notifica():
    bot = BotFalso()
    with Ctx() as ctx:
        assert correr(procesar_email_factura(bot, 1, MAIL)) is True

    ctx.registrar.assert_called_once()
    assert ctx.registrar.call_args[0][1] == "msg-1"  # idempotencia por message id
    ctx.marcar.assert_called_once_with("msg-1")
    assert "$13.405,84" in bot.mensajes[0]["text"]


@pytest.mark.unit
def test_factura_ya_registrada_marca_leido_sin_notificar_de_nuevo():
    bot = BotFalso()
    ya = resultado(ya_existia=True)
    with Ctx(registrar=ya) as ctx:
        assert correr(procesar_email_factura(bot, 1, MAIL)) is True

    ctx.marcar.assert_called_once_with("msg-1")
    assert bot.mensajes == []


@pytest.mark.unit
def test_si_falla_la_notificacion_la_factura_igual_queda_guardada():
    class BotRoto(BotFalso):
        async def send_message(self, **kw):
            raise ConnectionError("Telegram caído")

    with Ctx() as ctx:
        assert correr(procesar_email_factura(BotRoto(), 1, MAIL)) is True
    ctx.marcar.assert_called_once()


# ──────────────────────────────────────────────
# El invariante: si falla, NO se marca leído
# ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("fallo, donde", [
    (FacturaNoParseable("no encontré total a pagar"), "parsear"),
    (ValueError("algo raro"), "parsear"),
])
def test_fallo_al_parsear_no_marca_leido_y_avisa(fallo, donde):
    bot = BotFalso()
    with Ctx(parsear=fallo) as ctx:
        assert correr(procesar_email_factura(bot, 1, MAIL)) is False

    ctx.marcar.assert_not_called()
    assert len(bot.mensajes) == 1
    assert "⚠️" in bot.mensajes[0]["text"]


@pytest.mark.unit
@pytest.mark.parametrize("fallo", [
    ServicioDesconocido("identificador no registrado"),
    FacturaSospechosa("monto difiere x100 — revisá los decimales"),
    ConnectionError("supabase caído"),
])
def test_fallo_al_registrar_no_marca_leido_y_avisa(fallo):
    bot = BotFalso()
    with Ctx(registrar=fallo) as ctx:
        assert correr(procesar_email_factura(bot, 1, MAIL)) is False

    ctx.marcar.assert_not_called()
    assert len(bot.mensajes) == 1


@pytest.mark.unit
def test_el_aviso_incluye_lo_que_se_leyo_para_poder_diagnosticar():
    """Sin el monto y el vencimiento leídos no se puede saber qué regex tocar."""
    bot = BotFalso()
    with Ctx(registrar=FacturaSospechosa("monto difiere x100")):
        correr(procesar_email_factura(bot, 1, MAIL))

    texto = bot.mensajes[0]["text"]
    assert "$13.405,84" in texto
    assert "2026-08-05" in texto
    assert "edenor" in texto


@pytest.mark.unit
def test_no_se_marca_leido_si_falla_el_pdf_de_expensas():
    bot = BotFalso()
    incompleta = FacturaIncompleta(("https://s3/uno", "https://s3/dos"))
    with Ctx(parsear=incompleta) as ctx:
        with patch("bot.facturas_poller.resolver_expensas",
                   side_effect=ExpensasNoParseable("no encontré la unidad 255")):
            assert correr(procesar_email_factura(bot, 1, MAIL)) is False

    ctx.marcar.assert_not_called()
    assert "255" in bot.mensajes[0]["text"]


@pytest.mark.unit
def test_expensas_resuelto_por_pdf_se_registra():
    bot = BotFalso()
    incompleta = FacturaIncompleta(("https://s3/uno",))
    expensas = FacturaParseada(servicio="consorcio_gallo", identificador="",
                               monto=258198.55, vencimiento=date(2026, 8, 10))
    with Ctx(parsear=incompleta) as ctx:
        with patch("bot.facturas_poller.resolver_expensas", return_value=expensas):
            assert correr(procesar_email_factura(bot, 1, MAIL)) is True

    ctx.registrar.assert_called_once()
    assert ctx.registrar.call_args[0][0].monto == pytest.approx(258198.55)


# ──────────────────────────────────────────────
# resolver_expensas: elección del PDF por contenido
# ──────────────────────────────────────────────

SERVICIO_EXP = {"id": "srv", "slug": "consorcio_gallo", "unidad_funcional": "255"}


@pytest.mark.unit
def test_prueba_los_pdfs_hasta_encontrar_la_unidad():
    """El primer PDF es el de gastos del consorcio: no tiene la fila de la UF."""
    fila = FilaUnidad(unidad="255", total=258198.55, vencimiento=date(2026, 8, 10))
    with patch("bot.facturas_poller.queries.obtener_servicio_por_slug", return_value=SERVICIO_EXP), \
         patch("bot.facturas_poller.descargar_pdf", return_value=b"%PDF"), \
         patch("bot.facturas_poller.parsear_pdf_unidades",
               side_effect=[ExpensasNoParseable("sin unidad 255"), fila]):
        f = resolver_expensas(("https://s3/gastos", "https://s3/unidades"))

    assert f.monto == pytest.approx(258198.55)
    assert f.vencimiento == date(2026, 8, 10)
    assert f.identificador == ""  # se rutea por slug
    # Solo la URL que resultó tener la unidad, no la de gastos del consorcio:
    # es la que después se archiva como la factura del mes.
    assert f.pdf_urls == ("https://s3/unidades",)


@pytest.mark.unit
def test_si_ningun_pdf_tiene_la_unidad_falla_con_detalle():
    with patch("bot.facturas_poller.queries.obtener_servicio_por_slug", return_value=SERVICIO_EXP), \
         patch("bot.facturas_poller.descargar_pdf", return_value=b"%PDF"), \
         patch("bot.facturas_poller.parsear_pdf_unidades",
               side_effect=ExpensasNoParseable("sin unidad")):
        with pytest.raises(ExpensasNoParseable, match="ninguno de los 2"):
            resolver_expensas(("https://s3/a", "https://s3/b"))


@pytest.mark.unit
def test_pdf_sin_vencimiento_se_descarta():
    """Sin vencimiento la factura no sirve para la agenda: mejor fallar."""
    sin_vto = FilaUnidad(unidad="255", total=258198.55, vencimiento=None)
    with patch("bot.facturas_poller.queries.obtener_servicio_por_slug", return_value=SERVICIO_EXP), \
         patch("bot.facturas_poller.descargar_pdf", return_value=b"%PDF"), \
         patch("bot.facturas_poller.parsear_pdf_unidades", return_value=sin_vto):
        with pytest.raises(ExpensasNoParseable, match="vencimiento"):
            resolver_expensas(("https://s3/a",))


@pytest.mark.unit
def test_servicio_de_expensas_sin_unidad_configurada_falla_claro():
    with patch("bot.facturas_poller.queries.obtener_servicio_por_slug",
               return_value={"id": "srv", "slug": "consorcio_gallo", "unidad_funcional": None}):
        with pytest.raises(ExpensasNoParseable, match="unidad_funcional"):
            resolver_expensas(("https://s3/a",))


# ──────────────────────────────────────────────
# descargar_pdf: validaciones
# ──────────────────────────────────────────────

class RespuestaFalsa:
    def __init__(self, contenido=b"%PDF-1.7 ...", tipo="application/pdf"):
        self.content = contenido
        self.headers = {"Content-Type": tipo}

    def raise_for_status(self):
        pass


@pytest.mark.unit
def test_descarga_ok():
    with patch("requests.get", return_value=RespuestaFalsa()):
        assert descargar_pdf("https://s3/a").startswith(b"%PDF")


@pytest.mark.unit
def test_rechaza_lo_que_no_es_pdf():
    """El bucket de expensas sirve también el logo del mail: no parsearlo."""
    with patch("requests.get", return_value=RespuestaFalsa(b"\x89PNG", "image/png")):
        with pytest.raises(ExpensasNoParseable, match="no es un PDF"):
            descargar_pdf("https://s3/logo")


@pytest.mark.unit
def test_rechaza_contenido_sin_cabecera_pdf():
    """Content-Type correcto pero cuerpo que no es PDF (ej: una página de error)."""
    with patch("requests.get", return_value=RespuestaFalsa(b"<html>error</html>")):
        with pytest.raises(ExpensasNoParseable, match="cabecera PDF"):
            descargar_pdf("https://s3/a")


@pytest.mark.unit
def test_rechaza_archivos_enormes():
    with patch("requests.get", return_value=RespuestaFalsa(b"%PDF" + b"x" * (16 * 1024 * 1024))):
        with pytest.raises(ExpensasNoParseable, match="tope"):
            descargar_pdf("https://s3/a")


# ──────────────────────────────────────────────
# Loop
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_un_mail_roto_no_frena_a_los_demas():
    bot = BotFalso()
    mails = [{**MAIL, "id": "a"}, {**MAIL, "id": "b"}, {**MAIL, "id": "c"}]
    procesados = []

    async def procesar(bot_, chat, email):
        procesados.append(email["id"])
        if email["id"] == "b":
            raise RuntimeError("explota")
        return True

    with patch("bot.facturas_poller.get_unread_bank_emails", return_value=mails), \
         patch("bot.facturas_poller.procesar_email_factura", side_effect=procesar):
        assert correr(poll_facturas_once(bot, 1)) is True

    assert procesados == ["a", "b", "c"]


@pytest.mark.unit
def test_fallo_de_gmail_reporta_mala_salud():
    """Devolver False activa el dead-man's switch de _loop_poll."""
    with patch("bot.facturas_poller.get_unread_bank_emails",
               side_effect=ConnectionError("Gmail caído")):
        assert correr(poll_facturas_once(BotFalso(), 1)) is False


@pytest.mark.unit
def test_sin_mails_el_ciclo_es_sano():
    with patch("bot.facturas_poller.get_unread_bank_emails", return_value=[]):
        assert correr(poll_facturas_once(BotFalso(), 1)) is True


# ──────────────────────────────────────────────
# Fallback por identificador (mails reenviados)
# ──────────────────────────────────────────────

from bot.facturas_poller import parsear_con_fallback  # noqa: E402


@pytest.mark.unit
def test_fallback_rutea_por_numero_de_cuenta_cuando_el_remitente_es_desconocido():
    """
    Si reenviás las facturas desde otra casilla y el From: queda reescrito, el
    número de cuenta que viaja en el cuerpo salva el ruteo.
    """
    email = {"from": "yo@gmail.com", "subject": "Fwd: factura",
             "texto": "Numero de cuenta 5255064586 TOTAL A PAGAR $13.405,84", "html": ""}
    ident = {"tipo": "cuenta", "valor": "5255064586",
             "servicio": {"id": "s", "slug": "edenor", "activo": True}}

    with patch("bot.facturas_poller.parsear_facturas") as parsear, \
         patch("bot.tools.documentos.identificar_servicio", return_value=ident), \
         patch("bot.facturas_poller.queries.listar_identificadores_servicios",
               return_value=[ident]):
        parsear.side_effect = [
            FacturaNoParseable("remitente no registrado: 'yo@gmail.com'"),
            (PARSEADA,),
        ]
        assert parsear_con_fallback(email) == (PARSEADA,)

    assert parsear.call_args.kwargs["slug"] == "edenor"


@pytest.mark.unit
def test_el_fallback_no_se_usa_si_el_fallo_fue_de_formato():
    """Un template cambiado tiene que romper, no reintentar por otra vía."""
    with patch("bot.facturas_poller.parsear_facturas",
               side_effect=FacturaNoParseable("no encontré total a pagar")):
        with pytest.raises(FacturaNoParseable, match="total a pagar"):
            parsear_con_fallback({"from": "x@edenor.com", "texto": "..."})


@pytest.mark.unit
def test_si_el_fallback_tampoco_identifica_se_propaga_el_error_original():
    ident_vacio = []
    with patch("bot.facturas_poller.parsear_facturas",
               side_effect=FacturaNoParseable("remitente no registrado: 'x'")), \
         patch("bot.facturas_poller.queries.listar_identificadores_servicios",
               return_value=ident_vacio):
        with pytest.raises(FacturaNoParseable, match="remitente no registrado"):
            parsear_con_fallback({"from": "x@raro.com", "texto": "nada util"})


# ──────────────────────────────────────────────
# Ruido: se descarta sin alertar
# ──────────────────────────────────────────────

from bot.tools.facturas import FacturaIrrelevante  # noqa: E402


@pytest.mark.unit
def test_promo_se_marca_leida_sin_alertar_ni_guardar():
    """
    Una promo del mismo remitente no es un error: se marca leída y se sigue.
    Si alertara, cada campaña de Personal sería una notificación en falso.
    """
    bot = BotFalso()
    with Ctx(parsear=FacturaIrrelevante("mail de personal sin marcadores")) as ctx:
        assert correr(procesar_email_factura(bot, 1, MAIL)) is True

    ctx.marcar.assert_called_once_with("msg-1")
    ctx.registrar.assert_not_called()
    assert bot.mensajes == []


@pytest.mark.unit
def test_un_formato_cambiado_si_alerta_y_no_se_marca_leido():
    """Contraste explícito con el caso de arriba: acá sí hay que enterarse."""
    bot = BotFalso()
    with Ctx(parsear=FacturaNoParseable("no encontré total a pagar")) as ctx:
        assert correr(procesar_email_factura(bot, 1, MAIL)) is False

    ctx.marcar.assert_not_called()
    assert len(bot.mensajes) == 1


# ──────────────────────────────────────────────
# PDF de la factura (Personal)
# ──────────────────────────────────────────────

PERSONAL = FacturaParseada(
    servicio="personal", identificador="8100682932410002",
    monto=72711.49, vencimiento=date(2026, 9, 3),
    pdf_urls=("https://tufactura.personal.com.ar/facdigital-web/Consulta?q=TOKEN",),
)


@pytest.mark.unit
def test_el_pdf_se_archiva_y_se_avisa_en_el_resumen():
    bot = BotFalso()
    with Ctx(parsear=PERSONAL) as ctx:
        with patch("bot.facturas_poller.archivar_pdf_de_factura",
                   return_value={"id": "arch-1"}) as archivar:
            assert correr(procesar_email_factura(bot, 1, MAIL)) is True

    archivar.assert_called_once()
    assert archivar.call_args[0][1] == {"id": "fac-1"}  # se cuelga de la factura recién creada
    ctx.marcar.assert_called_once_with("msg-1")
    assert "PDF archivado" in bot.mensajes[0]["text"]


@pytest.mark.unit
def test_si_falla_el_pdf_la_factura_igual_queda_registrada_y_el_mail_leido():
    """
    El invariante del poller es "no marcar leído si algo falló", pero el PDF es
    la excepción deliberada: la factura ya está guardada y reintentar un flujo de
    descarga roto alertaría en cada ciclo para siempre. Lo faltante lo reclama el
    repaso semanal de documentación.
    """
    bot = BotFalso()
    with Ctx(parsear=PERSONAL) as ctx:
        with patch("bot.facturas_poller.archivar_pdf_de_factura",
                   side_effect=ConnectionError("tufactura no responde")):
            assert correr(procesar_email_factura(bot, 1, MAIL)) is True

    ctx.marcar.assert_called_once_with("msg-1")
    assert len(bot.mensajes) == 2
    assert "No pude bajar el PDF" in bot.mensajes[0]["text"]
    assert "registrada igual" in bot.mensajes[0]["text"]
    # El aviso NO puede decir que no se guardó nada: la factura sí se guardó.
    assert "Nada se guardó" not in bot.mensajes[0]["text"]
    assert "PDF archivado" not in bot.mensajes[1]["text"]


@pytest.mark.unit
def test_una_factura_sin_link_no_intenta_descargar_nada():
    bot = BotFalso()
    with Ctx():  # PARSEADA es de edenor, sin pdf_urls
        with patch("bot.facturas_poller.archivar_pdf_de_factura") as archivar:
            assert correr(procesar_email_factura(bot, 1, MAIL)) is True

    archivar.assert_not_called()
    assert "PDF archivado" not in bot.mensajes[0]["text"]


@pytest.mark.unit
def test_una_factura_ya_registrada_no_vuelve_a_archivar_el_pdf():
    """Evita un duplicado en Drive si el mail se reprocesa."""
    bot = BotFalso()
    ya = resultado(ya_existia=True)
    with Ctx(parsear=PERSONAL, registrar=ya):
        with patch("bot.facturas_poller.archivar_pdf_de_factura") as archivar:
            assert correr(procesar_email_factura(bot, 1, MAIL)) is True

    archivar.assert_not_called()


@pytest.mark.unit
def test_cualquier_error_de_descarga_sale_como_pdf_no_disponible():
    """El caller no tiene que distinguir en cuál de los dos saltos se rompió."""
    from bot.tools.personal_pdf import PersonalPdfNoDisponible

    with patch("bot.facturas_poller.descargar_pdf", side_effect=OSError("DNS")):
        with patch("bot.tools.personal_pdf.resolver_url_pdf", return_value="https://x/y.pdf"):
            with pytest.raises(PersonalPdfNoDisponible, match="falló la descarga"):
                descargar_factura_personal("https://tufactura.personal.com.ar/a", 1.0)


# ──────────────────────────────────────────────
# PDF de la factura (AySA)
# ──────────────────────────────────────────────

AYSA = FacturaParseada(
    servicio="aysa", identificador="1929557", monto=30562.17,
    vencimiento=date(2026, 8, 13), nro_factura="0111B20261385",
    pdf_urls=("https://customer27066g.musvc2.net/e/tr?q=TOKEN",),
)


@pytest.mark.unit
def test_cada_servicio_va_por_su_flujo_de_descarga():
    """Personal salta por JavaScript y AySA por redirecciones: no se mezclan."""
    with patch("bot.facturas_poller.descargar_factura_aysa", return_value=b"%PDF") as aysa, \
         patch("bot.facturas_poller.descargar_factura_personal") as personal:
        assert pdf_de_factura(AYSA) == b"%PDF"

    personal.assert_not_called()
    aysa.assert_called_once_with(AYSA.pdf_urls, "0111B20261385", 30562.17)


@pytest.mark.unit
def test_un_servicio_con_link_pero_sin_flujo_de_descarga_falla_claro():
    """Si mañana un parser devuelve pdf_urls y nadie cableó la descarga, que se
    note en el aviso y no en un archivado silencioso que nunca ocurre."""
    with pytest.raises(ValueError, match="descarga automática"):
        pdf_de_factura(replace(PERSONAL, servicio="metrogas"))


@pytest.mark.unit
def test_cualquier_error_de_descarga_de_aysa_sale_como_pdf_no_disponible():
    """El caller no tiene que distinguir en cuál de los saltos se rompió."""
    from bot.tools.aysa_pdf import AysaPdfNoDisponible

    with patch("bot.facturas_poller.descargar_pdf", side_effect=OSError("DNS")):
        with patch("bot.tools.aysa_pdf.resolver_url_pdf", return_value="https://x/y.pdf"):
            with pytest.raises(AysaPdfNoDisponible, match="falló la descarga"):
                descargar_factura_aysa(AYSA.pdf_urls, AYSA.nro_factura, AYSA.monto)


@pytest.mark.unit
def test_un_pdf_que_no_es_de_esta_factura_no_se_archiva():
    """La verificación por contenido es lo último que separa el PDF correcto del
    del mes pasado: si no pasa, no puede quedar colgado igual."""
    from bot.tools.aysa_pdf import AysaPdfNoDisponible

    with patch("bot.facturas_poller.descargar_pdf", return_value=b"%PDF"), \
         patch("bot.tools.aysa_pdf.resolver_url_pdf", return_value="https://x/y.pdf"), \
         patch("bot.tools.aysa_pdf.texto_primera_pagina", return_value="LSP 0111B99999999"):
        with pytest.raises(AysaPdfNoDisponible, match="otra factura"):
            descargar_factura_aysa(AYSA.pdf_urls, AYSA.nro_factura, AYSA.monto)


# ──────────────────────────────────────────────
# PDF de la factura (Edenor)
# ──────────────────────────────────────────────

TOKEN_EDENOR = ("eyJhbGciOiJIUzI1NiJ9."
                "eyJjdWVudGFfaWQiOiI1MjU1MDY0NTg2IiwiZmFjdHVyYV9pZCI6IjEifQ.firma")

EDENOR = FacturaParseada(
    servicio="edenor", identificador="5255064586", monto=13405.84,
    vencimiento=date(2026, 8, 5),
    pdf_urls=(f"https://edenordigital.com/descarga_de_factura?token={TOKEN_EDENOR}",),
)


@pytest.mark.unit
def test_edenor_va_por_su_propio_flujo():
    with patch("bot.facturas_poller.descargar_factura_edenor", return_value=b"%PDF") as edenor:
        assert pdf_de_factura(EDENOR) == b"%PDF"
    edenor.assert_called_once_with(EDENOR.pdf_urls[0], "5255064586", 13405.84)


@pytest.mark.unit
def test_el_pedido_a_la_api_de_edenor_lleva_la_cabecera_del_tenant():
    """Sin Utility-ID la API responde 400: si se pierde, esto lo dice."""
    with patch("bot.facturas_poller.descargar_pdf", return_value=b"%PDF") as bajar, \
         patch("bot.tools.edenor_pdf.texto_primera_pagina",
               return_value="Cuenta 5 255 064 586 TOTALAPAGAR $ 13.405,84"):
        descargar_factura_edenor(EDENOR.pdf_urls[0], EDENOR.identificador, EDENOR.monto)

    url, kwargs = bajar.call_args[0][0], bajar.call_args[1]
    assert url.startswith("https://utilitygo.widergy.com/api/v1/bills/public_pdf?token=")
    assert kwargs["headers"]["Utility-ID"] == "19"


@pytest.mark.unit
def test_una_factura_de_otra_cuenta_no_se_llega_a_pedir():
    """El token dice de qué cuenta es: si no es la del mail, no se pide nada."""
    from bot.tools.edenor_pdf import EdenorPdfNoDisponible

    with patch("bot.facturas_poller.descargar_pdf") as bajar:
        with pytest.raises(EdenorPdfNoDisponible, match="cuenta"):
            descargar_factura_edenor(EDENOR.pdf_urls[0], "9999999999", EDENOR.monto)
    bajar.assert_not_called()


@pytest.mark.unit
def test_cualquier_error_de_descarga_de_edenor_sale_como_pdf_no_disponible():
    from bot.tools.edenor_pdf import EdenorPdfNoDisponible

    with patch("bot.facturas_poller.descargar_pdf", side_effect=OSError("DNS")):
        with pytest.raises(EdenorPdfNoDisponible, match="falló la descarga"):
            descargar_factura_edenor(EDENOR.pdf_urls[0], EDENOR.identificador, EDENOR.monto)


@pytest.mark.unit
def test_el_pdf_del_mes_pasado_de_edenor_no_se_archiva():
    """La cuenta coincide igual todos los meses: lo que lo delata es el importe."""
    from bot.tools.edenor_pdf import EdenorPdfNoDisponible

    with patch("bot.facturas_poller.descargar_pdf", return_value=b"%PDF"), \
         patch("bot.tools.edenor_pdf.texto_primera_pagina",
               return_value="Cuenta 5 255 064 586 TOTALAPAGAR $ 12.000,00"):
        with pytest.raises(EdenorPdfNoDisponible, match="otra factura"):
            descargar_factura_edenor(EDENOR.pdf_urls[0], EDENOR.identificador, EDENOR.monto)


# ──────────────────────────────────────────────
# PDF de la factura (Consorcio Gallo / expensas)
# ──────────────────────────────────────────────

CONSORCIO = FacturaParseada(
    servicio="consorcio_gallo", identificador="", monto=266380.78,
    vencimiento=date(2026, 9, 10),
    pdf_urls=("https://simplesolutionscloud.s3.amazonaws.com/liq/255.pdf",),
)


@pytest.mark.unit
def test_las_expensas_tambien_se_archivan_solas():
    """
    Bug real: resolver_expensas bajaba el PDF, lo parseaba y lo tiraba, así que
    la factura del consorcio nunca tenía documento y su celda en Registro no
    llegaba nunca a estar completa. Era el único servicio con el PDF ya en la
    mano y el único que no lo archivaba.
    """
    with patch("bot.facturas_poller.descargar_factura_consorcio",
               return_value=b"%PDF") as consorcio:
        assert pdf_de_factura(CONSORCIO) == b"%PDF"

    consorcio.assert_called_once_with(CONSORCIO.pdf_urls[0], 266380.78)


@pytest.mark.unit
def test_la_liquidacion_se_verifica_antes_de_archivarse():
    """Mismo criterio que los otros tres: el importe tiene que ser el de la factura."""
    otra = FilaUnidad(unidad="255", total=258198.55, vencimiento=date(2026, 8, 10))
    with patch("bot.facturas_poller.queries.obtener_servicio_por_slug", return_value=SERVICIO_EXP), \
         patch("bot.facturas_poller.descargar_pdf", return_value=b"%PDF"), \
         patch("bot.facturas_poller.parsear_pdf_unidades", return_value=otra):
        with pytest.raises(ExpensasNoParseable, match="266.380,78"):
            descargar_factura_consorcio(CONSORCIO.pdf_urls[0], CONSORCIO.monto)


@pytest.mark.unit
def test_la_liquidacion_correcta_se_devuelve_tal_cual():
    fila = FilaUnidad(unidad="255", total=266380.78, vencimiento=date(2026, 9, 10))
    with patch("bot.facturas_poller.queries.obtener_servicio_por_slug", return_value=SERVICIO_EXP), \
         patch("bot.facturas_poller.descargar_pdf", return_value=b"%PDF-expensas"), \
         patch("bot.facturas_poller.parsear_pdf_unidades", return_value=fila):
        assert descargar_factura_consorcio(CONSORCIO.pdf_urls[0], CONSORCIO.monto) == b"%PDF-expensas"


@pytest.mark.unit
def test_un_mail_de_expensas_termina_con_el_pdf_colgado_de_la_factura():
    """El circuito completo, que es lo que estaba roto de punta a punta."""
    bot = BotFalso()
    incompleta = FacturaIncompleta(("https://s3/gastos", "https://s3/unidades"))
    with Ctx(parsear=incompleta) as ctx:
        with patch("bot.facturas_poller.resolver_expensas", return_value=CONSORCIO), \
             patch("bot.facturas_poller.archivar_pdf_de_factura",
                   return_value={"id": "arch-1"}) as archivar:
            assert correr(procesar_email_factura(bot, 1, MAIL)) is True

    archivar.assert_called_once()
    assert archivar.call_args[0][0].servicio == "consorcio_gallo"
    assert archivar.call_args[0][1] == {"id": "fac-1"}
    ctx.marcar.assert_called_once_with("msg-1")
    assert "PDF archivado" in bot.mensajes[0]["text"]


# ──────────────────────────────────────────────
# AySA con dos cuentas en el mismo aviso (depto + baulera)
# ──────────────────────────────────────────────

FIXTURES = Path(__file__).parent / "fixtures"

DEPTO = FacturaParseada(
    servicio="aysa", identificador="1929557", monto=32832.59,
    vencimiento=date(2026, 11, 12), nro_factura="0111B31630809",
    pdf_urls=("https://t/boton-1", "https://t/boton-2"),
)
BAULERA = replace(DEPTO, identificador="1932903", monto=19120.69,
                  vencimiento=date(2026, 11, 10), nro_factura="0111B31161881")

SERV_AYSA = {"id": "srv-aysa", "slug": "aysa", "nombre": "AySA"}
SERV_BAULERA = {"id": "srv-baulera", "slug": "aysa_baulera", "nombre": "AySA Baulera"}


def _mail_real(nombre: str) -> dict:
    """El .eml tal como lo entrega gmail_reader, para pasar por el poller entero."""
    ruta = FIXTURES / "emails" / f"{nombre}.eml"
    if not ruta.exists():
        pytest.skip(f"falta el fixture {nombre}.eml")
    msg = email_lib.message_from_bytes(ruta.read_bytes(), policy=policy.default)
    html = next(p.get_content() for p in msg.walk() if p.get_content_type() == "text/html")
    return {"id": "msg-aysa", "from": msg["From"], "subject": msg["Subject"],
            "body": "", "html": html}


def _pdf_real(nombre: str) -> bytes:
    ruta = FIXTURES / "facturas" / nombre
    if not ruta.exists():
        pytest.skip(f"falta el fixture {nombre}")
    return ruta.read_bytes()


@pytest.mark.unit
def test_el_aviso_real_de_aysa_registra_el_depto_y_la_baulera():
    """
    Bug real: el aviso del 20/10/2026 trajo las dos cuentas y solo se registró
    el depto; la baulera se perdió y el mail quedó leído. Ahora pasa el mail
    real por el poller entero: cada fila se rutea por su número de cuenta, se
    registra a su servicio y se avisa con el nombre de ese servicio.
    """
    por_cuenta = {"1929557": SERV_AYSA, "1932903": SERV_BAULERA}

    def registrar(parseada, eid):
        return resultado(factura_id=f"fac-{parseada.identificador}",
                         servicio=por_cuenta[parseada.identificador])

    bot = BotFalso()
    with patch("bot.facturas_poller.registrar_factura", side_effect=registrar) as reg, \
         patch("bot.facturas_poller.mark_as_read") as marcar, \
         patch("bot.facturas_poller.archivar_pdf_de_factura") as archivar:
        assert correr(procesar_email_factura(bot, 1, _mail_real("aysa_dos_cuentas"))) is True

    assert [c[0][0].identificador for c in reg.call_args_list] == ["1929557", "1932903"]
    marcar.assert_called_once_with("msg-aysa")
    # Cada PDF va a la carpeta del servicio al que se ruteó, no a la de "aysa".
    assert [c[0][2]["slug"] for c in archivar.call_args_list] == ["aysa", "aysa_baulera"]
    textos = [m["text"] for m in bot.mensajes]
    assert len(textos) == 2
    assert "$32.832,59" in textos[0] and "*AySA*" in textos[0]
    assert "$19.120,69" in textos[1] and "AySA Baulera" in textos[1]


@pytest.mark.unit
def test_si_una_de_las_facturas_falla_el_mail_queda_sin_leer():
    """
    La que entró sigue su curso (PDF y aviso) y la que falló avisa. El mail se
    reintenta, y el registro idempotente por mail y servicio no duplica la que
    ya está.
    """
    bot = BotFalso()
    fallo = ServicioDesconocido("el identificador '1932903' no está registrado")
    with Ctx(parsear=(DEPTO, BAULERA),
             registrar=[resultado(servicio=SERV_AYSA), fallo]) as ctx, \
         patch("bot.facturas_poller.archivar_pdf_de_factura") as archivar:
        assert correr(procesar_email_factura(bot, 1, MAIL)) is False

    ctx.marcar.assert_not_called()
    archivar.assert_called_once()
    textos = " ".join(m["text"] for m in bot.mensajes)
    assert "1932903" in textos            # la alerta dice qué cuenta falló
    assert "$32.832,59" in textos         # y la que entró se avisa igual


@pytest.mark.unit
def test_el_reintento_solo_registra_la_que_faltaba():
    """
    Recuperar la baulera de octubre es marcar el mail como no leído: el depto
    ya está (no se vuelve a archivar ni a avisar) y entra solo la baulera.
    """
    bot = BotFalso()
    with Ctx(parsear=(DEPTO, BAULERA),
             registrar=[resultado(ya_existia=True, servicio=SERV_AYSA),
                        resultado(servicio=SERV_BAULERA)]) as ctx, \
         patch("bot.facturas_poller.archivar_pdf_de_factura") as archivar:
        assert correr(procesar_email_factura(bot, 1, MAIL)) is True

    ctx.marcar.assert_called_once_with("msg-1")
    archivar.assert_called_once()
    assert archivar.call_args[0][2] is SERV_BAULERA
    assert len(bot.mensajes) == 1
    assert "AySA Baulera" in bot.mensajes[0]["text"]


@pytest.mark.unit
@pytest.mark.parametrize("orden", ["depto primero", "baulera primero"])
def test_cada_factura_se_queda_con_su_pdf_sin_importar_el_orden(orden):
    """
    Con los PDFs reales de octubre: el de la baulera menciona solo su LSP y su
    total, así que la verificación por contenido lo separa del del depto aunque
    los botones vengan en cualquier orden.
    """
    pdfs = {"https://t/depto": _pdf_real("aysa_depto_2026-11.pdf"),
            "https://t/baulera": _pdf_real("aysa_baulera_2026-11.pdf")}
    urls = tuple(pdfs) if orden == "depto primero" else tuple(reversed(pdfs))

    with patch("bot.tools.aysa_pdf.resolver_url_pdf", side_effect=lambda u: u), \
         patch("bot.facturas_poller.descargar_pdf", side_effect=pdfs.__getitem__):
        assert descargar_factura_aysa(urls, DEPTO.nro_factura, DEPTO.monto) \
            == pdfs["https://t/depto"]
        assert descargar_factura_aysa(urls, BAULERA.nro_factura, BAULERA.monto) \
            == pdfs["https://t/baulera"]


@pytest.mark.unit
def test_si_ningun_pdf_es_el_de_la_factura_no_se_archiva_y_dice_por_que():
    from bot.tools.aysa_pdf import AysaPdfNoDisponible

    with patch("bot.tools.aysa_pdf.resolver_url_pdf", side_effect=lambda u: u), \
         patch("bot.facturas_poller.descargar_pdf", return_value=b"%PDF"), \
         patch("bot.tools.aysa_pdf.texto_primera_pagina", return_value="LSP 0111B99999999"):
        with pytest.raises(AysaPdfNoDisponible, match="ninguno de los 2 PDFs"):
            descargar_factura_aysa(DEPTO.pdf_urls, DEPTO.nro_factura, DEPTO.monto)
