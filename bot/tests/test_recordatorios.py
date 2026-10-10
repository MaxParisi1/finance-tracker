"""
Tests de los recordatorios.

Dos riesgos opuestos que hay que balancear: que no avise (y pagues con recargo)
y que avise de más (y dejes de leerlo, que termina siendo lo mismo). Los tests
fijan la cadencia exacta para que ningún cambio futuro la corra sin querer.
"""

from datetime import date, datetime
from unittest.mock import patch

import pytest

from bot.tools.recordatorios import (
    TIPO_FALTA_COMPROBANTE, TIPO_FALTA_FACTURA, TIPO_VENCE, TIPO_VENCIDA,
    ZONA, _ultimo_envio_guardado, calcular_avisos, formatear_avisos, toca_enviar,
)

LUNES = date(2026, 8, 10)
MARTES = date(2026, 8, 11)


def factura(vto, estado="pendiente", archivos=(), nombre="AySA", monto=30562.17, id_="f1"):
    return {
        "id": id_, "monto": monto, "vencimiento": vto, "estado": estado,
        "servicios": {"slug": "aysa", "nombre": nombre},
        "archivos_drive": [{"tipo": t} for t in archivos],
    }


def tipos(avisos):
    return [a.tipo for a in avisos]


# ──────────────────────────────────────────────
# Cadencia previa al vencimiento
# ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("dias, avisa", [
    (7, False), (5, False), (4, False),
    (3, True),                      # primer aviso
    (2, False),
    (1, True),                      # víspera
    (0, True),                      # el día
])
def test_avisa_solo_en_los_dias_definidos(dias, avisa):
    """Sin esto sería un aviso por día durante una semana: ruido puro."""
    vto = date(2026, 8, 11 + dias)
    avisos = calcular_avisos([factura(vto.isoformat())], date(2026, 8, 11))
    assert (TIPO_VENCE in tipos(avisos)) is avisa


@pytest.mark.unit
@pytest.mark.parametrize("dias_vencida, avisa", [
    (1, False), (2, False),
    (3, True), (6, True), (9, True),   # insiste cada 3 días
    (4, False), (5, False),
])
def test_insiste_cada_tres_dias_una_vez_vencida(dias_vencida, avisa):
    vto = date(2026, 8, 11 - dias_vencida)
    avisos = calcular_avisos([factura(vto.isoformat())], MARTES)
    assert (TIPO_VENCIDA in tipos(avisos)) is avisa


@pytest.mark.unit
def test_una_factura_pagada_no_genera_avisos_de_vencimiento():
    avisos = calcular_avisos(
        [factura("2026-08-14", estado="pagada", archivos=("factura", "comprobante"))],
        MARTES,
    )
    assert avisos == []


# ──────────────────────────────────────────────
# Documentación faltante: repaso semanal
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_el_repaso_de_documentacion_es_solo_los_lunes():
    f = [factura("2026-08-14", estado="pagada", archivos=())]
    assert TIPO_FALTA_FACTURA in tipos(calcular_avisos(f, LUNES))
    assert TIPO_FALTA_FACTURA not in tipos(calcular_avisos(f, MARTES))


@pytest.mark.unit
def test_avisa_si_falta_la_factura():
    f = [factura("2026-08-14", estado="pagada", archivos=("comprobante",))]
    assert tipos(calcular_avisos(f, LUNES)) == [TIPO_FALTA_FACTURA]


@pytest.mark.unit
def test_avisa_si_falta_el_comprobante_de_una_pagada():
    f = [factura("2026-08-14", estado="pagada", archivos=("factura",))]
    assert tipos(calcular_avisos(f, LUNES)) == [TIPO_FALTA_COMPROBANTE]


@pytest.mark.unit
def test_no_pide_comprobante_de_una_factura_impaga():
    """Todavía no la pagaste: no puede faltarte el comprobante."""
    f = [factura("2026-08-20", estado="pendiente", archivos=("factura",))]
    assert TIPO_FALTA_COMPROBANTE not in tipos(calcular_avisos(f, LUNES))


@pytest.mark.unit
def test_con_todo_archivado_no_avisa_nada():
    f = [factura("2026-08-14", estado="pagada", archivos=("factura", "comprobante"))]
    assert calcular_avisos(f, LUNES) == []


@pytest.mark.unit
def test_no_persigue_facturas_viejas():
    """El repaso mira 3 meses atrás; lo anterior ya es historia."""
    f = [factura("2026-01-15", estado="pagada", archivos=())]
    assert calcular_avisos(f, LUNES) == []


@pytest.mark.unit
def test_el_limite_del_repaso_cruza_bien_el_año():
    """En febrero, 3 meses atrás es noviembre del año anterior."""
    febrero = date(2026, 2, 2)  # lunes
    assert febrero.weekday() == 0
    dentro = [factura("2025-12-10", estado="pagada", archivos=())]
    fuera = [factura("2025-09-10", estado="pagada", archivos=())]
    assert calcular_avisos(dentro, febrero) != []
    assert calcular_avisos(fuera, febrero) == []


# ──────────────────────────────────────────────
# Orden y datos corruptos
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_ordena_lo_mas_urgente_primero():
    avisos = calcular_avisos([
        factura("2026-08-14", id_="en3", nombre="Edenor"),
        factura("2026-08-08", id_="vencida", nombre="AySA"),
        factura("2026-08-11", id_="hoy", nombre="Metrogas"),
    ], MARTES)
    assert [a.servicio for a in avisos] == ["AySA", "Metrogas", "Edenor"]


