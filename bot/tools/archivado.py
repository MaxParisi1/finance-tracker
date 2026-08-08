"""
Archivado de un documento suelto: del PDF que te llega por Telegram a
Drive + factura vinculada + gasto registrado, sin preguntarte nada.

Orquesta las piezas ya testeadas por separado (identificación, conciliación,
Drive) y define QUÉ pasa en cada combinación:

  factura     + factura abierta  → PDF a Drive colgado de la factura
  comprobante + factura abierta  → PDF a Drive + gasto creado + factura saldada
  cualquiera  + sin factura      → PDF a Drive igual, sin vincular, y se avisa

La última regla es deliberada: el objetivo es registro total, así que un
documento nunca se descarta por no encontrarle pareja. Se archiva y queda
señalado como huérfano para resolverlo después.
"""

import logging
from dataclasses import dataclass
from datetime import date

from bot.db import queries
from bot.tools.conciliacion import elegir_factura
from bot.tools.documentos import TIPO_COMPROBANTE, DocumentoIdentificado
from bot.tools.drive_manager import get_drive_manager

logger = logging.getLogger(__name__)

__all__ = ["ResultadoArchivado", "archivar_documento"]

_EXTENSIONES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


@dataclass(frozen=True)
class ResultadoArchivado:
    tipo: str
    servicio: str
    archivo: dict
    factura: dict | None = None
    gasto: dict | None = None
    aviso: str | None = None   # qué quedó sin resolver, si algo


def _extension(mime: str) -> str:
    return _EXTENSIONES.get(mime, "pdf")


def _subir_a_drive(pdf_bytes: bytes, mime: str, nombre_servicio: str,
                   tipo: str, fecha: date) -> dict:
    """Sube a Drive con la estructura Comercio/Año/Mes que ya usa el resto."""
    dm = get_drive_manager()
    filename = dm.generate_filename(fecha, nombre_servicio, tipo, _extension(mime))
    folder_id, folder_path = dm.get_target_folder(nombre_servicio, fecha)
    subido = dm.upload_file(pdf_bytes, filename, folder_id, mime)
    return {**subido, "folder_path": folder_path}


def _registrar_pago(servicio: dict, factura: dict, fecha: date) -> dict:
    """
    Crea el gasto del pago tomando el monto de la FACTURA, no del comprobante.

    La factura es la fuente autoritativa: el comprobante puede haber perdido los
    centavos al extraerse del PDF (caso Personal Pay). Categoría y medio de pago
    salen del recurrente que ya tenías configurado.
    """
    from bot.tools.gastos import guardar_gasto

    recurrente = None
    if servicio.get("recurrente_id"):
        recurrente = queries.obtener_recurrente_por_id(servicio["recurrente_id"])

    gasto = guardar_gasto(
        descripcion=servicio["nombre"],
        monto=float(factura["monto"]),
        moneda=factura.get("moneda") or "ARS",
        categoria=(recurrente or {}).get("categoria") or "Hogar",
        medio_pago=(recurrente or {}).get("medio_pago") or "transferencia",
        fecha=fecha.isoformat(),
        comercio=servicio["nombre"],
        fuente="documento_telegram",
    )

    if recurrente:
        queries.vincular_gasto_recurrente(gasto["id"], recurrente["id"])

    return gasto


def archivar_documento(
    doc: DocumentoIdentificado,
    pdf_bytes: bytes,
    mime_type: str = "application/pdf",
    hoy: date | None = None,
) -> ResultadoArchivado:
    """
    Archiva un documento ya identificado. No levanta excepción por falta de
    factura: en ese caso archiva igual y lo reporta en `aviso`.
    """
    hoy = hoy or date.today()
    servicio = doc.servicio
    fecha = doc.fecha or hoy

    pendientes = queries.obtener_facturas_pendientes(servicio["id"])
    seleccion = elegir_factura(pendientes, doc.monto, doc.fecha)
    factura = seleccion.factura

    avisos = []
    if factura is None:
        avisos.append(f"quedó sin vincular ({seleccion.motivo})")
    elif not seleccion.coincide_monto and doc.monto is not None:
        avisos.append(
            f"el documento dice ${doc.monto:,.2f} y la factura ${float(factura['monto']):,.2f}"
        )

    # Si hay factura, su vencimiento manda para la carpeta: así el PDF cae en el
    # mes que corresponde aunque lo mandes tarde.
    if factura and factura.get("vencimiento"):
        try:
            fecha = date.fromisoformat(str(factura["vencimiento"]))
        except ValueError:
            pass

    subido = _subir_a_drive(pdf_bytes, mime_type, servicio["nombre"], doc.tipo, fecha)

    gasto = None
    if doc.tipo == TIPO_COMPROBANTE and factura and factura.get("estado") == "pendiente":
        gasto = _registrar_pago(servicio, factura, doc.fecha or hoy)
        saldada = queries.marcar_factura_pagada(
            factura["id"], gasto["id"], (doc.fecha or hoy).isoformat()
        )
        if not saldada:
            avisos.append("la factura ya figuraba saldada")

    archivo = queries.insertar_archivo_drive({
        "tipo": doc.tipo,
        "comercio": servicio["nombre"],
        "fecha": fecha.isoformat(),
        "categoria": None,
        "monto": float(factura["monto"]) if factura else doc.monto,
        "moneda": "ARS",
        "drive_file_id": subido["file_id"],
        "drive_file_name": subido["file_name"],
        "drive_web_view_link": subido["web_view_link"],
        "drive_folder_path": subido["folder_path"],
        "mime_type": mime_type,
        "factura_id": factura["id"] if factura else None,
        "gasto_id": gasto["id"] if gasto else None,
    })

    logger.info(
        "Documento archivado: %s/%s → factura=%s gasto=%s",
        servicio["slug"], doc.tipo,
        factura["id"] if factura else None, gasto["id"] if gasto else None,
    )

    return ResultadoArchivado(
        tipo=doc.tipo,
        servicio=servicio["nombre"],
        archivo=archivo,
        factura=factura,
        gasto=gasto,
        aviso=" · ".join(avisos) or None,
    )
