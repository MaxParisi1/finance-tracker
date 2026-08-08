"""
Tests de los recordatorios.

Dos riesgos opuestos que hay que balancear: que no avise (y pagues con recargo)
y que avise de más (y dejes de leerlo, que termina siendo lo mismo). Los tests
fijan la cadencia exacta para que ningún cambio futuro la corra sin querer.
"""

from datetime import date

import pytest

from bot.tools.recordatorios import (
    TIPO_FALTA_COMPROBANTE, TIPO_FALTA_FACTURA, TIPO_VENCE, TIPO_VENCIDA,
    calcular_avisos, formatear_avisos,
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
