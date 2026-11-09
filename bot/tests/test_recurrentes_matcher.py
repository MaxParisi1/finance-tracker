"""
Tests de la confirmación de recurrentes por Telegram.

Lo que se protege: que un botón "¿vincular?" siga funcionando aunque el bot se
haya reiniciado entre la pregunta y la respuesta.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bot.tools import recurrentes_matcher as matcher

GASTO_ID = "3f2b8c1e-7a4d-4e9b-9c55-0d1e2f3a4b5c"
REC_ID = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"

GASTO = {
    "id": GASTO_ID, "comercio": "Netflix.com", "descripcion": "Netflix",
    "monto_original": 9999.0, "moneda": "ARS", "fecha": "2026-08-10", "recurrente_id": None,
}
RECURRENTE = {
    "id": REC_ID, "descripcion": "Netflix", "frecuencia": "mensual",
    "proximo_vencimiento": "2026-08-12",
}


def _responder(data, gasto=GASTO, recurrentes=(RECURRENTE,)):
    """Simula el toque de un botón en un proceso que no recuerda nada."""
    with patch.object(matcher.queries, "obtener_gasto_por_id", return_value=gasto), \
         patch.object(matcher.queries, "obtener_recurrentes_activos", return_value=list(recurrentes)), \
         patch.object(matcher, "confirmar_vinculacion") as confirmar:
        texto = asyncio.run(matcher.procesar_callback(SimpleNamespace(data=data)))
    return texto, confirmar


@pytest.mark.unit
def test_la_clave_del_boton_entra_en_el_limite_de_telegram():
    """Telegram rechaza callback_data de más de 64 bytes."""
    data = f"mr:a:{matcher._empaquetar(GASTO_ID, REC_ID)}"
    assert len(data.encode()) <= 64
    assert matcher._desempaquetar(matcher._empaquetar(GASTO_ID, REC_ID)) == (GASTO_ID, REC_ID)


@pytest.mark.unit
def test_el_boton_funciona_despues_de_reiniciar_el_bot():
    """
    Bug real: la confirmación pendiente vivía en un dict en memoria. Con cada
    deploy-bot las preguntas sin contestar quedaban muertas: al tocar el botón
    respondía "ya fue procesada o expiró" y el gasto quedaba sin vincular.
    """
    texto, confirmar = _responder(f"mr:y:{matcher._empaquetar(GASTO_ID, REC_ID)}")

    assert "Vinculado" in texto
    confirmar.assert_called_once()
    args, kwargs = confirmar.call_args
    assert args[0] == GASTO_ID and args[1] == RECURRENTE
    # Los datos del pago salen del gasto guardado, no de la memoria del proceso.
    assert kwargs["comercio"] == "Netflix.com"
    assert kwargs["nuevo_monto"] == 9999.0
    assert kwargs["fecha_pago"] == "2026-08-10"
    assert kwargs["guardar_alias"] is False


@pytest.mark.unit
def test_recordar_siempre_guarda_el_alias():
    _, confirmar = _responder(f"mr:a:{matcher._empaquetar(GASTO_ID, REC_ID)}")
    assert confirmar.call_args.kwargs["guardar_alias"] is True
    assert confirmar.call_args.kwargs["confirmado_usuario"] is True


@pytest.mark.unit
def test_no_es_este_no_vincula():
    texto, confirmar = _responder(f"mr:n:{matcher._empaquetar(GASTO_ID, REC_ID)}")
    assert "no se vinculó" in texto
    confirmar.assert_not_called()


@pytest.mark.unit
def test_tocar_dos_veces_no_vincula_dos_veces():
    """Vincular avanza el próximo vencimiento: repetirlo lo correría dos meses."""
    ya_vinculado = {**GASTO, "recurrente_id": REC_ID}
    texto, confirmar = _responder(f"mr:y:{matcher._empaquetar(GASTO_ID, REC_ID)}", gasto=ya_vinculado)
    assert "ya está vinculado" in texto
    confirmar.assert_not_called()


@pytest.mark.unit
def test_gasto_borrado_no_vincula():
    texto, confirmar = _responder(f"mr:y:{matcher._empaquetar(GASTO_ID, REC_ID)}", gasto=None)
    assert "ya no existe" in texto
    confirmar.assert_not_called()


@pytest.mark.unit
def test_boton_del_formato_viejo_avisa_en_vez_de_romper():
    """Los mensajes ya enviados llevan la clave corta anterior ("3f2b8c1e:9a8b7c6d")."""
    texto, confirmar = _responder("mr:y:3f2b8c1e:9a8b7c6d")
    assert "expiró" in texto
    confirmar.assert_not_called()


# ──────────────────────────────────────────────
# Matching automático
# ──────────────────────────────────────────────

PLUS_ID = "ce4d699f-a60e-43c1-8659-da628693f4d0"
PEDIDOSYA_PLUS = {
    "id": PLUS_ID, "descripcion": "Pedidos Ya Plus", "monto_original": 4134.0,
    "moneda": "ARS", "frecuencia": "mensual", "dia_del_mes": None,
    "proximo_vencimiento": "2026-11-07",
}
PROPINA = {
    "id": "6b288d17-43bd-45da-b9d7-afe77adfc002", "comercio": "Dlo*Pedidosya Propina",
    "monto_original": 4000.0, "moneda": "ARS", "fecha": "2026-10-31",
}
CUOTA_PLUS = {
    "id": "7eabd282-2296-447c-b1a7-e4df371f41d2", "comercio": "Dlo*Pedidosya Plus",
    "monto_original": 4134.0, "moneda": "ARS", "fecha": "2026-11-07",
}


def _buscar(gasto, *, ya_cobrado_en_el_periodo, aliases=None, llm=0.0):
    """Corre el matcher con la base mockeada. Devuelve (candidato, mock del chequeo de período)."""
    aliases = {"dlo pedidosya plus": PLUS_ID} if aliases is None else aliases
    with patch.object(matcher.queries, "obtener_recurrentes_activos", return_value=[PEDIDOSYA_PLUS]), \
         patch.object(matcher.queries, "obtener_aliases_recurrentes", return_value=aliases), \
         patch.object(matcher.queries, "hay_gasto_vinculado_entre",
                      return_value=ya_cobrado_en_el_periodo) as periodo, \
         patch.object(matcher, "_score_llm", return_value=llm):
        return matcher.encontrar_candidato_db(gasto), periodo


@pytest.mark.unit
def test_una_propina_no_se_vincula_sola_al_recurrente_ya_cobrado_en_el_mes():
    """
    Bug real: el 31/10 una propina de PedidosYa ($4.000) se vinculó sola a
    PedidosYa Plus. El fuzzy contra el alias "dlo pedidosya plus" dio 90 por la
    subcadena "dlo pedidosya p", el monto cayó dentro del margen y, como el
    recurrente no tiene día fijo, la fecha no se miró: no importó que la cuota
    de octubre ya estuviera vinculada desde el 07/10. Un segundo cargo en el
    mismo período no se vincula sin preguntar.
    """
    candidato, periodo = _buscar(PROPINA, ya_cobrado_en_el_periodo=True)

    assert candidato is not None
    assert candidato.metodo == "usuario_pendiente"
    periodo.assert_called_once_with(PLUS_ID, "2026-10-01", "2026-10-31", excluir_gasto_id=PROPINA["id"])


@pytest.mark.unit
def test_el_cobro_del_mes_se_sigue_vinculando_solo():
    candidato, _ = _buscar(CUOTA_PLUS, ya_cobrado_en_el_periodo=False)
    assert candidato is not None
    assert candidato.metodo == "alias"


@pytest.mark.unit
def test_un_alias_tampoco_vincula_dos_veces_en_el_mismo_mes():
    """El alias se salta monto y fecha; el período es lo único que lo frena."""
    candidato, _ = _buscar(CUOTA_PLUS, ya_cobrado_en_el_periodo=True)
    assert candidato.metodo == "usuario_pendiente"


@pytest.mark.unit
def test_periodo_segun_frecuencia():
    assert matcher._periodo("2026-10-31", "mensual") == ("2026-10-01", "2026-10-31")
    assert matcher._periodo("2026-12-15", "mensual") == ("2026-12-01", "2026-12-31")
    assert matcher._periodo("2026-08-03", "semestral") == ("2026-07-01", "2026-12-31")
    assert matcher._periodo("2026-03-03", "semestral") == ("2026-01-01", "2026-06-30")
    assert matcher._periodo("2026-05-31", "anual") == ("2026-01-01", "2026-12-31")
    assert matcher._periodo("2026-11-11", "semanal") == ("2026-11-09", "2026-11-15")


@pytest.mark.unit
def test_el_vinculo_automatico_no_aprende_alias():
    """
    Bug real: al vincular la propina por fuzzy se guardó el alias
    "dlo pedidosya propina", y un alias se saltea monto y fecha: desde ahí toda
    propina de PedidosYa iba a caer en PedidosYa Plus sin que nadie lo
    confirmara. Solo aprende el botón "recordar siempre".
    """
    from bot import gmail_poller

    gasto = {**PROPINA}
    candidato = matcher.CandidatoMatch(recurrente=PEDIDOSYA_PLUS, confianza=0.9, metodo="fuzzy")

    class _Bot:
        async def send_message(self, **_):
            pass

    with patch.object(matcher, "encontrar_candidato_db", return_value=candidato), \
         patch.object(matcher, "confirmar_vinculacion") as confirmar:
        asyncio.run(gmail_poller._intentar_match_recurrente(_Bot(), 1, gasto))

    confirmar.assert_called_once()
    assert confirmar.call_args.kwargs["guardar_alias"] is False
