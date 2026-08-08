"""
Tests de registrar_factura: idempotencia, carreras y guardas de plausibilidad.

Lo que se protege acá es la integridad del histórico. Un dato faltante se
arregla después; un monto mal cargado contamina meses de estadísticas y no se
nota hasta que ya no se sabe cuál era el número real.
"""

from datetime import date
from unittest.mock import patch

import pytest

from bot.tools.facturas import FacturaParseada
from bot.tools.facturas_service import (
    FACTOR_SOSPECHA, FacturaSospechosa, ServicioDesconocido,
    registrar_factura,
)

HOY = date(2026, 8, 7)

SERVICIO = {"id": "srv-edenor", "slug": "edenor", "nombre": "Edenor", "activo": True}


def factura(**over) -> FacturaParseada:
    base = dict(
        servicio="edenor",
        identificador="5255064586",
        monto=13405.84,
        vencimiento=date(2026, 8, 15),
    )
    return FacturaParseada(**{**base, **over})


def _patchear(servicio=SERVICIO, por_email=None, ultima=None, por_vto=None,
              insert=None, por_slug=None):
    """Arma el set de patches sobre queries con valores por defecto sanos."""
    return [
        patch("bot.tools.facturas_service.queries.obtener_servicio_por_identificador",
              return_value=servicio),
        patch("bot.tools.facturas_service.queries.obtener_servicio_por_slug",
              return_value=por_slug),
        patch("bot.tools.facturas_service.queries.obtener_factura_por_email",
              return_value=por_email),
        patch("bot.tools.facturas_service.queries.obtener_ultima_factura",
              return_value=ultima),
        patch("bot.tools.facturas_service.queries.obtener_factura_por_vencimiento",
              return_value=por_vto),
        patch("bot.tools.facturas_service.queries.insertar_factura",
              **({"side_effect": insert} if isinstance(insert, Exception) else
                 {"return_value": insert or {"id": "fac-1"}})),
    ]


class _Contexto:
    """Aplica varios patches y expone los mocks por nombre corto."""

    def __init__(self, **kw):
        self._patches = _patchear(**kw)

    def __enter__(self):
        self.mocks = [p.start() for p in self._patches]
        (self.servicio, self.por_slug, self.por_email,
         self.ultima, self.por_vto, self.insert) = self.mocks
        return self

    def __exit__(self, *a):
        for p in self._patches:
            p.stop()


# ──────────────────────────────────────────────
# Camino feliz
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_registra_una_factura_nueva():
    with _Contexto() as ctx:
        res = registrar_factura(factura(), email_message_id="msg-1", hoy=HOY)

    assert res.ya_existia is False
    fila = ctx.insert.call_args[0][0]
    assert fila["servicio_id"] == "srv-edenor"
    assert fila["monto"] == pytest.approx(13405.84)
    assert fila["vencimiento"] == "2026-08-15"
    assert fila["estado"] == "pendiente"
    assert fila["email_message_id"] == "msg-1"


@pytest.mark.unit
def test_guarda_periodo_y_numero_de_factura():
    f = factura(
        periodo_desde=date(2026, 6, 4),
        periodo_hasta=date(2026, 7, 3),
        nro_factura="0111B20261385",
    )
    with _Contexto() as ctx:
        registrar_factura(f, hoy=HOY)

    fila = ctx.insert.call_args[0][0]
    assert fila["periodo_desde"] == "2026-06-04"
    assert fila["periodo_hasta"] == "2026-07-03"
    assert fila["nro_factura"] == "0111B20261385"


@pytest.mark.unit
def test_monto_se_redondea_a_dos_decimales():
    with _Contexto() as ctx:
        registrar_factura(factura(monto=13405.8449), hoy=HOY)
    assert ctx.insert.call_args[0][0]["monto"] == 13405.84


