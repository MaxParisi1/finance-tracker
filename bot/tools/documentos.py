"""
Identificación de un PDF suelto: el usuario lo comparte al bot sin decir nada y
hay que deducir de qué servicio es, si es factura o comprobante, y a qué factura
abierta corresponde.

Todo determinístico. El ruteo va por identificador numérico (cuenta, cliente,
referente, CBU) buscado dentro del texto del PDF, nunca por nombre del emisor ni
por dirección: los proveedores escriben el nombre de mil formas y discrepan
hasta en la altura de la calle.

Clave de diseño: el ruteo es AGNÓSTICO DE LA PLATAFORMA DE PAGO. El número de
cuenta de AySA aparece en un comprobante de Mercado Pago, de Rapipago o del
home banking, porque es lo que se tipea para pagar en cualquier lado. Si cambia
la plataforma, el ruteo sigue funcionando; a lo sumo falla la lectura del monto,
que degrada a una confirmación del usuario.
"""

import io
import logging
import re
from dataclasses import dataclass

from bot.db import queries
from bot.tools.montos import MontoInvalido, parse_fecha_ar, parse_monto_ar

logger = logging.getLogger(__name__)

__all__ = [
    "DocumentoIdentificado", "DocumentoNoIdentificado", "TIPO_FACTURA",
    "TIPO_COMPROBANTE", "aplanar", "detectar_tipo", "identificar_servicio",
    "extraer_texto_pdf", "identificar_documento",
]

TIPO_FACTURA = "factura"
TIPO_COMPROBANTE = "comprobante"

# Marcadores de tipo, tomados de los documentos reales. Los de comprobante son
# más distintivos porque una factura no habla nunca en pasado ("Pagaste").
_MARCAS_COMPROBANTE = (
    "comprobante de pago", "pagaste", "transferiste a", "forma de pago",
    "medio de pago", "nro. de operación", "n.° de operación", "número de transacción",
    "persona que pagó", "cuenta de origen",
)
_MARCAS_FACTURA = (
    "liquidacion de servicios", "liquidación de servicios", "liquidaciondeservicios",
    "total a pagar", "totalapagar", "fecha de emisión", "fechadeemisión",
    "período de liquidación", "resumen de servicios", "segundo vencimiento",
    "2°.vencimiento", "2° vencimiento",
)


class DocumentoNoIdentificado(Exception):
    """No se pudo determinar el servicio o el tipo. Hay que preguntarle al usuario."""


@dataclass(frozen=True)
class DocumentoIdentificado:
    servicio: dict
    tipo: str
    identificador: str
    monto: float | None = None
    fecha: object | None = None  # datetime.date


def aplanar(texto: str) -> str:
    """
    Normaliza para buscar identificadores: saca espacios, puntos y guiones para
    que 'Cuenta 5 255 064 586' y '5255064586' colapsen al mismo string.
    """
    return re.sub(r"[\s.\-]", "", texto or "")


def detectar_tipo(texto: str) -> str:
    """
    Factura o comprobante, por marcadores. Si ninguno gana con claridad se
    levanta la excepción: preguntar es barato, archivar mal es caro.
    """
    bajo = texto.lower()
    comprobante = sum(1 for m in _MARCAS_COMPROBANTE if m in bajo)
    factura = sum(1 for m in _MARCAS_FACTURA if m in bajo)

    if comprobante == 0 and factura == 0:
        raise DocumentoNoIdentificado("no reconocí si es factura o comprobante")
    if comprobante == factura:
        raise DocumentoNoIdentificado(
            f"ambiguo: {comprobante} marcas de comprobante y {factura} de factura"
        )
    return TIPO_COMPROBANTE if comprobante > factura else TIPO_FACTURA


