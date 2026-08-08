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


def existe_gasto_con_email(message_id: str) -> bool:
    """
    True si ya existe un gasto importado desde ese email de Gmail.
    Idempotencia: evita duplicados si el proceso muere entre guardar_gasto()
    y mark_as_read() y el email se reprocesa en el siguiente ciclo.
    """
    client = get_client()
    res = (
        client.table("gastos")
        .select("id")
        .eq("email_message_id", message_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


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


def vincular_gasto_recurrente(gasto_id: str, recurrente_id: str) -> None:
    client = get_client()
    client.table("gastos").update({"recurrente_id": recurrente_id}).eq("id", gasto_id).execute()
    logger.info("Gasto %s vinculado a recurrente %s", gasto_id, recurrente_id)


def _siguiente_vencimiento(d: date, frecuencia: str) -> date:
    """Avanza una fecha un período según la frecuencia, con clamp de fin de mes."""
    import calendar as _cal
    from datetime import timedelta
    if frecuencia == "anual":
        return d.replace(year=d.year + 1, day=min(d.day, _cal.monthrange(d.year + 1, d.month)[1]))
    if frecuencia == "semanal":
        return d + timedelta(days=7)
    mes, anio = (d.month + 1, d.year) if d.month < 12 else (1, d.year + 1)
    return d.replace(year=anio, month=mes, day=min(d.day, _cal.monthrange(anio, mes)[1]))


def avanzar_proximo_vencimiento(
    recurrente_id: str, frecuencia: str, proximo_actual: str, fecha_pago: str | None = None
) -> None:
    """
    Avanza proximo_vencimiento al menos un período. Si el pago llegó tarde
    (proximo_actual quedó en el pasado), sigue avanzando hasta superar la fecha
    del pago, evitando que la ventana de matching futura quede desalineada.
    """
    frecuencia = frecuencia or "mensual"
    d = date.fromisoformat(str(proximo_actual))
    ancla = date.fromisoformat(str(fecha_pago)) if fecha_pago else date.today()

    nueva = _siguiente_vencimiento(d, frecuencia)
    guard = 0
    while nueva <= ancla and guard < 120:
        nueva = _siguiente_vencimiento(nueva, frecuencia)
        guard += 1

    client = get_client()
    client.table("gastos_recurrentes").update({"proximo_vencimiento": nueva.isoformat()}).eq("id", recurrente_id).execute()
    logger.info("Recurrente %s → proximo_vencimiento=%s", recurrente_id, nueva)


def actualizar_monto_recurrente(recurrente_id: str, nuevo_monto: float) -> None:
    """Actualiza el monto esperado del recurrente al último observado."""
    client = get_client()
    client.table("gastos_recurrentes").update({"monto_original": nuevo_monto}).eq("id", recurrente_id).execute()
    logger.info("Recurrente %s → monto_original=%s", recurrente_id, nuevo_monto)


def obtener_aliases_recurrentes() -> dict[str, str]:
    """Retorna dict {comercio_normalizado: recurrente_id}."""
    client = get_client()
    res = client.table("recurrentes_aliases").select("comercio_normalizado, recurrente_id").execute()
    return {r["comercio_normalizado"]: r["recurrente_id"] for r in res.data}


def upsert_alias_recurrente(recurrente_id: str, comercio_normalizado: str, confirmado_por_usuario: bool) -> None:
    client = get_client()
    client.table("recurrentes_aliases").upsert(
        {"recurrente_id": recurrente_id, "comercio_normalizado": comercio_normalizado, "confirmado_por_usuario": confirmado_por_usuario},
        on_conflict="comercio_normalizado",
    ).execute()


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


def eliminar_archivo_drive(archivo_id: str) -> dict:
    """Elimina el registro de un archivo de la base de datos."""
    client = get_client()
    client.table("archivos_drive").delete().eq("id", archivo_id).execute()
    return {"eliminado": True, "id": archivo_id}


def desvincular_archivo_drive(archivo_id: str) -> dict:
    """Desvincula un archivo de su gasto (pone gasto_id = null)."""
    client = get_client()
    res = (
        client.table("archivos_drive")
        .update({"gasto_id": None})
        .eq("id", archivo_id)
        .execute()
    )
    if not res.data:
        return {"error": "No se encontró el archivo."}
    return {"desvinculado": True, "id": archivo_id}


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


# ──────────────────────────────────────────────
# Servicios fijos y facturas
# ──────────────────────────────────────────────

def obtener_servicio_por_identificador(identificador: str) -> dict | None:
    """
    Resuelve un servicio a partir de un identificador YA NORMALIZADO
    (número de cuenta, cliente, referente, CBU o CUIT).

    Es el único camino de ruteo: nunca se matchea por nombre ni por dirección.
    servicios_identificadores.valor es UNIQUE, así que no puede haber ambigüedad.
    """
    client = get_client()
    res = (
        client.table("servicios_identificadores")
        .select("tipo, valor, servicios(*)")
        .eq("valor", identificador)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None

    fila = res.data[0]
    servicio = fila.get("servicios")
    if not servicio or not servicio.get("activo"):
        return None

    return {**servicio, "identificador_tipo": fila["tipo"], "identificador": fila["valor"]}


def obtener_factura_por_email(message_id: str) -> dict | None:
    """Factura ya creada a partir de ese mail, si existe (idempotencia del poller)."""
    client = get_client()
    res = (
        client.table("facturas")
        .select("*")
        .eq("email_message_id", message_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def obtener_factura_por_vencimiento(servicio_id: str, vencimiento: str) -> dict | None:
    """
    Factura del servicio con ese vencimiento exacto. Sirve para resolver la
    carrera contra el índice único (servicio_id, vencimiento) sin duplicar.
    """
    client = get_client()
    res = (
        client.table("facturas")
        .select("*")
        .eq("servicio_id", servicio_id)
        .eq("vencimiento", vencimiento)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def insertar_factura(factura: dict) -> dict:
    client = get_client()
    res = client.table("facturas").insert(factura).execute()
    creada = res.data[0]
    logger.info(
        "Factura insertada id=%s servicio=%s $%s vence=%s",
        creada.get("id"), factura.get("servicio_id"),
        factura.get("monto"), factura.get("vencimiento"),
    )
    return creada


def obtener_facturas_pendientes(servicio_id: str | None = None) -> list[dict]:
    """Facturas impagas, de un servicio o de todos, más próximas a vencer primero."""
    client = get_client()
    q = client.table("facturas").select("*, servicios(slug, nombre)").eq("estado", "pendiente")
    if servicio_id:
        q = q.eq("servicio_id", servicio_id)
    return q.order("vencimiento").execute().data


def marcar_factura_pagada(factura_id: str, gasto_id: str, fecha_pago: str) -> dict:
    """
    Vincula el pago a la factura. Solo aplica sobre facturas pendientes: si otro
    proceso ya la saldó, no se pisa y se devuelve {} (el caller decide).
    """
    client = get_client()
    res = (
        client.table("facturas")
        .update({"estado": "pagada", "gasto_id": gasto_id, "fecha_pago": fecha_pago})
        .eq("id", factura_id)
        .eq("estado", "pendiente")
        .execute()
    )
    if not res.data:
        logger.warning("Factura %s no se marcó pagada (¿ya estaba saldada?)", factura_id)
        return {}
    logger.info("Factura %s pagada con gasto %s", factura_id, gasto_id)
    return res.data[0]


def vincular_archivo_a_factura(archivo_id: str, factura_id: str) -> dict:
    """Cuelga un PDF de la factura, exista o no todavía el gasto."""
    client = get_client()
    res = (
        client.table("archivos_drive")
        .update({"factura_id": factura_id})
        .eq("id", archivo_id)
        .execute()
    )
    return res.data[0] if res.data else {}


def obtener_ultima_factura(servicio_id: str) -> dict | None:
    """
    Última factura del servicio por vencimiento, en cualquier estado.
    Se usa como referencia de plausibilidad del monto: la anterior suele estar
    pagada, así que filtrar por pendientes daría None casi siempre.
    """
    client = get_client()
    res = (
        client.table("facturas")
        .select("*")
        .eq("servicio_id", servicio_id)
        .neq("estado", "anulada")
        .order("vencimiento", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def obtener_servicio_por_slug(slug: str) -> dict | None:
    """
    Resuelve un servicio por su slug. Es la vía para expensas, cuyo mail no trae
    ningún número de cuenta: ahí el remitente es el identificador.
    """
    client = get_client()
    res = (
        client.table("servicios")
        .select("*")
        .eq("slug", slug)
        .eq("activo", True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def listar_identificadores_servicios() -> list[dict]:
    """
    Todos los identificadores registrados, con su servicio.
    Se traen enteros (son pocos) para poder buscarlos como substring dentro del
    texto de un PDF, donde el número puede venir espaciado o embebido en una
    línea de código de barras.
    """
    client = get_client()
    res = (
        client.table("servicios_identificadores")
        .select("tipo, valor, servicios(*)")
        .execute()
    )
    return [
        {"tipo": f["tipo"], "valor": f["valor"], "servicio": f["servicios"]}
        for f in res.data
        if f.get("servicios") and f["servicios"].get("activo")
    ]


def obtener_recurrente_por_id(recurrente_id: str) -> dict | None:
    client = get_client()
    res = client.table("gastos_recurrentes").select("*").eq("id", recurrente_id).limit(1).execute()
    return res.data[0] if res.data else None


def obtener_facturas_con_archivos(desde: str) -> list[dict]:
    """
    Facturas desde una fecha, con su servicio y los tipos de archivo adjuntos.

    Se trae todo junto para poder decidir en memoria qué falta (factura, pago o
    comprobante) sin una consulta por fila.
    """
    client = get_client()
    res = (
        client.table("facturas")
        .select("*, servicios(slug, nombre), archivos_drive(tipo)")
        .neq("estado", "anulada")
        .gte("vencimiento", desde)
        .order("vencimiento")
        .execute()
    )
    return res.data
