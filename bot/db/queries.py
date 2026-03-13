"""
Queries de bajo nivel contra Supabase.
Todas las funciones devuelven dicts o listas de dicts crudos.
La lógica de negocio vive en bot/tools/.
"""

from datetime import date
from typing import Any
from .supabase_client import get_client


# ──────────────────────────────────────────────
# Gastos
# ──────────────────────────────────────────────

def insertar_gasto(gasto: dict) -> dict:
    client = get_client()
    res = client.table("gastos").insert(gasto).execute()
    return res.data[0]


def obtener_gastos(filtros: dict) -> list[dict]:
    """
    filtros admitidos:
      mes (int), anio (int), categoria (str), medio_pago (str),
      moneda (str), fecha_desde (str YYYY-MM-DD), fecha_hasta (str YYYY-MM-DD)
    """
    client = get_client()
    q = client.table("gastos").select("*")

    if "mes" in filtros and "anio" in filtros:
        mes = int(filtros["mes"])
        anio = int(filtros["anio"])
        fecha_desde = date(anio, mes, 1).isoformat()
        # último día del mes
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
    res = client.table("gastos").select("*").eq("id", gasto_id).execute()
    return res.data[0] if res.data else None


def actualizar_gasto(gasto_id: str, campos: dict) -> dict:
    client = get_client()
    res = client.table("gastos").update(campos).eq("id", gasto_id).execute()
    return res.data[0]


def eliminar_gasto(gasto_id: str) -> bool:
    client = get_client()
    client.table("gastos").delete().eq("id", gasto_id).execute()
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
