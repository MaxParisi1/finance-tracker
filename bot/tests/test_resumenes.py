"""
Orquestación de la conciliación de resúmenes (bot ↔ web por Supabase).

Lo que se protege: que un resumen dudoso no deje nada a medias, que el mismo
resumen no se procese dos veces, y que cargar un movimiento no duplique el
gasto aunque el proceso se caiga a mitad de camino. La base y el storage están
mockeados.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from bot.tools import resumenes
from bot.tools.resumen_bbva import Movimiento, Resumen, ResumenInvalido

TARJETA = {"id": "t-visa", "sufijo": "1670", "nombre": "Visa Credito", "red": "visa", "tipo": "credito"}
FILA = {"id": "r1", "storage_path": "2026/r1.pdf"}


def _resumen(*movs):
    return Resumen(
        red="visa", producto="Visa Signature", cuenta="1077662388",
        cierre=date(2026, 10, 22), vencimiento=date(2026, 11, 4), cierre_anterior=date(2026, 9, 24),
        saldo_anterior={"ARS": Decimal(0)}, saldo_actual={"ARS": Decimal("117063.23")}, movimientos=list(movs),
    )


MAPFRE = Movimiento(
    seccion="consumo", fecha=date(2026, 9, 30), descripcion="MAPFRE SEGUROS0411417538070-004-000",
    monto=Decimal("117063.23"), moneda="ARS", cupon="004212",
)


def _q(**overrides):
    """Mock del módulo queries con valores por defecto de un caso feliz."""
    q = MagicMock()
    q.descargar_resumen.return_value = b"%PDF"
    q.tarjeta_por_cuenta.return_value = TARJETA
    q.otro_resumen_con_cierre.return_value = False
    q.gastos_entre.return_value = []
    q.gasto_por_email.return_value = None
    for k, v in overrides.items():
        getattr(q, k).return_value = v
    return q


@pytest.mark.unit
def test_un_resumen_que_no_cierra_queda_en_error_sin_movimientos():
    q = _q()
    with patch.object(resumenes, "queries", q), \
         patch.object(resumenes, "leer_resumen", side_effect=ResumenInvalido("En ARS: no da el saldo actual")):
        resumenes.procesar_resumen(FILA)

    q.reemplazar_movimientos_resumen.assert_not_called()
    campos = q.actualizar_resumen.call_args.args[1]
    assert campos["estado"] == "error"
    assert "no da el saldo actual" in campos["error"]


@pytest.mark.unit
def test_una_cuenta_desconocida_no_se_adivina():
    q = _q(tarjeta_por_cuenta=None)
    with patch.object(resumenes, "queries", q), patch.object(resumenes, "leer_resumen", return_value=_resumen(MAPFRE)):
        resumenes.procesar_resumen(FILA)

    q.reemplazar_movimientos_resumen.assert_not_called()
    assert "1077662388" in q.actualizar_resumen.call_args.args[1]["error"]


@pytest.mark.unit
def test_el_mismo_resumen_bajado_dos_veces_no_se_procesa_dos_veces():
    """Dos descargas del mismo resumen tienen bytes distintos: el sha no alcanza, se mira tarjeta + cierre."""
    q = _q(otro_resumen_con_cierre=True)
    with patch.object(resumenes, "queries", q), patch.object(resumenes, "leer_resumen", return_value=_resumen(MAPFRE)):
        resumenes.procesar_resumen(FILA)

    q.reemplazar_movimientos_resumen.assert_not_called()
    assert "ya estaba cargado" in q.actualizar_resumen.call_args.args[1]["error"]


@pytest.mark.unit
def test_un_faltante_lleva_categoria_y_recurrente_sugeridos():
    """
    Caso real: Mapfre falta en el resumen de octubre; se sugiere su recurrente
    sin preguntarle al LLM. El historial por comercio sugería "Hogar"; manda la
    categoría del fijo.
    """
    q = _q()
    rec = {"id": "rec-mapfre", "categoria": "Transporte"}
    with patch.object(resumenes, "queries", q), \
         patch.object(resumenes, "leer_resumen", return_value=_resumen(MAPFRE)), \
         patch.object(resumenes, "historial_comercio", return_value={"categoria_mas_frecuente": "Hogar"}), \
         patch.object(resumenes.matcher, "sugerir_recurrente", return_value=rec):
        resumenes.procesar_resumen(FILA)

    (fila,) = q.reemplazar_movimientos_resumen.call_args.args[1]
    assert (fila["estado"], fila["recurrente_id"], fila["categoria_sugerida"]) == ("falta", "rec-mapfre", "Transporte")
    campos = q.actualizar_resumen.call_args.args[1]
    assert (campos["estado"], campos["tarjeta_id"], campos["cierre"]) == ("procesado", "t-visa", "2026-10-22")


def _mov(**overrides):
    base = {
        "id": "m1", "descripcion": "MAPFRE SEGUROS0411417538070-004-000", "monto": "117063.23",
        "moneda": "ARS", "fecha": "2026-09-30", "cuota_actual": None, "cuotas_total": None,
        "categoria_sugerida": "Transporte", "recurrente_id": None,
        "resumenes_tarjeta": {"id": "r1", "cierre": "2026-10-22", "tarjetas": TARJETA},
    }
    return {**base, **overrides}


@pytest.mark.unit
def test_cargar_un_movimiento_crea_el_gasto_y_lo_vincula_sin_aprender_alias():
    q = _q()
    q.obtener_recurrentes_activos.return_value = [{"id": "rec-mapfre", "frecuencia": "mensual"}]
    with patch.object(resumenes, "queries", q), \
         patch.object(resumenes, "guardar_gasto", return_value={"id": "g-nuevo"}) as guardar, \
         patch.object(resumenes.matcher, "confirmar_vinculacion") as vincular:
        resumenes.cargar_movimiento(_mov(recurrente_id="rec-mapfre"))

    kw = guardar.call_args.kwargs
    assert (kw["monto"], kw["medio_pago"], kw["fecha"], kw["fuente"]) == (117063.23, "credito_ars", "2026-09-30", "resumen_tarjeta")
    assert kw["tarjeta"] == "Visa Credito 1670"
    assert kw["email_message_id"] == "resumen:m1"
    assert vincular.call_args.kwargs["guardar_alias"] is False
    q.actualizar_movimiento_resumen.assert_called_once_with("m1", {"estado": "cargado", "gasto_id": "g-nuevo"})


@pytest.mark.unit
def test_cargar_dos_veces_no_duplica_el_gasto():
    """Si el bot se cae entre crear el gasto y marcar el movimiento, el reintento lo encuentra."""
    q = _q(gasto_por_email={"id": "g-ya-creado"})
    with patch.object(resumenes, "queries", q), patch.object(resumenes, "guardar_gasto") as guardar:
        resumenes.cargar_movimiento(_mov())

    guardar.assert_not_called()
    q.actualizar_movimiento_resumen.assert_called_once_with("m1", {"estado": "cargado", "gasto_id": "g-ya-creado"})


@pytest.mark.unit
def test_sin_categoria_no_se_carga():
    q = _q()
    with patch.object(resumenes, "queries", q), patch.object(resumenes, "guardar_gasto") as guardar:
        resumenes.cargar_movimiento(_mov(categoria_sugerida=None))

    guardar.assert_not_called()
    q.actualizar_movimiento_resumen.assert_called_once_with("m1", {"estado": "falta"})


@pytest.mark.unit
def test_una_cuota_se_carga_con_la_fecha_del_periodo_y_no_la_de_la_compra():
    q = _q()
    with patch.object(resumenes, "queries", q), \
         patch.object(resumenes, "guardar_gasto", return_value={"id": "g"}) as guardar:
        resumenes.cargar_movimiento(_mov(fecha="2026-02-03", cuota_actual=9, cuotas_total=18, monto="37856.72"))

    kw = guardar.call_args.kwargs
    assert (kw["fecha"], kw["cuotas"], kw["cuota_actual"]) == ("2026-10-22", 18, 9)


@pytest.mark.unit
def test_un_error_inesperado_deja_el_resumen_en_error_y_sigue_con_los_demas():
    q = _q()
    q.resumenes_pendientes.return_value = [FILA, {"id": "r2", "storage_path": "x"}]
    q.movimientos_a_cargar.return_value = []
    with patch.object(resumenes, "queries", q), \
         patch.object(resumenes, "procesar_resumen", side_effect=[RuntimeError("boom"), None]) as procesar:
        resumenes.procesar_ciclo()

    assert procesar.call_count == 2
    assert q.actualizar_resumen.call_args.args[1]["estado"] == "error"