# ──────────────────────────────────────────────
# Idempotencia
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_mail_ya_procesado_no_reinserta():
    """Si el proceso murió después de insertar, el reintento no duplica."""
    previa = {"id": "fac-previa", "estado": "pendiente"}
    with _Contexto(por_email=previa) as ctx:
        res = registrar_factura(factura(), email_message_id="msg-1", hoy=HOY)

    assert res.ya_existia is True
    assert res.factura["id"] == "fac-previa"
    ctx.insert.assert_not_called()


@pytest.mark.unit
def test_idempotencia_se_chequea_antes_de_resolver_el_servicio():
    """Evita trabajo (y falsos ServicioDesconocido) sobre mails ya procesados."""
    with _Contexto(servicio=None, por_email={"id": "fac-previa"}) as ctx:
        res = registrar_factura(factura(), email_message_id="msg-1", hoy=HOY)

    assert res.ya_existia is True
    ctx.servicio.assert_not_called()


@pytest.mark.unit
def test_carrera_por_vencimiento_duplicado_devuelve_la_existente():
    """Dos ciclos insertando a la vez: el que pierde recupera, no explota."""
    existente = {"id": "fac-existente"}
    conflicto = Exception('duplicate key value violates unique constraint (23505)')
    with _Contexto(insert=conflicto, por_vto=existente):
        res = registrar_factura(factura(), hoy=HOY)

    assert res.ya_existia is True
    assert res.factura["id"] == "fac-existente"


@pytest.mark.unit
def test_error_de_insert_que_no_es_conflicto_se_propaga():
    """Un fallo de red no debe disfrazarse de 'ya existía'."""
    with _Contexto(insert=ConnectionError("supabase caído")):
        with pytest.raises(ConnectionError):
            registrar_factura(factura(), hoy=HOY)


@pytest.mark.unit
def test_conflicto_sin_fila_recuperable_se_propaga():
    """Si dice duplicado pero no aparece la fila, algo más está mal: no tragar."""
    conflicto = Exception("duplicate key")
    with _Contexto(insert=conflicto, por_vto=None):
        with pytest.raises(Exception, match="duplicate key"):
            registrar_factura(factura(), hoy=HOY)


# ──────────────────────────────────────────────
# Ruteo
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_identificador_no_registrado_no_escribe():
    with _Contexto(servicio=None) as ctx:
        with pytest.raises(ServicioDesconocido, match="5255064586"):
            registrar_factura(factura(), hoy=HOY)
    ctx.insert.assert_not_called()


# ──────────────────────────────────────────────
# Guardas de plausibilidad
# ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("vencimiento, motivo", [
    (date(2025, 1, 1), "muy en el pasado"),
    (date(2027, 6, 1), "muy en el futuro"),
])
def test_vencimiento_fuera_de_ventana_no_se_guarda(vencimiento, motivo):
    """Un regex que agarró la fecha de emisión o del período tiene que romper."""
    with _Contexto() as ctx:
        with pytest.raises(FacturaSospechosa):
            registrar_factura(factura(vencimiento=vencimiento), hoy=HOY)
    ctx.insert.assert_not_called(), motivo


@pytest.mark.unit
def test_vencimiento_reciente_en_el_pasado_si_se_acepta():
    """Una factura vencida hace poco es normal (llegó tarde o se pagó tarde)."""
    with _Contexto():
        res = registrar_factura(factura(vencimiento=date(2026, 7, 20)), hoy=HOY)
    assert res.ya_existia is False


@pytest.mark.unit
def test_monto_desproporcionado_no_se_guarda():
    """
    Ésta es la red que atrapa el bug de decimales: si el parser leyera
    13.405,84 como 1.340.584, el salto x100 lo frena antes de la base.
    """
    with _Contexto(ultima={"monto": 13405.84}) as ctx:
        with pytest.raises(FacturaSospechosa, match="decimales"):
            registrar_factura(factura(monto=1340584.0), hoy=HOY)
    ctx.insert.assert_not_called()


