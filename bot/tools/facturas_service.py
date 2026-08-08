"""
Persistencia de facturas parseadas.

Concentra las garantías que hacen que esto sea confiable:

  - Idempotencia doble: por email_message_id y por (servicio, vencimiento).
    Si el proceso muere entre insertar y marcar el mail como leído, el reintento
    no duplica.
  - Carrera contra el índice único: si dos ciclos insertan a la vez, el que
    pierde recupera la fila existente en vez de explotar.
  - Guardas de plausibilidad: un vencimiento fuera de ventana o un monto
    desproporcionado respecto del mes anterior NO se guardan; se levanta
    FacturaSospechosa para que el usuario confirme. Es la red que atrapa un
    regex que agarró el número equivocado.
  - Ante cualquier duda, no se escribe. Un dato faltante se arregla; un dato
    incorrecto contamina el histórico y no se nota hasta mucho después.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from bot.db import queries
from bot.tools.facturas import FacturaParseada

logger = logging.getLogger(__name__)

__all__ = [
    "ServicioDesconocido", "FacturaSospechosa", "ResultadoRegistro",
    "registrar_factura", "VENTANA_VTO_PASADO", "VENTANA_VTO_FUTURO", "FACTOR_SOSPECHA",
]

# Un vencimiento muy lejos de hoy casi siempre significa que el regex agarró
# otra fecha del mail (emisión, período, "válido hasta").
VENTANA_VTO_PASADO = timedelta(days=180)
VENTANA_VTO_FUTURO = timedelta(days=120)

# Salto máximo tolerado respecto de la última factura del mismo servicio antes
# de pedir confirmación. Generoso a propósito: en Argentina un servicio puede
# duplicarse mes a mes sin que sea un error. Un x10 no.
FACTOR_SOSPECHA = 10.0


class ServicioDesconocido(Exception):
    """El identificador no está registrado en servicios_identificadores."""


class FacturaSospechosa(Exception):
    """Los datos parsearon pero no son plausibles. No se guarda nada."""


@dataclass(frozen=True)
class ResultadoRegistro:
    factura: dict
    ya_existia: bool


def _validar_vencimiento(vencimiento: date, hoy: date) -> None:
    if vencimiento < hoy - VENTANA_VTO_PASADO:
        raise FacturaSospechosa(
            f"vencimiento {vencimiento} está más de {VENTANA_VTO_PASADO.days} días en el pasado"
        )
    if vencimiento > hoy + VENTANA_VTO_FUTURO:
        raise FacturaSospechosa(
            f"vencimiento {vencimiento} está más de {VENTANA_VTO_FUTURO.days} días en el futuro"
        )


def _validar_monto(monto: float, ultima: dict | None) -> None:
    if monto < 0:
        raise FacturaSospechosa(f"monto negativo: {monto}")

    if not ultima:
        return

    try:
        previo = float(ultima.get("monto") or 0)
    except (TypeError, ValueError):
        return

    if previo <= 0 or monto <= 0:
        return

    razon = max(monto / previo, previo / monto)
    if razon > FACTOR_SOSPECHA:
        raise FacturaSospechosa(
            f"monto {monto:,.2f} difiere x{razon:.0f} del anterior ({previo:,.2f}) — "
            f"revisá si el parser leyó bien los decimales"
        )


def _es_conflicto_unico(exc: Exception) -> bool:
    """
    True si el error viene de violar un índice único. Supabase/PostgREST no
    expone un tipo propio, así que se inspecciona el texto (23505 = unique_violation).
    """
    texto = str(exc).lower()
    return "23505" in texto or "duplicate key" in texto or "already exists" in texto


def registrar_factura(
    factura: FacturaParseada,
    email_message_id: str | None = None,
    hoy: date | None = None,
) -> ResultadoRegistro:
    """
    Persiste una factura parseada. Idempotente y seguro ante reintentos.

    Levanta ServicioDesconocido si el identificador no está registrado, y
    FacturaSospechosa si los datos no pasan las guardas de plausibilidad.
    """
    hoy = hoy or date.today()

    # 1. Idempotencia por mail, antes de cualquier otra cosa.
    if email_message_id:
        previa = queries.obtener_factura_por_email(email_message_id)
        if previa:
            logger.info("Mail %s ya generó la factura %s", email_message_id, previa.get("id"))
            return ResultadoRegistro(factura=previa, ya_existia=True)

    # 2. Ruteo. Se prefiere el identificador numérico; el slug es el fallback
    #    para expensas, cuyo mail no trae número de cuenta (ahí el remitente es
    #    el identificador). Sin servicio resuelto no se escribe nada.
    servicio = None
    if factura.identificador:
        servicio = queries.obtener_servicio_por_identificador(factura.identificador)
    if servicio is None:
        servicio = queries.obtener_servicio_por_slug(factura.servicio)
    if servicio is None:
        raise ServicioDesconocido(
            f"ni el identificador {factura.identificador!r} ni el slug "
            f"{factura.servicio!r} están registrados"
        )

    # 3. Guardas de plausibilidad.
    _validar_vencimiento(factura.vencimiento, hoy)
    _validar_monto(factura.monto, queries.obtener_ultima_factura(servicio["id"]))

    fila = {
        "servicio_id": servicio["id"],
        "monto": round(factura.monto, 2),
        "moneda": "ARS",
        "vencimiento": factura.vencimiento.isoformat(),
        "periodo_desde": factura.periodo_desde.isoformat() if factura.periodo_desde else None,
        "periodo_hasta": factura.periodo_hasta.isoformat() if factura.periodo_hasta else None,
        "nro_factura": factura.nro_factura,
        "email_message_id": email_message_id,
        "estado": "pendiente",
    }

    # 4. Insert tolerante a la carrera contra (servicio_id, vencimiento).
    try:
        creada = queries.insertar_factura(fila)
    except Exception as exc:
        if not _es_conflicto_unico(exc):
            raise
        existente = queries.obtener_factura_por_vencimiento(
            servicio["id"], fila["vencimiento"]
        )
        if existente is None:
            raise
        logger.info(
            "Factura de %s con vencimiento %s ya existía (id=%s)",
            servicio["slug"], fila["vencimiento"], existente.get("id"),
        )
        return ResultadoRegistro(factura=existente, ya_existia=True)

    return ResultadoRegistro(factura=creada, ya_existia=False)