def identificar_servicio(texto: str, identificadores: list[dict]) -> dict:
    """
    Busca los identificadores conocidos dentro del texto aplanado.

    Se compara por substring (no igualdad) porque el número puede venir embebido
    en una línea de código de barras. Si matchea más de un servicio se levanta
    la excepción en vez de elegir: un archivo mal ruteado es peor que preguntar.
    """
    plano = aplanar(texto)
    if not plano:
        raise DocumentoNoIdentificado("el PDF no tiene texto extraíble")

    encontrados = {}
    for ident in identificadores:
        valor = ident["valor"]
        if valor and valor in plano:
            slug = ident["servicio"]["slug"]
            # Ante varios identificadores del mismo servicio, gana el más largo
            # (menos chance de ser una coincidencia espuria).
            previo = encontrados.get(slug)
            if previo is None or len(valor) > len(previo["valor"]):
                encontrados[slug] = ident

    if not encontrados:
        raise DocumentoNoIdentificado(
            "ningún identificador conocido aparece en el documento"
        )
    if len(encontrados) > 1:
        slugs = ", ".join(sorted(encontrados))
        raise DocumentoNoIdentificado(f"coincide con varios servicios: {slugs}")

    return next(iter(encontrados.values()))


def _primer_monto(texto: str) -> float | None:
    """
    Monto del documento. Los comprobantes de Mercado Pago lo ponen arriba de
    todo ('$ 13.40584'), así que alcanza con el primer monto grande del texto.
    Devuelve None si no hay: el caller pide confirmación en vez de inventar.
    """
    for m in re.finditer(r"\$\s*([\d.\s]+(?:,\d+)?)", texto):
        try:
            valor = parse_monto_ar(m.group(1))
        except MontoInvalido:
            continue
        if valor > 0:
            return valor
    return None


_FECHA = r"\d{1,2}\s*/\s*(?:[a-záéíóú]{3,}|\d{1,2})\s*/\s*\d{2,4}"

# Etiquetas que preceden a la fecha que nos interesa, por orden de preferencia.
# Sin esto se agarra la primera fecha del PDF, que en las facturas suele ser el
# "Inicio de actividades" de la empresa (AySA: 2006, MetroGAS: 1992).
_ETIQUETAS_FECHA = (
    r"vencimiento[:\s]*", r"vence(?:\s+el)?[:\s]*", r"fecha\s+de\s+pago[:\s]*", r"fecha[:\s]*",
)

# Una fecha de este circuito no puede estar a años de hoy.
_MARGEN_ANIOS = 3


def _fecha_documento(texto: str, hoy: object | None = None) -> object | None:
    """
    Fecha del documento, priorizando la que sigue a una etiqueta conocida y
    descartando las implausibles. Devuelve None antes que una fecha inventada.
    """
    from datetime import date as _date

    hoy = hoy or _date.today()

    def _plausible(cruda: str):
        try:
            f = parse_fecha_ar(cruda)
        except MontoInvalido:
            return None
        return f if abs(f.year - hoy.year) <= _MARGEN_ANIOS else None

    for etiqueta in _ETIQUETAS_FECHA:
        for m in re.finditer(etiqueta + f"({_FECHA})", texto, re.I):
            fecha = _plausible(m.group(1))
            if fecha:
                return fecha

    for m in re.finditer(f"({_FECHA})", texto, re.I):
        fecha = _plausible(m.group(1))
        if fecha:
            return fecha

    return None


def extraer_texto_pdf(pdf_bytes: bytes) -> str:
    """Texto de todas las páginas. pdfplumber se importa acá para no pagarlo al arrancar."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def identificar_documento(pdf_bytes: bytes) -> DocumentoIdentificado:
    """
    Identifica un PDF suelto. Levanta DocumentoNoIdentificado si algo no cierra;
    el caller le pregunta al usuario en vez de adivinar.
    """
    texto = extraer_texto_pdf(pdf_bytes)
    if not texto.strip():
        raise DocumentoNoIdentificado(
            "el PDF no tiene texto (¿es un escaneo?). Mandalo como foto para leerlo con visión."
        )

    ident = identificar_servicio(texto, queries.listar_identificadores_servicios())
    tipo = detectar_tipo(texto)

    doc = DocumentoIdentificado(
        servicio=ident["servicio"],
        tipo=tipo,
        identificador=ident["valor"],
        monto=_primer_monto(texto),
        fecha=_fecha_documento(texto),
    )
    logger.info(
        "Documento identificado: %s · %s · $%s",
        doc.servicio.get("slug"), doc.tipo, doc.monto,
    )
    return doc
