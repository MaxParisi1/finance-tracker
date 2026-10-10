"""
Tests del estado persistente del bot: qué mails quedaron sin procesar y cómo
terminó cada ciclo. Es lo que alimenta la bandeja "Requiere tu atención".
"""

from unittest.mock import patch

import pytest

from bot.tools import estado

MAIL = {"id": "m1", "subject": "Consumo con tu tarjeta"}


@pytest.mark.unit
def test_el_ciclo_guarda_los_mails_que_quedaron_sin_leer():
    estado.empezar_ciclo("Consumos")
    estado.anotar_atascado("Consumos", MAIL, "El lector no pudo extraer la transacción")

    with patch.object(estado.queries, "guardar_estado") as guardar:
        assert estado.cerrar_ciclo("Consumos", True) is True

    guardar.assert_called_once_with("poller:Consumos", {
        "ok": True,
        "atascados": [{"id": "m1", "asunto": "Consumo con tu tarjeta",
                       "motivo": "El lector no pudo extraer la transacción"}],
    })


@pytest.mark.unit
def test_un_mail_resuelto_desaparece_en_el_ciclo_siguiente():
    """Cada ciclo arranca de cero: si el reintento anduvo, no queda en la bandeja."""
    estado.empezar_ciclo("Consumos")
    estado.anotar_atascado("Consumos", MAIL, "x")
    estado.empezar_ciclo("Consumos")

    with patch.object(estado.queries, "guardar_estado") as guardar:
        estado.cerrar_ciclo("Consumos", True)

    assert guardar.call_args.args[1]["atascados"] == []


@pytest.mark.unit
def test_el_mismo_mail_no_se_anota_dos_veces():
    estado.empezar_ciclo("Consumos_visa")
    estado.anotar_atascado("Consumos_visa", MAIL, "a")
    estado.anotar_atascado("Consumos_visa", MAIL, "b")

    with patch.object(estado.queries, "guardar_estado") as guardar:
        estado.cerrar_ciclo("Consumos_visa", True)

    assert len(guardar.call_args.args[1]["atascados"]) == 1


@pytest.mark.unit
def test_si_la_base_falla_el_poller_sigue():
    """Guardar el estado es accesorio: no puede frenar el registro de gastos."""
    estado.empezar_ciclo("Facturas")
    with patch.object(estado.queries, "guardar_estado", side_effect=RuntimeError("caída")):
        assert estado.cerrar_ciclo("Facturas", False) is False
