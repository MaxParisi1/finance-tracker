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
         patch.object(resumenes.matcher, "sugerir_recurrente", return_value={"id": "rec-mapfre"}), \
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


@pytest.mark.unit
def test_un_fijo_elegido_a_mano_se_aprende_como_alias():
    """
    Caso real: YouTube pasó a cobrarse como "GOOGLE *YouTubeP P1p8Hdgx USD 3,00"
    y el bot no lo sugirió. Si el usuario lo vincula a mano, es su confirmación:
    se guarda el alias para que el mes que viene se vincule solo.
    """
    q = _q()
    q.obtener_recurrentes_activos.return_value = [{"id": "rec-yt", "frecuencia": "mensual"}]
    with patch.object(resumenes, "queries", q), \
         patch.object(resumenes, "guardar_gasto", return_value={"id": "g"}), \
         patch.object(resumenes.matcher, "sugerir_recurrente", return_value=None), \
         patch.object(resumenes.matcher, "confirmar_vinculacion") as vincular:
        resumenes.cargar_movimiento(_mov(
            descripcion="GOOGLE *YouTubeP P1p8Hdgx USD 3,00", monto="3.00", moneda="USD", recurrente_id="rec-yt",
        ))

    assert vincular.call_args.kwargs["guardar_alias"] is True
    assert vincular.call_args.kwargs["confirmado_usuario"] is True


def _impuesto(id, descripcion, monto, moneda="ARS"):
    return {
        "id": id, "resumen_id": "r1", "seccion": "impuesto", "descripcion": descripcion,
        "monto": monto, "moneda": moneda, "categoria_sugerida": "Impuestos y comisiones",
        "resumenes_tarjeta": {"id": "r1", "cierre": "2026-10-22", "tarjetas": TARJETA},
    }


@pytest.mark.unit
def test_los_impuestos_de_un_resumen_van_en_un_solo_gasto():
    """Sellos, IVA e IIBB sueltos no aportan nada: un gasto por resumen, con el detalle en las notas."""
    q = _q()
    filas = [
        _impuesto("i1", "IMPUESTO DE SELLOS $", "20462.41"),
        _impuesto("i2", "IVA RG 4240 21%( 4578,00)", "961.38"),
        _impuesto("i3", "IIBB PERCEP-BSAS 2,00%( 4578,00)", "91.56"),
    ]
    with patch.object(resumenes, "queries", q), \
         patch.object(resumenes, "guardar_gasto", return_value={"id": "g-imp"}) as guardar:
        resumenes.cargar_impuestos(filas)

    guardar.assert_called_once()
    kw = guardar.call_args.kwargs
    assert (kw["monto"], kw["categoria"], kw["fecha"]) == (21515.35, "Impuestos y comisiones", "2026-10-22")
    assert kw["email_message_id"] == "resumen:r1:impuestos:ARS"
    assert "IMPUESTO DE SELLOS" in kw["notas"]
    assert q.actualizar_movimiento_resumen.call_count == 3


@pytest.mark.unit
def test_los_impuestos_cargados_dos_veces_no_duplican():
    q = _q(gasto_por_email={"id": "g-imp"})
    with patch.object(resumenes, "queries", q), patch.object(resumenes, "guardar_gasto") as guardar:
        resumenes.cargar_impuestos([_impuesto("i1", "IMPUESTO DE SELLOS $", "20462.41")])

    guardar.assert_not_called()
    q.actualizar_movimiento_resumen.assert_called_once_with("i1", {"estado": "cargado", "gasto_id": "g-imp"})


def _bonif(**overrides):
    base = {
        "id": "b1", "resumen_id": "r1", "seccion": "consumo", "cupon": "001015",
        "descripcion": "BONIF. CONSUMO OPENPAY*MILAGRANJAS", "monto": "-12003.73", "moneda": "ARS",
        "gasto_id": "g-milagranjas",
    }
    return {**base, **overrides}


@pytest.mark.unit
def test_la_bonificacion_se_resta_del_gasto_del_consumo():
    """Caso real: Milagranjas $45.076 con bonificación de $12.003,73 → queda lo que realmente se pagó."""
    q = _q()
    q.obtener_gasto_por_id.return_value = {
        "id": "g-milagranjas", "monto_original": 45076.0, "moneda": "ARS", "tipo_cambio": 1.0, "notas": None,
    }
    with patch.object(resumenes, "queries", q):
        resumenes.aplicar_bonificacion(_bonif())

    gasto_id, campos = q.actualizar_gasto.call_args.args
    assert gasto_id == "g-milagranjas"
    assert (campos["monto_original"], campos["monto_ars"]) == (33072.27, 33072.27)
    assert "[bonif:b1]" in campos["notas"]
    q.actualizar_movimiento_resumen.assert_called_once_with("b1", {"estado": "aplicada", "gasto_id": "g-milagranjas"})


@pytest.mark.unit
def test_la_bonificacion_no_se_descuenta_dos_veces():
    """Si el bot se cayó después de actualizar el gasto, la marca en las notas evita restarla de nuevo."""
    q = _q()
    q.obtener_gasto_por_id.return_value = {
        "id": "g-milagranjas", "monto_original": 33072.27, "moneda": "ARS", "tipo_cambio": 1.0,
        "notas": "Bonificación -12003.73 del resumen [bonif:b1]",
    }
    with patch.object(resumenes, "queries", q):
        resumenes.aplicar_bonificacion(_bonif())

    q.actualizar_gasto.assert_not_called()
    q.actualizar_movimiento_resumen.assert_called_once_with("b1", {"estado": "aplicada", "gasto_id": "g-milagranjas"})


@pytest.mark.unit
def test_la_bonificacion_de_un_consumo_no_cargado_vuelve_a_revisar():
    q = _q()
    q.movimiento_consumo_por_cupon.return_value = {"id": "c1", "estado": "falta", "gasto_id": None}
    with patch.object(resumenes, "queries", q):
        resumenes.aplicar_bonificacion(_bonif(gasto_id=None))

    q.actualizar_gasto.assert_not_called()
    q.actualizar_movimiento_resumen.assert_called_once_with("b1", {"estado": "bonificacion"})


@pytest.mark.unit
def test_el_ciclo_carga_el_consumo_antes_que_su_bonificacion():
    q = _q()
    q.resumenes_pendientes.return_value = []
    consumo = _mov(id="c1", seccion="consumo", monto="48290.25")
    bonif = _bonif(gasto_id=None)
    imp = _impuesto("i1", "IMPUESTO DE SELLOS $", "61.04")
    q.movimientos_a_cargar.return_value = [bonif, imp, consumo]
    orden = []
    with patch.object(resumenes, "queries", q), \
         patch.object(resumenes, "cargar_impuestos", side_effect=lambda f: orden.append("impuestos")), \
         patch.object(resumenes, "cargar_movimiento", side_effect=lambda m: orden.append(m["id"])), \
         patch.object(resumenes, "aplicar_bonificacion", side_effect=lambda m: orden.append(m["id"])):
        resumenes.procesar_ciclo()

    assert orden == ["impuestos", "c1", "b1"]
