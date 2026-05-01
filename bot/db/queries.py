"""
Queries de bajo nivel contra Supabase.
Todas las funciones devuelven dicts o listas de dicts crudos.
La lógica de negocio vive en bot/tools/.
"""

import logging
from datetime import date
from typing import Any
from .supabase_client import get_client

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Gastos
# ──────────────────────────────────────────────

def insertar_gasto(gasto: dict) -> dict:
    client = get_client()
    res = client.table("gastos").insert(gasto).execute()
    logger.info("Gasto insertado id=%s descripcion=%r", res.data[0].get("id"), gasto.get("descripcion"))
    return res.data[0]


def obtener_gastos(filtros: dict) -> list[dict]:
    """
    filtros admitidos:
      mes (int), anio (int), categoria (str), medio_pago (str),
      moneda (str), fecha_desde (str YYYY-MM-DD), fecha_hasta (str YYYY-MM-DD),
      busqueda (str) → texto libre contra descripcion/comercio (todos los meses)
    """
    client = get_client()
    q = client.table("gastos").select("*").is_("deleted_at", "null")

    if "busqueda" in filtros:
        term = filtros["busqueda"].lower()
        q = q.or_(f"descripcion.ilike.%{term}%,comercio.ilike.%{term}%")
    elif "mes" in filtros and "anio" in filtros:
        mes = int(filtros["mes"])
        anio = int(filtros["anio"])
        fecha_desde = date(anio, mes, 1).isoformat()
        if mes == 12:
            fecha_hasta = date(anio + 1, 1, 1).isoformat()
        else:
            fecha_hasta = date(anio, mes + 1, 1).isoformat()
        q = q.gte("fecha", fecha_desde).lt("fecha", fecha_hasta)
    elif "fecha_desde" in filtros:
        q = q.gte("fecha", filtros["fecha_desde"])
        if "fecha_hasta" in filtros:
            q = q.lte("fecha", filtros["fecha_hasta"])

    if "categoria" in filtros:
        q = q.eq("categoria", filtros["categoria"])
    if "medio_pago" in filtros:
        q = q.eq("medio_pago", filtros["medio_pago"])
    if "moneda" in filtros:
        q = q.eq("moneda", filtros["moneda"])

    q = q.order("fecha", desc=True)
    res = q.execute()
    return res.data


