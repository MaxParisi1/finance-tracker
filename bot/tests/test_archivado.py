"""
Tests del archivado end-to-end de un documento suelto.

Invariante principal: el PDF SIEMPRE termina en Drive. El objetivo es registro
total, así que ningún documento se descarta por no encontrarle factura — se
archiva y se reporta como huérfano.
"""

from datetime import date
from unittest.mock import patch

import pytest

from bot.tools.archivado import archivar_documento
from bot.tools.documentos import TIPO_COMPROBANTE, TIPO_FACTURA, DocumentoIdentificado

HOY = date(2026, 8, 8)

SERVICIO = {"id": "srv-aysa", "slug": "aysa", "nombre": "AySA",
            "recurrente_id": "rec-aysa", "activo": True}

FACTURA = {"id": "fac-1", "monto": 30562.17, "moneda": "ARS",
           "vencimiento": "2026-08-13", "estado": "pendiente"}

RECURRENTE = {"id": "rec-aysa", "descripcion": "AySA",
              "categoria": "Hogar", "medio_pago": "transferencia"}

SUBIDO = {"file_id": "drv-1", "file_name": "2026-08-13_aysa_comprobante.pdf",
          "web_view_link": "https://drive/x", "folder_path": "AySA/2026/08 - Agosto"}


def doc(tipo=TIPO_COMPROBANTE, monto=30562.17, fecha=date(2026, 8, 7)):
    return DocumentoIdentificado(servicio=SERVICIO, tipo=tipo,
                                 identificador="1929557", monto=monto, fecha=fecha)


class Entorno:
    """Patchea todo el borde externo (Drive + DB) y expone los mocks."""

    def __init__(self, pendientes=None, recurrente=RECURRENTE, saldada=None):
        self._p = [
            patch("bot.tools.archivado.queries.obtener_facturas_pendientes",
                  return_value=pendientes if pendientes is not None else [FACTURA]),
            patch("bot.tools.archivado.queries.obtener_recurrente_por_id",
                  return_value=recurrente),
            patch("bot.tools.archivado.queries.marcar_factura_pagada",
                  return_value=saldada if saldada is not None else {"id": "fac-1"}),
            patch("bot.tools.archivado.queries.vincular_gasto_recurrente"),
            patch("bot.tools.archivado.queries.insertar_archivo_drive",
                  side_effect=lambda fila: {"id": "arch-1", **fila}),
            patch("bot.tools.archivado._subir_a_drive", return_value=SUBIDO),
            patch("bot.tools.gastos.guardar_gasto",
                  return_value={"id": "gasto-1", "monto_original": 30562.17}),
        ]

    def __enter__(self):
        (self.pendientes, self.recurrente, self.saldar, self.vincular,
         self.insertar_archivo, self.subir, self.guardar_gasto) = [p.start() for p in self._p]
        return self

    def __exit__(self, *a):
        for p in self._p:
            p.stop()


# ──────────────────────────────────────────────
# Comprobante con factura abierta: el caso principal
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_comprobante_archiva_registra_el_gasto_y_salda_la_factura():
    with Entorno() as env:
        r = archivar_documento(doc(), b"%PDF", hoy=HOY)

    assert r.factura["id"] == "fac-1"
    assert r.gasto["id"] == "gasto-1"
    assert r.aviso is None
    env.saldar.assert_called_once_with("fac-1", "gasto-1", "2026-08-07")

    fila = env.insertar_archivo.call_args[0][0]
    assert fila["factura_id"] == "fac-1"
    assert fila["gasto_id"] == "gasto-1"
    assert fila["tipo"] == TIPO_COMPROBANTE


@pytest.mark.unit
def test_el_monto_del_gasto_sale_de_la_factura_no_del_comprobante():
    """
    El comprobante de Personal Pay pierde los centavos al extraerse. La factura
    es la fuente autoritativa, así que el gasto se registra con SU monto.
    """
    with Entorno() as env:
        archivar_documento(doc(monto=30562.00), b"%PDF", hoy=HOY)

    assert env.guardar_gasto.call_args.kwargs["monto"] == pytest.approx(30562.17)


