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


MAPFRE_ID = "21e8f7ea-6cae-4bed-b0b8-9930a898254f"
MAPFRE = {
    "id": MAPFRE_ID, "descripcion": "Mapfre Seguros", "monto_original": 100011.78,
    "moneda": "ARS", "frecuencia": "mensual", "dia_del_mes": None,
    "proximo_vencimiento": "2026-06-03",
}
MAPFRE_31_MAYO = {
    "id": "0d5b3a2e-1c4f-4e8a-9b7d-6f2e1a3c5b7d", "comercio": "Mapfre Seguros Sa",
    "monto_original": 104491.14, "moneda": "ARS", "fecha": "2026-05-31",
}


def _buscar(gasto, *, vinculados, recurrente=PEDIDOSYA_PLUS, aliases=None, llm=0.0):
    """
    Corre el matcher con la base mockeada. `vinculados` es cuántos gastos ya
    tiene el recurrente entre el período anterior y el actual.
    """
    aliases = {"dlo pedidosya plus": PLUS_ID, "mapfre seguros sa": MAPFRE_ID} if aliases is None else aliases
    with patch.object(matcher.queries, "obtener_recurrentes_activos", return_value=[recurrente]), \
         patch.object(matcher.queries, "obtener_aliases_recurrentes", return_value=aliases), \
         patch.object(matcher.queries, "contar_gastos_vinculados_entre",
                      return_value=vinculados) as conteo, \
         patch.object(matcher, "_score_llm", return_value=llm):
        return matcher.encontrar_candidato_db(gasto), conteo


@pytest.mark.unit
def test_una_propina_no_se_vincula_sola_al_recurrente_ya_cobrado_en_el_mes():
    """
    Bug real: el 31/10 una propina de PedidosYa ($4.000) se vinculó sola a
    PedidosYa Plus. El fuzzy contra el alias "dlo pedidosya plus" dio 90 por la
    subcadena "dlo pedidosya p", el monto cayó dentro del margen y, como el
    recurrente no tiene día fijo, la fecha no se miró. Septiembre y octubre ya
    tenían su cuota vinculada: no hay período libre donde imputarla, así que
    se pregunta.
    """
    candidato, conteo = _buscar(PROPINA, vinculados=2)

    assert candidato is not None
    assert candidato.metodo == "usuario_pendiente"
    # Mira el período anterior y el actual juntos.
    conteo.assert_called_once_with(PLUS_ID, "2026-09-01", "2026-10-31", excluir_gasto_id=PROPINA["id"])


@pytest.mark.unit
def test_un_debito_adelantado_ocupa_el_periodo_anterior_libre():
    """
    Caso real: Mapfre debitó el 03/05 y el 31/05, y los dos eran legítimos
    (el del 31 es la cuota de junio, adelantada). Abril estaba vacío, así que
    entre los dos períodos hay un solo cobro y el segundo se vincula solo.
    """
    candidato, conteo = _buscar(MAPFRE_31_MAYO, vinculados=1, recurrente=MAPFRE)

    assert candidato.metodo == "alias"
    conteo.assert_called_once_with(MAPFRE_ID, "2026-04-01", "2026-05-31", excluir_gasto_id=MAPFRE_31_MAYO["id"])


@pytest.mark.unit
def test_el_cobro_del_mes_se_sigue_vinculando_solo():
    candidato, _ = _buscar(CUOTA_PLUS, vinculados=1)
    assert candidato is not None
    assert candidato.metodo == "alias"


@pytest.mark.unit
def test_un_alias_tampoco_vincula_un_tercer_cobro():
    """El alias se salta monto y fecha; el conteo de períodos es lo único que lo frena."""
    candidato, _ = _buscar(CUOTA_PLUS, vinculados=2)
    assert candidato.metodo == "usuario_pendiente"


@pytest.mark.unit
def test_periodo_anterior_segun_frecuencia():
    assert matcher._periodo_anterior("2026-01-15", "mensual") == ("2025-12-01", "2025-12-31")
    assert matcher._periodo_anterior("2026-03-31", "mensual") == ("2026-02-01", "2026-02-28")
    assert matcher._periodo_anterior("2026-08-03", "semestral") == ("2026-01-01", "2026-06-30")
    assert matcher._periodo_anterior("2026-03-03", "semestral") == ("2025-07-01", "2025-12-31")
    assert matcher._periodo_anterior("2026-05-31", "anual") == ("2025-01-01", "2025-12-31")
    assert matcher._periodo_anterior("2026-11-11", "semanal") == ("2026-11-02", "2026-11-08")


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
