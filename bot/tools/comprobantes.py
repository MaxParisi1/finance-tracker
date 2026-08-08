"""
Herramientas del agente para gestión de comprobantes y facturas en Google Drive.
Estas funciones son llamadas como tools por el agente vía function calling.
"""

import logging
import re

from bot.db import queries
from bot.tools.drive_manager import get_drive_manager

logger = logging.getLogger(__name__)

def vincular_comprobante_a_gasto(archivo_id: str, gasto_id: str) -> dict:
    """
    Vincula un archivo de Drive con un gasto existente.
    """
    try:
        result = queries.vincular_archivo_a_gasto(archivo_id, gasto_id)
        if not result:
            return {"error": "No se encontró el archivo o el gasto."}
        return {"vinculado": True, "archivo_id": archivo_id, "gasto_id": gasto_id}
    except Exception as e:
        logger.exception("Error vinculando comprobante a gasto")
        return {"error": str(e)}


def listar_carpetas_drive() -> dict:
    """Lista las carpetas raíz existentes en Google Drive."""
    try:
        dm = get_drive_manager()
        carpetas = dm.list_root_folders()
        return {"carpetas": carpetas}
    except Exception as e:
        logger.exception("Error listando carpetas de Drive")
        return {"error": str(e)}


def eliminar_comprobante_drive(archivo_id: str, eliminar_de_drive: bool = False) -> dict:
    """
    Elimina un comprobante de la base de datos y opcionalmente de Google Drive.

    Si eliminar_de_drive=True, también borra el archivo físico de Drive.
    Si False (default), solo elimina el registro de Supabase.
    """
    from bot.db.supabase_client import get_client
    client = get_client()
    res = client.table("archivos_drive").select("drive_file_id").eq("id", archivo_id).execute()
    if not res.data:
        return {"error": "No se encontró el archivo."}

    drive_file_id = res.data[0].get("drive_file_id")

    if eliminar_de_drive and drive_file_id:
        try:
            dm = get_drive_manager()
            dm.delete_file(drive_file_id)
            logger.info("Archivo eliminado de Drive: %s", drive_file_id)
        except Exception as e:
            logger.warning("No se pudo eliminar de Drive: %s", e)

    return queries.eliminar_archivo_drive(archivo_id)


def buscar_comprobantes(
    comercio: str | None = None,
    mes: int | None = None,
    anio: int | None = None,
    categoria: str | None = None,
    tipo: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> dict:
    """
    Busca comprobantes en la base de datos según criterios.
    """
    filtros: dict = {}
    if comercio:
        filtros["comercio"] = comercio
    if mes is not None:
        filtros["mes"] = mes
    if anio is not None:
        filtros["anio"] = anio
    if categoria:
        filtros["categoria"] = categoria
    if tipo:
        filtros["tipo"] = tipo
    if fecha_desde:
        filtros["fecha_desde"] = fecha_desde
    if fecha_hasta:
        filtros["fecha_hasta"] = fecha_hasta

    try:
        archivos = queries.obtener_archivos_drive(filtros)
        return {
            "cantidad": len(archivos),
            "archivos": [
                {
                    "id": a["id"],
                    "nombre": a["drive_file_name"],
                    "comercio": a.get("comercio"),
                    "fecha": a.get("fecha"),
                    "tipo": a.get("tipo"),
                    "categoria": a.get("categoria"),
                    "monto": a.get("monto"),
                    "moneda": a.get("moneda"),
                    "link": a.get("drive_web_view_link"),
                    "gasto_vinculado": a.get("gasto_id") is not None,
                    "carpeta": a.get("drive_folder_path"),
                }
                for a in archivos
            ],
        }
    except Exception as e:
        logger.exception("Error buscando comprobantes")
        return {"error": str(e)}
