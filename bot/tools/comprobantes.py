"""
Herramientas del agente para gestión de comprobantes y facturas en Google Drive.
Estas funciones son llamadas como tools por el agente vía function calling.
"""

import logging
from datetime import date

from bot.db import queries
from bot.tools.drive_manager import get_drive_manager

logger = logging.getLogger(__name__)

# Estado temporal de archivos pendientes de subir (en memoria, por chat_id)
# { chat_id: {"file_bytes": bytes, "mime_type": str, "datos_extraidos": dict} }
_archivo_pendiente: dict[int, dict] = {}


def set_archivo_pendiente(chat_id: int, file_bytes: bytes, mime_type: str, datos: dict) -> None:
    """Almacena temporalmente los datos del archivo para que el agente pueda subirlo."""
    _archivo_pendiente[chat_id] = {
        "file_bytes": file_bytes,
        "mime_type": mime_type,
        "datos_extraidos": datos,
    }


def clear_archivo_pendiente(chat_id: int) -> None:
    _archivo_pendiente.pop(chat_id, None)


def get_archivo_pendiente(chat_id: int) -> dict | None:
    return _archivo_pendiente.get(chat_id)


def _extension_from_mime(mime_type: str) -> str:
    """Obtiene extensión de archivo a partir del MIME type."""
    mime_map = {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    return mime_map.get(mime_type, "bin")


def subir_comprobante_a_drive(
    chat_id: int,
    comercio: str | None = None,
    fecha: str | None = None,
    tipo: str | None = None,
    categoria: str | None = None,
    monto: float | None = None,
    moneda: str | None = None,
) -> dict:
    """
    Sube el archivo pendiente a Google Drive con la estructura organizada.

    Los datos del archivo (bytes, mime_type) se obtienen del estado temporal
    almacenado por set_archivo_pendiente().

    Los parámetros permiten al agente sobreescribir datos extraídos por Gemini
    si el usuario los corrige.

    Returns:
        Dict con info del archivo subido: drive_file_name, drive_web_view_link, etc.
    """
    pendiente = get_archivo_pendiente(chat_id)
    if not pendiente:
        return {"error": "No hay ningún archivo pendiente para subir."}

    file_bytes = pendiente["file_bytes"]
    mime_type = pendiente["mime_type"]
    datos = pendiente["datos_extraidos"]

    # Usar parámetros del agente o los extraídos por Gemini
    comercio_final = comercio or datos.get("comercio") or "desconocido"
    fecha_str = fecha or datos.get("fecha") or date.today().isoformat()
    tipo_final = tipo or datos.get("tipo") or "comprobante"
    categoria_final = categoria or datos.get("categoria_sugerida") or "Otros"
    monto_final = monto if monto is not None else datos.get("monto")
    moneda_final = moneda or datos.get("moneda")

    try:
        fecha_doc = date.fromisoformat(fecha_str)
    except ValueError:
        fecha_doc = date.today()

    extension = _extension_from_mime(mime_type)

    try:
        dm = get_drive_manager()

        # Generar nombre de archivo
        filename = dm.generate_filename(fecha_doc, comercio_final, tipo_final, extension)

        # Obtener carpeta destino
        folder_id, folder_path = dm.get_target_folder(comercio_final, fecha_doc)

        # Verificar duplicado en DB (evita call extra a Drive API)
        db_dup = queries.buscar_duplicado_archivo(
            comercio_final, fecha_doc.isoformat(), tipo_final
        )
        if db_dup:
            clear_archivo_pendiente(chat_id)
            return {
                "duplicado": True,
                "archivo_existente": {
                    "nombre": db_dup.get("drive_file_name", filename),
                    "link": db_dup.get("drive_web_view_link", ""),
                    "carpeta": folder_path,
                },
                "mensaje": (
                    f"Ya existe un archivo '{db_dup.get('drive_file_name', filename)}' "
                    f"en {folder_path}. No se subió duplicado."
                ),
            }

        # Subir archivo
        result = dm.upload_file(file_bytes, filename, folder_id, mime_type)

        # Guardar metadata en Supabase
        registro = queries.insertar_archivo_drive({
            "tipo": tipo_final,
            "comercio": comercio_final,
            "fecha": fecha_doc.isoformat(),
            "categoria": categoria_final,
            "monto": monto_final,
            "moneda": moneda_final,
            "drive_file_id": result["file_id"],
            "drive_file_name": result["file_name"],
            "drive_web_view_link": result["web_view_link"],
            "drive_folder_path": folder_path,
            "mime_type": mime_type,
        })

        clear_archivo_pendiente(chat_id)

        return {
            "subido": True,
            "id": registro["id"],
            "archivo": result["file_name"],
            "carpeta": folder_path,
            "link": result["web_view_link"],
            "comercio": comercio_final,
            "fecha": fecha_doc.isoformat(),
            "tipo": tipo_final,
            "categoria": categoria_final,
            "monto": monto_final,
            "moneda": moneda_final,
        }

    except Exception as e:
        logger.exception("Error subiendo comprobante a Drive")
        return {"error": f"Error al subir a Drive: {str(e)}"}


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