@pytest.mark.unit
def test_categoria_y_medio_de_pago_salen_del_recurrente_configurado():
    with Entorno() as env:
        archivar_documento(doc(), b"%PDF", hoy=HOY)

    kw = env.guardar_gasto.call_args.kwargs
    assert kw["categoria"] == "Hogar"
    assert kw["medio_pago"] == "transferencia"
    assert kw["descripcion"] == "AySA"


@pytest.mark.unit
def test_sin_recurrente_configurado_usa_defaults_sin_romper():
    with Entorno(recurrente=None) as env:
        r = archivar_documento(doc(), b"%PDF", hoy=HOY)

    assert r.gasto is not None
    env.vincular.assert_not_called()


@pytest.mark.unit
def test_el_pdf_se_archiva_en_el_mes_del_vencimiento_no_en_el_de_hoy():
    """Si mandás el comprobante tarde, igual cae en la carpeta correcta."""
    tarde = doc(fecha=date(2026, 9, 20))
    with Entorno() as env:
        archivar_documento(tarde, b"%PDF", hoy=date(2026, 9, 20))

    fecha_drive = env.subir.call_args[0][4]
    assert fecha_drive == date(2026, 8, 13)  # vencimiento de la factura


# ──────────────────────────────────────────────
# Factura suelta
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_factura_se_cuelga_de_la_factura_sin_crear_gasto():
    with Entorno() as env:
        r = archivar_documento(doc(tipo=TIPO_FACTURA), b"%PDF", hoy=HOY)

    assert r.gasto is None
    env.guardar_gasto.assert_not_called()
    env.saldar.assert_not_called()
    assert env.insertar_archivo.call_args[0][0]["factura_id"] == "fac-1"


# ──────────────────────────────────────────────
# Sin factura: se archiva igual
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_sin_factura_pendiente_igual_se_archiva_y_avisa():
    """Registro total: nunca se descarta un documento por no tener pareja."""
    with Entorno(pendientes=[]) as env:
        r = archivar_documento(doc(), b"%PDF", hoy=HOY)

    assert r.factura is None
    assert r.gasto is None
    assert "sin vincular" in r.aviso
    env.subir.assert_called_once()
    assert env.insertar_archivo.call_args[0][0]["factura_id"] is None


@pytest.mark.unit
def test_sin_factura_el_archivo_conserva_el_monto_leido():
    with Entorno(pendientes=[]) as env:
        archivar_documento(doc(monto=30562.17), b"%PDF", hoy=HOY)
    assert env.insertar_archivo.call_args[0][0]["monto"] == pytest.approx(30562.17)


# ──────────────────────────────────────────────
# Discrepancias y carreras
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_monto_discrepante_vincula_pero_lo_reporta():
    with Entorno() as env:
        r = archivar_documento(doc(monto=99999.0), b"%PDF", hoy=HOY)

    assert r.factura["id"] == "fac-1"
    assert "99.999" in r.aviso.replace(",", ".") or "99,999" in r.aviso
    assert r.gasto is not None  # se registra igual, con el monto de la factura


@pytest.mark.unit
def test_factura_ya_saldada_por_otra_via_se_reporta():
    """marcar_factura_pagada devuelve {} si otro proceso la saldó primero."""
    with Entorno(saldada={}) as env:
        r = archivar_documento(doc(), b"%PDF", hoy=HOY)
    assert "ya figuraba saldada" in r.aviso


@pytest.mark.unit
def test_comprobante_de_factura_ya_pagada_no_duplica_el_gasto():
    pagada = {**FACTURA, "estado": "pagada"}
    with Entorno(pendientes=[pagada]) as env:
        r = archivar_documento(doc(), b"%PDF", hoy=HOY)

    assert r.gasto is None
    env.guardar_gasto.assert_not_called()
    # El PDF igual queda colgado de la factura.
    assert env.insertar_archivo.call_args[0][0]["factura_id"] == "fac-1"


@pytest.mark.unit
def test_documento_sin_fecha_usa_hoy():
    with Entorno(pendientes=[]) as env:
        archivar_documento(doc(fecha=None), b"%PDF", hoy=HOY)
    assert env.subir.call_args[0][4] == HOY
