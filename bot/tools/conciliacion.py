"""
Conciliación de un documento suelto contra las facturas abiertas.

Recibe un DocumentoIdentificado (ya sabemos servicio y tipo) y decide a qué
factura corresponde, para que el PDF quede archivado en el lugar correcto y,
si es un comprobante, quede registrado el pago.

Criterio de selección, en este orden:
  1. Una sola factura pendiente del servicio → es esa. El monto solo se usa
     como chequeo de cordura, no como requisito: los comprobantes de Personal
     Pay pierden los centavos al extraerse, y pagar con recargo del 2°
     vencimiento cambia el importe. Exigir igualdad exacta rompería casos
     legítimos.
  2. Varias pendientes → gana la más cercana en monto, siempre que haya una
     sola dentro de la tolerancia. Si hay empate, se pregunta.
  3. Ninguna pendiente → no se inventa: se archiva el PDF igual (no perder el
     documento nunca) y se avisa que quedó sin vincular.
"""

import logging
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)

__all__ = [
    "ConciliacionAmbigua", "SeleccionFactura", "elegir_factura",
    "TOLERANCIA_RELATIVA", "TOLERANCIA_MINIMA",
]

# Un comprobante puede diferir del importe de la factura por recargos de 2°
# vencimiento o por centavos perdidos en la extracción del PDF.
TOLERANCIA_RELATIVA = 0.05   # 5%
TOLERANCIA_MINIMA = 1.0      # pesos


class ConciliacionAmbigua(Exception):
    """Más de una factura encaja. Preguntar antes que elegir mal."""


@dataclass(frozen=True)
class SeleccionFactura:
    factura: dict | None
    motivo: str
    coincide_monto: bool


def _tolerancia(monto: float) -> float:
    return max(abs(monto) * TOLERANCIA_RELATIVA, TOLERANCIA_MINIMA)


def _monto_de(factura: dict) -> float | None:
    try:
        return float(factura.get("monto"))
    except (TypeError, ValueError):
        return None


def elegir_factura(
    pendientes: list[dict],
    monto: float | None = None,
    fecha: date | None = None,
) -> SeleccionFactura:
    """
    Elige la factura que corresponde a un documento.

    `monto` puede ser None (el PDF no lo tenía legible): en ese caso se resuelve
    solo si hay una única factura pendiente.
    """
    if not pendientes:
        return SeleccionFactura(None, "no hay facturas pendientes de este servicio", False)

    if len(pendientes) == 1:
        unica = pendientes[0]
        esperado = _monto_de(unica)
        coincide = (
            monto is not None and esperado is not None
            and abs(monto - esperado) <= _tolerancia(esperado)
        )
        if monto is not None and esperado is not None and not coincide:
            logger.info(
                "Única factura pendiente ($%s) difiere del documento ($%s); se vincula igual",
                esperado, monto,
            )
        return SeleccionFactura(unica, "única factura pendiente del servicio", coincide)

    if monto is None:
        raise ConciliacionAmbigua(
            f"hay {len(pendientes)} facturas pendientes y el documento no trae monto legible"
        )

    candidatas = [
        f for f in pendientes
        if (esperado := _monto_de(f)) is not None
        and abs(monto - esperado) <= _tolerancia(esperado)
    ]

    if not candidatas:
        raise ConciliacionAmbigua(
            f"ninguna de las {len(pendientes)} facturas pendientes coincide con ${monto:,.2f}"
        )
    if len(candidatas) > 1:
        montos = ", ".join(f"${_monto_de(f):,.2f}" for f in candidatas)
        raise ConciliacionAmbigua(
            f"${monto:,.2f} podría corresponder a varias facturas ({montos})"
        )

    return SeleccionFactura(candidatas[0], "coincide por monto entre varias pendientes", True)
