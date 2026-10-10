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