@pytest.mark.unit
def test_aumento_grande_pero_plausible_se_acepta():
    """Con inflación, que un servicio se triplique no es un error."""
    with _Contexto(ultima={"monto": 13405.84}):
        res = registrar_factura(factura(monto=40217.52), hoy=HOY)
    assert res.ya_existia is False


@pytest.mark.unit
def test_caida_desproporcionada_tambien_se_frena():
    """El error simétrico: leer 5.266,75 como 52,66."""
    with _Contexto(ultima={"monto": 5266.75}):
        with pytest.raises(FacturaSospechosa):
            registrar_factura(factura(monto=52.66), hoy=HOY)


@pytest.mark.unit
def test_primera_factura_del_servicio_no_tiene_con_que_comparar():
    with _Contexto(ultima=None):
        res = registrar_factura(factura(monto=999999.0), hoy=HOY)
    assert res.ya_existia is False


@pytest.mark.unit
@pytest.mark.parametrize("previo", [0, None, "", "roto"])
def test_monto_anterior_invalido_no_rompe_el_registro(previo):
    """Una factura anterior con monto corrupto no puede bloquear la nueva."""
    with _Contexto(ultima={"monto": previo}):
        res = registrar_factura(factura(), hoy=HOY)
    assert res.ya_existia is False


@pytest.mark.unit
def test_monto_cero_es_valido():
    """MetroGAS factura $0,00 cuando no hay consumo; es un dato real."""
    with _Contexto(ultima={"monto": 5266.75}):
        res = registrar_factura(factura(monto=0.0), hoy=HOY)
    assert res.ya_existia is False


@pytest.mark.unit
def test_monto_negativo_no_se_guarda():
    with _Contexto():
        with pytest.raises(FacturaSospechosa, match="negativo"):
            registrar_factura(factura(monto=-100.0), hoy=HOY)


@pytest.mark.unit
def test_factor_de_sospecha_es_el_limite_exacto():
    """Justo en el borde pasa; apenas arriba, no."""
    base = 10000.0
    with _Contexto(ultima={"monto": base}):
        registrar_factura(factura(monto=base * FACTOR_SOSPECHA), hoy=HOY)
    with _Contexto(ultima={"monto": base}):
        with pytest.raises(FacturaSospechosa):
            registrar_factura(factura(monto=base * FACTOR_SOSPECHA * 1.01), hoy=HOY)


# ──────────────────────────────────────────────
# Ruteo por slug (expensas: el mail no trae número de cuenta)
# ──────────────────────────────────────────────

SERVICIO_EXPENSAS = {"id": "srv-consorcio", "slug": "consorcio_gallo",
                     "nombre": "Consorcio Gallo", "activo": True,
                     "unidad_funcional": "255"}


@pytest.mark.unit
def test_expensas_sin_identificador_rutea_por_slug():
    f = factura(servicio="consorcio_gallo", identificador="", monto=258198.55,
                vencimiento=date(2026, 8, 10))
    with _Contexto(servicio=None, por_slug=SERVICIO_EXPENSAS) as ctx:
        res = registrar_factura(f, hoy=HOY)

    assert res.ya_existia is False
    assert ctx.insert.call_args[0][0]["servicio_id"] == "srv-consorcio"


@pytest.mark.unit
def test_el_identificador_tiene_prioridad_sobre_el_slug():
    """Si el número de cuenta resuelve, no se cae al slug (que es más débil)."""
    with _Contexto(servicio=SERVICIO, por_slug=SERVICIO_EXPENSAS) as ctx:
        registrar_factura(factura(), hoy=HOY)
    assert ctx.insert.call_args[0][0]["servicio_id"] == "srv-edenor"
    ctx.por_slug.assert_not_called()


@pytest.mark.unit
def test_sin_identificador_ni_slug_conocidos_no_escribe():
    with _Contexto(servicio=None, por_slug=None) as ctx:
        with pytest.raises(ServicioDesconocido):
            registrar_factura(factura(), hoy=HOY)
    ctx.insert.assert_not_called()
