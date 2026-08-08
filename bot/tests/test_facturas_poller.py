"""
Tests del poller de facturas.

El invariante que se protege: un mail SOLO se marca como leído si quedó
resuelto. Si algo falla, el mail sigue sin leer y llega un aviso — así ninguna
factura se pierde en silencio, que es el modo de falla más caro de todos.
"""

import asyncio
from datetime import date
from unittest.mock import patch

import pytest

from bot.facturas_poller import (
    descargar_pdf, poll_facturas_once, procesar_email_factura, resolver_expensas,
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
        patch("bot.facturas_poller.parsear_email",
              **({"side_effect": parsear} if isinstance(parsear, Exception)
                 else {"return_value": parsear or PARSEADA})),
        patch("bot.facturas_poller.registrar_factura",
              **({"side_effect": registrar} if isinstance(registrar, Exception)
                 else {"return_value": registrar or ResultadoRegistro(
                     factura={"id": "fac-1"}, ya_existia=False)})),
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
    ya = ResultadoRegistro(factura={"id": "fac-1"}, ya_existia=True)
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

    with patch("bot.facturas_poller.parsear_email") as parsear, \
         patch("bot.tools.documentos.identificar_servicio", return_value=ident), \
         patch("bot.facturas_poller.queries.listar_identificadores_servicios",
               return_value=[ident]):
        parsear.side_effect = [
            FacturaNoParseable("remitente no registrado: 'yo@gmail.com'"),
            PARSEADA,
        ]
        assert parsear_con_fallback(email) is PARSEADA

    assert parsear.call_args.kwargs["slug"] == "edenor"


@pytest.mark.unit
def test_el_fallback_no_se_usa_si_el_fallo_fue_de_formato():
    """Un template cambiado tiene que romper, no reintentar por otra vía."""
    with patch("bot.facturas_poller.parsear_email",
               side_effect=FacturaNoParseable("no encontré total a pagar")):
        with pytest.raises(FacturaNoParseable, match="total a pagar"):
            parsear_con_fallback({"from": "x@edenor.com", "texto": "..."})


@pytest.mark.unit
def test_si_el_fallback_tampoco_identifica_se_propaga_el_error_original():
    ident_vacio = []
    with patch("bot.facturas_poller.parsear_email",
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
