"""
Tests de las funciones de negocio críticas del bot.

Ejecutar desde la raíz del proyecto:
    cd bot && python -m pytest tests/ -v

No requieren conexión a Supabase ni a Gemini: todo se mockea.
"""

import pytest
from datetime import date
from unittest.mock import patch, MagicMock


# ──────────────────────────────────────────────
# _siguiente_mes
# ──────────────────────────────────────────────

from bot.tools.gastos import _siguiente_mes


def test_siguiente_mes_normal():
    assert _siguiente_mes(date(2024, 3, 15)) == date(2024, 4, 15)


def test_siguiente_mes_diciembre():
    assert _siguiente_mes(date(2024, 12, 10)) == date(2025, 1, 10)


def test_siguiente_mes_ajuste_dia_31():
    # 31 de enero → 28 de febrero (no 31)
    assert _siguiente_mes(date(2024, 1, 31)) == date(2024, 2, 29)  # 2024 es bisiesto


def test_siguiente_mes_ajuste_dia_30_febrero():
    assert _siguiente_mes(date(2024, 1, 30)) == date(2024, 2, 29)


# ──────────────────────────────────────────────
# guardar_gasto — lógica ARS
# ──────────────────────────────────────────────

GASTO_INSERTAR_MOCK = {
    "id": "uuid-123",
    "descripcion": "Supermercado",
    "monto_original": 5000.0,
    "monto_ars": 5000.0,
    "moneda": "ARS",
    "categoria": "Alimentación",
    "medio_pago": "debito",
    "fecha": "2024-03-15",
    "fuente": "telegram_texto",
    "cuotas": 1,
    "cuota_actual": 1,
}


@patch("bot.tools.gastos.queries.insertar_gasto", return_value=GASTO_INSERTAR_MOCK)
def test_guardar_gasto_ars(mock_insert):
    from bot.tools.gastos import guardar_gasto

    resultado = guardar_gasto(
        descripcion="Supermercado",
        monto=5000.0,
        moneda="ARS",
        categoria="Alimentación",
        medio_pago="debito",
        fecha="2024-03-15",
    )

    assert resultado["id"] == "uuid-123"
    assert resultado["monto_ars"] == 5000.0
    mock_insert.assert_called_once()

    call_args = mock_insert.call_args[0][0]
    assert call_args["monto_ars"] == 5000.0
    assert call_args["tipo_cambio"] == 1.0
    assert call_args["tipo_cambio_tipo"] == "n/a"


# ──────────────────────────────────────────────
# guardar_gasto — lógica USD con conversión
# ──────────────────────────────────────────────

GASTO_USD_MOCK = {**GASTO_INSERTAR_MOCK, "moneda": "USD", "monto_original": 100.0, "monto_ars": 120000.0}


@patch("bot.tools.gastos.queries.insertar_gasto", return_value=GASTO_USD_MOCK)
@patch("bot.tools.gastos.convertir_usd_a_ars", return_value={
    "monto_ars": 120000.0,
    "tipo_cambio": 1200.0,
    "tipo_cambio_tipo": "blue",
})
def test_guardar_gasto_usd(mock_conversion, mock_insert):
    from bot.tools.gastos import guardar_gasto

    resultado = guardar_gasto(
        descripcion="Netflix",
        monto=100.0,
        moneda="USD",
        categoria="Entretenimiento",
        medio_pago="credito_usd",
    )

    mock_conversion.assert_called_once_with(100.0, "blue")
    call_args = mock_insert.call_args[0][0]
    assert call_args["monto_ars"] == 120000.0
    assert call_args["tipo_cambio"] == 1200.0
    assert call_args["tipo_cambio_tipo"] == "blue"


# ──────────────────────────────────────────────
# guardar_gasto — validación moneda inválida
# ──────────────────────────────────────────────

def test_guardar_gasto_moneda_invalida():
    from bot.tools.gastos import guardar_gasto

    with pytest.raises(ValueError, match="Moneda inválida"):
        guardar_gasto(
            descripcion="Test",
            monto=100.0,
            moneda="EUR",
            categoria="Otros",
            medio_pago="efectivo_ars",
        )


# ──────────────────────────────────────────────
# guardar_gasto — auto-expansión de cuotas
# ──────────────────────────────────────────────

@patch("bot.tools.gastos.queries.insertar_gasto", return_value=GASTO_INSERTAR_MOCK)
def test_guardar_gasto_cuotas_genera_registros(mock_insert):
    from bot.tools.gastos import guardar_gasto

    guardar_gasto(
        descripcion="Notebook",
        monto=600000.0,
        moneda="ARS",
        categoria="Tecnología",
        medio_pago="credito_ars",
        fecha="2024-03-01",
        cuotas=3,
    )

    # 1 cuota principal + 2 cuotas adicionales = 3 llamadas total
    assert mock_insert.call_count == 3

    # Verificar fechas de las cuotas 2 y 3
    calls = [c[0][0] for c in mock_insert.call_args_list]
    assert calls[0]["fecha"] == "2024-03-01"
    assert calls[0]["cuota_actual"] == 1
    assert calls[1]["fecha"] == "2024-04-01"
    assert calls[1]["cuota_actual"] == 2
    assert calls[2]["fecha"] == "2024-05-01"
    assert calls[2]["cuota_actual"] == 3


# ──────────────────────────────────────────────
# eliminar_gasto — soft delete
# ──────────────────────────────────────────────

@patch("bot.tools.gastos.queries.eliminar_gasto", return_value=True)
def test_eliminar_gasto(mock_eliminar):
    from bot.tools.gastos import eliminar_gasto

    resultado = eliminar_gasto("uuid-456")

    mock_eliminar.assert_called_once_with("uuid-456")
    assert resultado == {"eliminado": True, "id": "uuid-456"}
