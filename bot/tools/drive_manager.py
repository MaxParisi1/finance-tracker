"""
Gestión de archivos en Google Drive via Service Account.
Estructura de carpetas:
  Root/
  ├── {Comercio}/
  │   ├── {Año}/
  │   │   ├── 01 - Enero/
  │   │   ├── 02 - Febrero/
  │   │   └── ...
"""

import io
import os
import json
import logging
import unicodedata
import re
from datetime import date

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]

MONTH_NAMES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

# Mapeo de categoría de gasto → carpeta Drive (ya no se usa, pero lo dejamos
# por si en el futuro se quiere agregar otra capa).
CATEGORIA_FOLDER_MAP = {
    "Hogar": "Servicios",
    "Salud": "Salud",
    "Impuestos": "Impuestos",
}


def _normalizar_comercio(nombre: str) -> str:
    """
    Normaliza nombre de comercio para usar como nombre de archivo.
    Lowercase, sin acentos, espacios → guiones bajos.
    """
    # Quitar acentos
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase, reemplazar espacios y puntos por guión bajo
    normalizado = sin_acentos.lower().strip()
    normalizado = re.sub(r"[\s.]+", "_", normalizado)
    # Quitar caracteres no alfanuméricos excepto guión bajo y guión
    normalizado = re.sub(r"[^a-z0-9_\-]", "", normalizado)
    return normalizado


def _normalizar_carpeta(nombre: str) -> str:
    """
    Normaliza nombre de comercio para usar como nombre de carpeta.
    Primera letra mayúscula de cada palabra, sin normalizar a lowercase.
    """
    nombre = nombre.strip()
    # Quitar caracteres raros pero mantener legibilidad
    nombre = re.sub(r"[^\w\s.\-áéíóúÁÉÍÓÚñÑ]", "", nombre)
    # Title case
    return nombre.title() if nombre else "Otros"


