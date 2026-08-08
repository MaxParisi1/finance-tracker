"""Tests del canal de avisos de error por Telegram."""

import asyncio

import pytest

from bot.tools.alertas import (
    alertar_error, escapar_md, formatear_error, resetear_dedup,
)
from bot.tools.facturas import FacturaNoParseable


class BotFalso:
    def __init__(self, explota: bool = False):
        self.mensajes: list[dict] = []
        self.explota = explota

    async def send_message(self, **kwargs):
        if self.explota:
            raise ConnectionError("Telegram caído")
        self.mensajes.append(kwargs)


@pytest.fixture(autouse=True)
def _limpiar_dedup():
    resetear_dedup()
    yield
    resetear_dedup()


@pytest.mark.unit
def test_escapar_md_neutraliza_markdown():
    assert "*" not in escapar_md("total *roto*")
    assert escapar_md("gasto_id") == "gasto\\_id"


@pytest.mark.unit
def test_el_mensaje_incluye_el_campo_que_falló():
    """El aviso tiene que decir QUÉ se rompió para poder escribir el fix."""
    exc = FacturaNoParseable("no encontré total a pagar")
    msg = formatear_error("Factura sin parsear", {"Servicio": "edenor"}, exc)
    assert "edenor" in msg
    assert "no encontré total a pagar" in msg
    assert "FacturaNoParseable" in msg


@pytest.mark.unit
def test_detalle_largo_se_trunca():
    msg = formatear_error("X", {}, ValueError("y" * 2000))
    assert len(msg) < 700
    assert "…" in msg


@pytest.mark.unit
def test_contexto_none_se_omite():
    msg = formatear_error("X", {"Servicio": "aysa", "Monto": None}, None)
    assert "aysa" in msg
    assert "Monto" not in msg


@pytest.mark.unit
def test_envia_la_alerta():
    bot = BotFalso()
    assert asyncio.run(alertar_error(bot, 1, titulo="Falló", exc=ValueError("x"))) is True
    assert len(bot.mensajes) == 1
    assert bot.mensajes[0]["chat_id"] == 1


@pytest.mark.unit
def test_no_spamea_la_misma_falla():
    """El poller corre cada 15 min: la misma falla no puede avisar cada ciclo."""
    bot = BotFalso()
    for _ in range(5):
        asyncio.run(alertar_error(bot, 1, titulo="Falló", exc=ValueError("x"), clave="k"))
    assert len(bot.mensajes) == 1


@pytest.mark.unit
def test_fallas_distintas_avisan_por_separado():
    bot = BotFalso()
    asyncio.run(alertar_error(bot, 1, titulo="A", exc=ValueError("x"), clave="a"))
    asyncio.run(alertar_error(bot, 1, titulo="B", exc=ValueError("x"), clave="b"))
    assert len(bot.mensajes) == 2


@pytest.mark.unit
def test_si_telegram_falla_no_propaga():
    """Un fallo al avisar no puede tumbar el loop del poller."""
    assert asyncio.run(alertar_error(BotFalso(explota=True), 1, titulo="Falló")) is False