@pytest.mark.unit
@pytest.mark.parametrize("vto_roto", [None, "", "no-es-fecha", "2026-13-45"])
def test_factura_con_vencimiento_corrupto_se_omite_sin_romper(vto_roto):
    avisos = calcular_avisos(
        [factura(vto_roto, id_="rota"), factura("2026-08-11", id_="sana")], MARTES
    )
    assert [a.factura_id for a in avisos] == ["sana"]


@pytest.mark.unit
def test_servicio_sin_nombre_no_rompe():
    f = {"id": "x", "monto": 100, "vencimiento": "2026-08-11",
         "estado": "pendiente", "servicios": None, "archivos_drive": None}
    assert calcular_avisos([f], MARTES)[0].servicio == "(servicio desconocido)"


# ──────────────────────────────────────────────
# Formato del mensaje
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_sin_avisos_no_hay_mensaje():
    assert formatear_avisos([]) is None


@pytest.mark.unit
def test_el_mensaje_usa_formato_de_montos_argentino():
    msg = formatear_avisos(calcular_avisos([factura("2026-08-11")], MARTES))
    assert "$30.562,17" in msg


@pytest.mark.unit
def test_el_mensaje_distingue_vencida_de_por_vencer():
    vencida = formatear_avisos(calcular_avisos([factura("2026-08-08")], MARTES))
    hoy = formatear_avisos(calcular_avisos([factura("2026-08-11")], MARTES))
    proxima = formatear_avisos(calcular_avisos([factura("2026-08-14")], MARTES))
    assert "venció hace 3 días" in vencida
    assert "vence *hoy*" in hoy
    assert "vence en 3 días" in proxima


@pytest.mark.unit
def test_con_varios_vencimientos_muestra_el_total():
    avisos = calcular_avisos([
        factura("2026-08-11", monto=1000.0, id_="a", nombre="AySA"),
        factura("2026-08-14", monto=2000.0, id_="b", nombre="Edenor"),
    ], MARTES)
    assert "Total: $3.000,00" in formatear_avisos(avisos)


@pytest.mark.unit
def test_un_solo_vencimiento_no_muestra_total_redundante():
    msg = formatear_avisos(calcular_avisos([factura("2026-08-11")], MARTES))
    assert "Total" not in msg


@pytest.mark.unit
def test_separa_vencimientos_de_documentacion_pendiente():
    avisos = calcular_avisos([
        factura("2026-08-13", id_="a", nombre="AySA"),
        factura("2026-08-05", estado="pagada", archivos=(), id_="b", nombre="Edenor"),
    ], LUNES)
    msg = formatear_avisos(avisos)
    assert "*Vencimientos*" in msg
    assert "*Documentación pendiente*" in msg


# ──────────────────────────────────────────────
# Una vez por día, aunque el bot se reinicie
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_no_reenvia_el_recordatorio_despues_de_un_reinicio():
    """
    Bug real: la marca de "hoy ya avisé" era una variable local del loop. Cada
    deploy-bot después de las 9 arrancaba sin memoria y volvía a mandar el
    recordatorio del día. Ahora la marca se lee de la base al arrancar.
    """
    with patch("bot.tools.estado.queries.leer_estado", return_value={"fecha": "2026-08-11"}):
        ultimo = _ultimo_envio_guardado()

    reinicio_a_las_15 = datetime(2026, 8, 11, 15, 0, tzinfo=ZONA)
    assert ultimo == date(2026, 8, 11)
    assert toca_enviar(reinicio_a_las_15, ultimo) is False


@pytest.mark.unit
def test_al_dia_siguiente_vuelve_a_avisar():
    assert toca_enviar(datetime(2026, 8, 12, 9, 5, tzinfo=ZONA), date(2026, 8, 11)) is True


@pytest.mark.unit
def test_antes_de_las_nueve_no_avisa():
    assert toca_enviar(datetime(2026, 8, 12, 8, 59, tzinfo=ZONA), date(2026, 8, 11)) is False


@pytest.mark.unit
def test_si_la_base_no_responde_el_loop_arranca_igual():
    """Sin marca se comporta como antes (avisa); lo que no puede es tumbar el bot."""
    with patch("bot.tools.estado.queries.leer_estado", side_effect=RuntimeError("sin red")):
        assert _ultimo_envio_guardado() is None


@pytest.mark.unit
def test_las_nueve_son_las_de_argentina_no_las_del_servidor():
    """A las 9:00 UTC en Buenos Aires son las 6: todavía no toca."""
    from datetime import timezone
    nueve_utc = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc).astimezone(ZONA)
    assert toca_enviar(nueve_utc, None) is False


@pytest.mark.unit
def test_un_envio_fallido_no_cuenta_como_enviado():
    """
    Si Telegram falla a las 9, el día no puede quedar marcado como avisado: la
    marca se guarda en la base, así que ni un reinicio lo reintentaría.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from bot.tools.recordatorios import enviar_recordatorios

    vence_hoy = [factura("2026-08-11")]
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("Telegram caído"))
    with patch("bot.db.queries.obtener_facturas_con_archivos", return_value=vence_hoy):
        assert asyncio.run(enviar_recordatorios(bot, 1, MARTES)) is False

    bot.send_message = AsyncMock()
    with patch("bot.db.queries.obtener_facturas_con_archivos", return_value=vence_hoy):
        assert asyncio.run(enviar_recordatorios(bot, 1, MARTES)) is True


@pytest.mark.unit
def test_un_dia_sin_nada_que_avisar_queda_resuelto():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from bot.tools.recordatorios import enviar_recordatorios

    bot = MagicMock()
    bot.send_message = AsyncMock()
    with patch("bot.db.queries.obtener_facturas_con_archivos", return_value=[]):
        assert asyncio.run(enviar_recordatorios(bot, 1, MARTES)) is True
    bot.send_message.assert_not_called()