class DriveManager:
    """Gestiona la subida y búsqueda de archivos en Google Drive."""

    def __init__(self):
        self._root_folder_id = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID")

        if not self._root_folder_id:
            raise RuntimeError("Falta variable de entorno: GOOGLE_DRIVE_ROOT_FOLDER_ID")

        refresh_token = os.environ.get("DRIVE_REFRESH_TOKEN")
        client_id = os.environ.get("DRIVE_CLIENT_ID")
        client_secret = os.environ.get("DRIVE_CLIENT_SECRET")

        if not all([refresh_token, client_id, client_secret]):
            raise RuntimeError(
                "Faltan variables de entorno: DRIVE_REFRESH_TOKEN, DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET"
            )

        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        credentials.refresh(Request())
        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)

        # Cache de folder IDs para evitar consultas repetidas
        # key: "parent_id/folder_name" → value: folder_id
        self._folder_cache: dict[str, str] = {}

    def _find_folder(self, name: str, parent_id: str) -> str | None:
        """Busca una carpeta por nombre dentro de un parent."""
        cache_key = f"{parent_id}/{name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        query = (
            f"name='{name}' and "
            f"'{parent_id}' in parents and "
            f"mimeType='application/vnd.google-apps.folder' and "
            f"trashed=false"
        )
        results = self._service.files().list(
            q=query, fields="files(id, name)", spaces="drive"
        ).execute()

        files = results.get("files", [])
        if files:
            folder_id = files[0]["id"]
            self._folder_cache[cache_key] = folder_id
            return folder_id
        return None

    def _create_folder(self, name: str, parent_id: str) -> str:
        """Crea una carpeta y retorna su ID."""
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = self._service.files().create(
            body=metadata, fields="id"
        ).execute()

        folder_id = folder["id"]
        cache_key = f"{parent_id}/{name}"
        self._folder_cache[cache_key] = folder_id
        logger.info("Carpeta creada en Drive: %s (id=%s)", name, folder_id)
        return folder_id

    def _get_or_create_folder(self, name: str, parent_id: str) -> str:
        """Obtiene o crea una carpeta."""
        existing = self._find_folder(name, parent_id)
        if existing:
            return existing
        return self._create_folder(name, parent_id)

    def get_target_folder(self, comercio: str, fecha: date) -> tuple[str, str]:
        """
        Obtiene o crea la estructura de carpetas:
          Root/{Comercio}/{Año}/{MM - Mes}/

        Args:
            comercio: Nombre del comercio (se normaliza para carpeta).
            fecha: Fecha del documento.

        Returns:
            Tuple (folder_id, folder_path) donde folder_path es la ruta lógica.
        """
        # Nivel 1: Carpeta del comercio
        carpeta_comercio = _normalizar_carpeta(comercio)
        comercio_id = self._get_or_create_folder(carpeta_comercio, self._root_folder_id)

        # Nivel 2: Año
        anio_str = str(fecha.year)
        anio_id = self._get_or_create_folder(anio_str, comercio_id)

        # Nivel 3: Mes (formato "01 - Enero")
        mes_str = f"{fecha.month:02d} - {MONTH_NAMES[fecha.month - 1]}"
        mes_id = self._get_or_create_folder(mes_str, anio_id)

        folder_path = f"{carpeta_comercio}/{anio_str}/{mes_str}"
        return mes_id, folder_path

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        folder_id: str,
        mime_type: str,
    ) -> dict:
        """
        Sube un archivo a Drive.

        Returns:
            {"file_id": str, "web_view_link": str, "file_name": str}
        """
        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype=mime_type,
            resumable=True,
        )

        metadata = {
            "name": filename,
            "parents": [folder_id],
        }

        uploaded = self._service.files().create(
            body=metadata,
            media_body=media,
            fields="id, webViewLink, name",
        ).execute()

        file_id = uploaded["id"]
        web_view_link = uploaded.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"

        result = {
            "file_id": file_id,
            "web_view_link": web_view_link,
            "file_name": uploaded["name"],
        }

        logger.info("Archivo subido a Drive: %s (id=%s)", filename, result["file_id"])
        return result

    def generate_filename(
        self,
        fecha: date,
        comercio: str,
        tipo: str,
        extension: str,
    ) -> str:
        """
        Genera nombre de archivo: YYYY-MM-DD_comercio_tipo.ext

        Args:
            fecha: Fecha del documento.
            comercio: Nombre del comercio (se normaliza).
            tipo: 'factura', 'comprobante', 'ticket', 'recibo', 'resumen'.
            extension: 'pdf', 'jpg', 'png', etc.
        """
        fecha_str = fecha.isoformat()
        comercio_norm = _normalizar_comercio(comercio)
        tipo = tipo.lower().strip()

        # Asegurar que la extensión no tenga punto
        extension = extension.lstrip(".")

        return f"{fecha_str}_{comercio_norm}_{tipo}.{extension}"

    def check_duplicate(self, filename: str, folder_id: str) -> dict | None:
        """
        Verifica si ya existe un archivo con el mismo nombre en la carpeta.

        Returns:
            Dict con info del archivo existente, o None si no existe.
        """
        query = (
            f"name='{filename}' and "
            f"'{folder_id}' in parents and "
            f"trashed=false"
        )
        results = self._service.files().list(
            q=query, fields="files(id, name, webViewLink)", spaces="drive"
        ).execute()

        files = results.get("files", [])
        if files:
            return {
                "file_id": files[0]["id"],
                "file_name": files[0]["name"],
                "web_view_link": files[0].get("webViewLink", ""),
            }
        return None


# Singleton global (se inicializa lazy)
_drive_manager: DriveManager | None = None


def get_drive_manager() -> DriveManager:
    """Obtiene la instancia singleton de DriveManager."""
    global _drive_manager
    if _drive_manager is None:
        _drive_manager = DriveManager()
    return _drive_manager