def obtener_gasto_por_id(gasto_id: str) -> dict | None:
    client = get_client()
    res = (
        client.table("gastos")
        .select("*")
        .eq("id", gasto_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return res.data[0] if res.data else None


def actualizar_gasto(gasto_id: str, campos: dict) -> dict:
    client = get_client()
    res = client.table("gastos").update(campos).eq("id", gasto_id).execute()
    return res.data[0]


def obtener_comercios() -> list[str]:
    """Devuelve todos los nombres de comercio distintos, ordenados alfabéticamente."""
    client = get_client()
    res = (
        client.table("gastos")
        .select("comercio")
        .is_("deleted_at", "null")
        .execute()
    )
    unique = sorted({r["comercio"] for r in res.data if r.get("comercio")})
    return unique


def eliminar_gasto(gasto_id: str) -> bool:
    """Soft delete: marca el gasto como eliminado sin borrarlo de la DB."""
    from datetime import datetime, timezone
    client = get_client()
    client.table("gastos").update(
        {"deleted_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", gasto_id).execute()
    logger.info("Gasto eliminado (soft delete) id=%s", gasto_id)
    return True


# ──────────────────────────────────────────────
# Gastos recurrentes
# ──────────────────────────────────────────────

def insertar_recurrente(recurrente: dict) -> dict:
    client = get_client()
    res = client.table("gastos_recurrentes").insert(recurrente).execute()
    return res.data[0]


def obtener_recurrentes_activos() -> list[dict]:
    client = get_client()
    res = (
        client.table("gastos_recurrentes")
        .select("*")
        .eq("activo", True)
        .order("proximo_vencimiento")
        .execute()
    )
    return res.data


# ──────────────────────────────────────────────
# Categorías
# ──────────────────────────────────────────────

def obtener_categorias_activas() -> list[dict]:
    client = get_client()
    res = (
        client.table("categorias")
        .select("nombre, descripcion, color, icono")
        .eq("activa", True)
        .order("nombre")
        .execute()
    )
    return res.data


# ──────────────────────────────────────────────
# Tipos de cambio histórico
# ──────────────────────────────────────────────

def insertar_tipo_cambio(fecha: str, tipo: str, valor: float) -> None:
    """Upsert: si ya existe el par (fecha, tipo), no falla."""
    client = get_client()
    client.table("tipos_cambio_historico").upsert(
        {"fecha": fecha, "tipo": tipo, "valor": valor},
        on_conflict="fecha,tipo",
    ).execute()


# ──────────────────────────────────────────────
# Sesiones del bot (historial persistente)
# ──────────────────────────────────────────────

def cargar_historial_bot(chat_id: int) -> list[dict]:
    """Carga el historial de conversación desde la DB."""
    client = get_client()
    res = (
        client.table("bot_sessions")
        .select("history")
        .eq("chat_id", chat_id)
        .execute()
    )
    return res.data[0]["history"] if res.data else []


def guardar_historial_bot(chat_id: int, history: list[dict]) -> None:
    """Upsert del historial de conversación."""
    from datetime import datetime, timezone
    client = get_client()
    client.table("bot_sessions").upsert(
        {
            "chat_id": chat_id,
            "history": history,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="chat_id",
    ).execute()


def obtener_tipo_cambio_historico(fecha: str, tipo: str) -> float | None:
    client = get_client()
    res = (
        client.table("tipos_cambio_historico")
        .select("valor")
        .eq("fecha", fecha)
        .eq("tipo", tipo)
        .execute()
    )
    return res.data[0]["valor"] if res.data else None


# ──────────────────────────────────────────────
# Archivos Drive (comprobantes/facturas)
# ──────────────────────────────────────────────

def insertar_archivo_drive(archivo: dict) -> dict:
    client = get_client()
    res = client.table("archivos_drive").insert(archivo).execute()
    logger.info(
        "Archivo Drive insertado id=%s file=%s",
        res.data[0].get("id"),
        archivo.get("drive_file_name"),
    )
    return res.data[0]


def obtener_archivos_drive(filtros: dict) -> list[dict]:
    """
    Busca archivos en archivos_drive con filtros opcionales.
    filtros admitidos: comercio (ilike), mes (int), anio (int),
                       categoria, tipo, fecha_desde, fecha_hasta, gasto_id
    """
    client = get_client()
    q = client.table("archivos_drive").select("*")

    if "comercio" in filtros:
        term = filtros["comercio"].lower()
        q = q.ilike("comercio", f"%{term}%")

    if "mes" in filtros and "anio" in filtros:
        mes = int(filtros["mes"])
        anio = int(filtros["anio"])
        fecha_desde = date(anio, mes, 1).isoformat()
        if mes == 12:
            fecha_hasta = date(anio + 1, 1, 1).isoformat()
        else:
            fecha_hasta = date(anio, mes + 1, 1).isoformat()
        q = q.gte("fecha", fecha_desde).lt("fecha", fecha_hasta)
    elif "anio" in filtros:
        anio = int(filtros["anio"])
        q = q.gte("fecha", f"{anio}-01-01").lt("fecha", f"{anio + 1}-01-01")
    elif "fecha_desde" in filtros:
        q = q.gte("fecha", filtros["fecha_desde"])
        if "fecha_hasta" in filtros:
            q = q.lte("fecha", filtros["fecha_hasta"])

    if "categoria" in filtros:
        q = q.eq("categoria", filtros["categoria"])
    if "tipo" in filtros:
        q = q.eq("tipo", filtros["tipo"])
    if "gasto_id" in filtros:
        q = q.eq("gasto_id", filtros["gasto_id"])

    q = q.order("fecha", desc=True)
    res = q.execute()
    return res.data


def sincronizar_fecha_archivos(gasto_id: str, fecha: str) -> None:
    """Actualiza la fecha de todos los archivos_drive vinculados a un gasto."""
    client = get_client()
    client.table("archivos_drive").update({"fecha": fecha}).eq("gasto_id", gasto_id).execute()


def vincular_archivo_a_gasto(archivo_id: str, gasto_id: str) -> dict:
    """Vincula un archivo de Drive con un gasto existente.

    archivo_id puede ser el UUID de Supabase o el drive_file_id de Google Drive.
    """
    import re
    client = get_client()
    _UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
    column = "id" if _UUID_RE.match(archivo_id) else "drive_file_id"
    res = (
        client.table("archivos_drive")
        .update({"gasto_id": gasto_id})
        .eq(column, archivo_id)
        .execute()
    )
    return res.data[0] if res.data else {}


def obtener_archivos_por_gasto(gasto_id: str) -> list[dict]:
    """Obtiene todos los archivos vinculados a un gasto."""
    client = get_client()
    res = (
        client.table("archivos_drive")
        .select("*")
        .eq("gasto_id", gasto_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data


def buscar_duplicado_archivo(comercio: str, fecha: str, tipo: str) -> dict | None:
    """Busca si ya existe un archivo con mismo comercio, fecha y tipo."""
    client = get_client()
    res = (
        client.table("archivos_drive")
        .select("*")
        .ilike("comercio", comercio)
        .eq("fecha", fecha)
        .eq("tipo", tipo)
        .execute()
    )
    return res.data[0] if res.data else None


def contar_archivos_por_gastos(gasto_ids: list[str]) -> dict[str, int]:
    """Cuenta archivos vinculados para una lista de gasto_ids."""
    if not gasto_ids:
        return {}
    client = get_client()
    res = (
        client.table("archivos_drive")
        .select("gasto_id")
        .in_("gasto_id", gasto_ids)
        .execute()
    )
    conteo: dict[str, int] = {}
    for row in res.data:
        gid = row["gasto_id"]
        conteo[gid] = conteo.get(gid, 0) + 1
    return conteo


# ──────────────────────────────────────────────
# Tarjetas
# ──────────────────────────────────────────────

def buscar_tarjeta_por_sufijo(sufijo: str) -> dict | None:
    client = get_client()
    res = (
        client.table("tarjetas")
        .select("*")
        .eq("sufijo", sufijo)
        .execute()
    )
    return res.data[0] if res.data else None


def insertar_tarjeta(tarjeta: dict) -> dict:
    client = get_client()
    res = client.table("tarjetas").insert(tarjeta).execute()
    logger.info("Tarjeta creada sufijo=%s tipo=%s", tarjeta.get("sufijo"), tarjeta.get("tipo"))
    return res.data[0]


def listar_tarjetas() -> list[dict]:
    client = get_client()
    res = (
        client.table("tarjetas")
        .select("*")
        .order("created_at")
        .execute()
    )
    return res.data


def actualizar_tarjeta(sufijo: str, campos: dict) -> dict:
    client = get_client()
    res = (
        client.table("tarjetas")
        .update(campos)
        .eq("sufijo", sufijo)
        .execute()
    )
    return res.data[0] if res.data else {}
