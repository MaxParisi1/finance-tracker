"""
Agente financiero con Function Calling nativo de Gemini.
Loop manual: sin LangChain ni frameworks intermedios.
Máximo MAX_ITER iteraciones por mensaje para evitar loops infinitos.
SDK: google-genai (nuevo, reemplaza google-generativeai)
"""

import os
import json
import logging
from datetime import date, datetime, timezone, timedelta

from google.genai import types

from google import genai
from bot.gemini_client import get_client as _get_client, create_chat_with_fallback


from bot.tools.gastos import (
    guardar_gasto,
    guardar_multiples_gastos,
    guardar_gasto_recurrente,
    editar_gasto,
    eliminar_gasto,
    consultar_gastos,
    resumen_mensual,
    comparar_meses,
    gastos_recurrentes_activos,
    tendencia_gastos,
    top_comercios,
    proyeccion_mensual,
    historial_comercio,
)
from bot.tools.tipo_cambio import obtener_tipo_cambio
from bot.tools.bbva_parser import importar_pdf_bbva, guardar_movimientos_bbva
from bot.tools.comprobantes import (
    subir_comprobante_a_drive,
    vincular_comprobante_a_gasto,
    buscar_comprobantes,
)
from bot.db.queries import obtener_categorias_activas, obtener_gastos

logger = logging.getLogger(__name__)

MAX_ITER = 5
MODEL = "gemini-2.5-flash"

# Estado temporal del PDF pendiente de confirmación (en memoria, por chat_id)
# { chat_id: {"resultado": dict, "pdf_bytes": bytes} }
_pdf_pendiente: dict[int, dict] = {}

# Estado temporal del gasto pendiente de confirmación (en memoria, por chat_id)
# { chat_id: {"tool": "guardar_gasto"|"guardar_multiples_gastos", "args": dict} }
_gasto_pendiente: dict[int, dict] = {}


def set_pdf_pendiente(chat_id: int, resultado: dict, pdf_bytes: bytes) -> None:
    _pdf_pendiente[chat_id] = {"resultado": resultado, "pdf_bytes": pdf_bytes}


def clear_pdf_pendiente(chat_id: int) -> None:
    _pdf_pendiente.pop(chat_id, None)


# El chat_id activo se setea antes de cada llamada a run_agent desde main.py
_chat_id_activo: int | None = None


def _previsualizar_pdf_bbva() -> dict:
    """Devuelve el resumen del PDF ya parseado (previamente guardado en _pdf_pendiente)."""
    if _chat_id_activo is None or _chat_id_activo not in _pdf_pendiente:
        return {"error": "No hay ningún PDF pendiente de procesar."}
    return _pdf_pendiente[_chat_id_activo]["resultado"]


def _confirmar_importacion_pdf_bbva() -> dict:
    """Guarda los movimientos nuevos del PDF y limpia el estado temporal."""
    if _chat_id_activo is None or _chat_id_activo not in _pdf_pendiente:
        return {"error": "No hay ningún PDF pendiente de confirmar."}

    resultado = _pdf_pendiente[_chat_id_activo]["resultado"]
    movimientos_nuevos = resultado.get("movimientos_nuevos", [])

    guardados = guardar_movimientos_bbva(movimientos_nuevos)
    clear_pdf_pendiente(_chat_id_activo)

    return {
        "importados": guardados,
        "duplicados_omitidos": resultado.get("total_duplicados", 0),
    }

# ──────────────────────────────────────────────
# Declaraciones de herramientas para Gemini
# ──────────────────────────────────────────────

_TOOL_DECLARATIONS = [

    types.FunctionDeclaration(
        name="guardar_gasto",
        description=(
            "Registra un gasto. SIEMPRE llamar primero con dry_run=True para obtener el preview "
            "y mostrárselo al usuario antes de confirmar. El sistema procesará la confirmación "
            "automáticamente. Solo omitir dry_run como fallback si el usuario ya confirmó pero "
            "el sistema no lo procesó."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "dry_run":          types.Schema(type="BOOLEAN", description="True para registrar como pendiente y obtener preview. Usar SIEMPRE antes de pedir confirmación."),
                "descripcion":      types.Schema(type="STRING", description="Descripción del gasto"),
                "monto":            types.Schema(type="NUMBER", description="Monto en la moneda original"),
                "moneda":           types.Schema(type="STRING", enum=["ARS", "USD"]),
                "categoria":        types.Schema(type="STRING", description="Categoría del gasto"),
                "medio_pago":       types.Schema(type="STRING", enum=[
                                        "credito_ars", "credito_usd", "debito",
                                        "efectivo_ars", "efectivo_usd", "transferencia"
                                    ]),
                "fecha":            types.Schema(type="STRING", description="Fecha YYYY-MM-DD. Si no se especifica, usar hoy."),
                "cuotas":           types.Schema(type="INTEGER", description="Total de cuotas (1 si es al contado)"),
                "cuota_actual":     types.Schema(type="INTEGER", description="Número de cuota actual"),
                "comercio":         types.Schema(type="STRING", description="Nombre del comercio"),
                "notas":            types.Schema(type="STRING", description="Notas adicionales"),
                "fuente":           types.Schema(type="STRING", description="Origen del registro"),
                "tipo_cambio_tipo": types.Schema(type="STRING", enum=["blue", "oficial", "mep"],
                                                 description="TC a usar si moneda es USD. Default: oficial."),
                "tarjeta":          types.Schema(type="STRING", description="Identificador de tarjeta, ej: 'BBVA Mastercard 3327'"),
            },
            required=["descripcion", "monto", "moneda", "categoria", "medio_pago"],
        ),
    ),

    types.FunctionDeclaration(
        name="guardar_multiples_gastos",
        description=(
            "Guarda varios gastos de una sola vez. Usá cuando el usuario menciona 2 o más gastos. "
            "SIEMPRE llamar primero con dry_run=True para obtener el listado y mostrárselo al usuario. "
            "El sistema procesará la confirmación automáticamente."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "dry_run": types.Schema(type="BOOLEAN", description="True para registrar como pendiente y obtener preview. Usar SIEMPRE antes de pedir confirmación."),
                "gastos": types.Schema(
                    type="ARRAY",
                    description="Lista de gastos a guardar. Cada elemento tiene los mismos campos que guardar_gasto.",
                    items=types.Schema(
                        type="OBJECT",
                        properties={
                            "descripcion":      types.Schema(type="STRING"),
                            "monto":            types.Schema(type="NUMBER"),
                            "moneda":           types.Schema(type="STRING", enum=["ARS", "USD"]),
                            "categoria":        types.Schema(type="STRING"),
                            "medio_pago":       types.Schema(type="STRING", enum=[
                                                    "credito_ars", "credito_usd", "debito",
                                                    "efectivo_ars", "efectivo_usd", "transferencia"
                                                ]),
                            "fecha":            types.Schema(type="STRING"),
                            "cuotas":           types.Schema(type="INTEGER"),
                            "cuota_actual":     types.Schema(type="INTEGER"),
                            "comercio":         types.Schema(type="STRING"),
                            "notas":            types.Schema(type="STRING"),
                            "tipo_cambio_tipo": types.Schema(type="STRING", enum=["blue", "oficial", "mep"]),
                            "tarjeta":          types.Schema(type="STRING"),
                        },
                        required=["descripcion", "monto", "moneda", "categoria", "medio_pago"],
                    ),
                ),
            },
            required=["gastos"],
        ),
    ),

    types.FunctionDeclaration(
        name="guardar_gasto_recurrente",
        description="Registra un gasto recurrente (suscripción, expensa, etc.).",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "descripcion": types.Schema(type="STRING"),
                "monto":       types.Schema(type="NUMBER"),
                "moneda":      types.Schema(type="STRING", enum=["ARS", "USD"]),
                "frecuencia":  types.Schema(type="STRING", enum=["mensual", "anual", "semanal"]),
                "dia_del_mes": types.Schema(type="INTEGER", description="Día del mes en que vence (1-31)"),
                "categoria":   types.Schema(type="STRING"),
                "medio_pago":  types.Schema(type="STRING"),
            },
            required=["descripcion", "monto", "moneda", "frecuencia", "dia_del_mes", "categoria", "medio_pago"],
        ),
    ),

    types.FunctionDeclaration(
        name="editar_gasto",
        description="Edita uno o más campos de un gasto ya guardado.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "gasto_id":           types.Schema(type="STRING", description="UUID del gasto a editar"),
                "campos_a_modificar": types.Schema(type="OBJECT", description="Dict con los campos a cambiar"),
            },
            required=["gasto_id", "campos_a_modificar"],
        ),
    ),

    types.FunctionDeclaration(
        name="eliminar_gasto",
        description="Elimina un gasto por su UUID. Confirmar con el usuario antes de llamar.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "gasto_id": types.Schema(type="STRING", description="UUID del gasto a eliminar"),
            },
            required=["gasto_id"],
        ),
    ),

    types.FunctionDeclaration(
        name="consultar_gastos",
        description=(
            "Consulta gastos con filtros opcionales. "
            "Filtros: mes, anio, categoria, medio_pago, moneda, fecha_desde, fecha_hasta."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "filtros": types.Schema(
                    type="OBJECT",
                    description="Dict con los filtros a aplicar. Puede estar vacío.",
                ),
            },
        ),
    ),

    types.FunctionDeclaration(
        name="resumen_mensual",
        description="Devuelve el total gastado en un mes agrupado por categoría.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "mes":  types.Schema(type="INTEGER", description="Número de mes (1-12)"),
                "anio": types.Schema(type="INTEGER", description="Año de 4 dígitos"),
            },
            required=["mes", "anio"],
        ),
    ),

    types.FunctionDeclaration(
        name="comparar_meses",
        description="Compara totales y distribución de categorías entre dos meses.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "mes1":  types.Schema(type="INTEGER"),
                "anio1": types.Schema(type="INTEGER"),
                "mes2":  types.Schema(type="INTEGER"),
                "anio2": types.Schema(type="INTEGER"),
            },
            required=["mes1", "anio1", "mes2", "anio2"],
        ),
    ),

    types.FunctionDeclaration(
        name="gastos_recurrentes_activos",
        description="Devuelve los gastos recurrentes activos con su próximo vencimiento.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),

    types.FunctionDeclaration(
        name="obtener_tipo_cambio",
        description="Consulta el tipo de cambio actual (blue, oficial o mep) desde bluelytics.com.ar.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "tipo": types.Schema(type="STRING", enum=["blue", "oficial", "mep"],
                                     description="Tipo de cambio. Default: oficial."),
            },
        ),
    ),

    types.FunctionDeclaration(
        name="obtener_categorias",
        description="Devuelve la lista de categorías activas disponibles en la base de datos.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),

    types.FunctionDeclaration(
        name="tendencia_gastos",
        description=(
            "Muestra la evolución del gasto total en los últimos N meses con variación porcentual. "
            "Útil para ver si el gasto está subiendo o bajando con el tiempo."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "meses": types.Schema(type="INTEGER", description="Cantidad de meses a analizar hacia atrás (default: 6)"),
            },
        ),
    ),

    types.FunctionDeclaration(
        name="top_comercios",
        description=(
            "Devuelve el ranking de los comercios/lugares con mayor gasto en un período. "
            "Muestra dónde se gasta más dinero."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "mes":    types.Schema(type="INTEGER", description="Mes a analizar (default: mes actual)"),
                "anio":   types.Schema(type="INTEGER", description="Año a analizar (default: año actual)"),
                "limite": types.Schema(type="INTEGER", description="Cantidad de resultados (default: 10)"),
            },
        ),
    ),

    types.FunctionDeclaration(
        name="proyeccion_mensual",
        description=(
            "Proyecta cuánto se gastará al final del mes actual, "
            "basándose en el ritmo de gasto de los días transcurridos."
        ),
        parameters=types.Schema(type="OBJECT", properties={}),
    ),

    types.FunctionDeclaration(
        name="previsualizar_pdf_bbva",
        description=(
            "Parsea el PDF BBVA que el usuario acaba de enviar y devuelve un resumen "
            "para que el usuario confirme antes de importar. "
            "Llamar SIEMPRE antes de confirmar_importacion_pdf_bbva."
        ),
        parameters=types.Schema(type="OBJECT", properties={}),
    ),

    types.FunctionDeclaration(
        name="confirmar_importacion_pdf_bbva",
        description=(
            "Guarda en la DB los movimientos nuevos del PDF BBVA ya parseado. "
            "Llamar SOLO después de que el usuario confirme explícitamente tras ver la previsualización."
        ),
        parameters=types.Schema(type="OBJECT", properties={}),
    ),

    types.FunctionDeclaration(
        name="historial_comercio",
        description=(
            "Busca gastos previos del mismo comercio y devuelve la categoría y medio de pago más frecuentes. "
            "Llamar cuando el usuario menciona un comercio específico para auto-categorizar sin preguntar."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "comercio": types.Schema(type="STRING", description="Nombre del comercio a buscar"),
            },
            required=["comercio"],
        ),
    ),

    # ── Comprobantes / Drive ──────────────────────

    types.FunctionDeclaration(
        name="subir_comprobante_a_drive",
        description=(
            "Sube el comprobante/factura que el usuario acaba de enviar a Google Drive. "
            "Los bytes del archivo ya están almacenados internamente. "
            "Los parámetros permiten sobreescribir los datos que Gemini Vision extrajo. "
            "Llamar SOLO después de mostrar un resumen al usuario y recibir confirmación."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "comercio":       types.Schema(type="STRING", description="Nombre del comercio/emisor"),
                "fecha":          types.Schema(type="STRING", description="Fecha del documento YYYY-MM-DD"),
                "tipo":           types.Schema(type="STRING", description="factura, comprobante, ticket, recibo o resumen"),
                "categoria":      types.Schema(type="STRING", description="Categoría del comprobante (debe coincidir con las categorías válidas obtenidas via obtener_categorias)"),
                "monto":          types.Schema(type="NUMBER", description="Monto si es visible"),
                "moneda":         types.Schema(type="STRING", enum=["ARS", "USD"]),
                "nombre_archivo": types.Schema(type="STRING", description="Nombre personalizado para el archivo (sin extensión). Si no se especifica, se usa el nombre sugerido automáticamente."),
            },
        ),
    ),

    types.FunctionDeclaration(
        name="vincular_comprobante_a_gasto",
        description=(
            "Vincula un archivo ya subido a Drive con un gasto existente. "
            "Útil cuando el usuario sube un comprobante de pago para un gasto ya registrado."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "archivo_id": types.Schema(type="STRING", description="El campo 'id' (UUID) devuelto por subir_comprobante_a_drive. NO usar el drive_file_id ni la URL."),
                "gasto_id":   types.Schema(type="STRING", description="UUID del gasto a vincular"),
            },
            required=["archivo_id", "gasto_id"],
        ),
    ),

    types.FunctionDeclaration(
        name="buscar_comprobantes",
        description=(
            "Busca comprobantes y facturas guardados en Drive. "
            "Permite filtrar por comercio, mes, año, categoría y tipo."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "comercio":    types.Schema(type="STRING", description="Nombre del comercio a buscar"),
                "mes":         types.Schema(type="INTEGER", description="Mes (1-12)"),
                "anio":        types.Schema(type="INTEGER", description="Año"),
                "categoria":   types.Schema(type="STRING", description="Categoría del comprobante"),
                "tipo":        types.Schema(type="STRING", description="factura, comprobante, ticket, recibo o resumen"),
                "fecha_desde": types.Schema(type="STRING", description="Fecha desde YYYY-MM-DD"),
                "fecha_hasta": types.Schema(type="STRING", description="Fecha hasta YYYY-MM-DD"),
            },
        ),
    ),
]

TOOLS = types.Tool(function_declarations=_TOOL_DECLARATIONS)

# Tools que efectivamente persisten un gasto en la DB
_SAVE_TOOLS = {"guardar_gasto", "guardar_multiples_gastos", "guardar_gasto_recurrente"}

# Palabras que el usuario usa para confirmar
_PALABRAS_CONFIRMACION = {"sí", "si", "dale", "ok", "confirmado", "va", "confirmo", "listo", "sí dale", "si dale"}

# Palabras que el modelo usa cuando "afirma" haber guardado (señal de alucinación si no hubo tool call)
_PALABRAS_GUARDADO_MODELO = ["guardé", "guardado", "registré", "registrado", "he guardado", "fue guardado", "quedó guardado"]


def _es_confirmacion(msg: str) -> bool:
    normalized = msg.strip().lower()
    return any(normalized == c or normalized.startswith(c + " ") for c in _PALABRAS_CONFIRMACION)


def _es_pura_confirmacion(msg: str) -> bool:
    """Exact-match estricto: solo la palabra de confirmación, sin nada más."""
    normalized = msg.strip().lower().strip("!.,¡¿ ")
    return normalized in _PALABRAS_CONFIRMACION


def _modelo_afirma_guardado(text: str) -> bool:
    normalized = text.lower()
    return any(k in normalized for k in _PALABRAS_GUARDADO_MODELO)


def _format_bypass_response(tool: str, args: dict, resultado: dict) -> str:
    if tool == "guardar_multiples_gastos":
        guardados = resultado.get("guardados", 0)
        errores = resultado.get("errores", [])
        ids = resultado.get("ids", [])
        ids_str = f" · IDs: {', '.join(str(i)[:8] for i in ids)}" if ids else ""
        if errores:
            return f"Guardé {guardados} gastos ✓{ids_str} ({len(errores)} con error)"
        return f"Guardé los {guardados} gastos ✓{ids_str}"

    comercio = args.get("comercio") or args.get("descripcion", "gasto")
    monto = args.get("monto", 0)
    moneda = args.get("moneda", "ARS")
    categoria = args.get("categoria", "")
    medio_pago = args.get("medio_pago", "")
    cuotas = args.get("cuotas", 1)
    gasto_id = resultado.get("id", "")
    cuotas_str = f" · {cuotas} cuotas" if cuotas > 1 else ""
    id_str = f" · ref `{str(gasto_id)[:8]}`" if gasto_id else ""
    return f"Guardé ✓ {comercio} · ${monto:,.0f} {moneda} · {categoria} · {medio_pago}{cuotas_str}{id_str}"


# ──────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────

def _ejecutar_funcion(nombre: str, args: dict) -> str:
    try:
        if nombre == "guardar_gasto":
            if args.pop("dry_run", False) and _chat_id_activo is not None:
                _gasto_pendiente[_chat_id_activo] = {"tool": "guardar_gasto", "args": dict(args)}
                resultado = {
                    "preview": True,
                    "datos": args,
                    "instruccion": "Mostrá este resumen al usuario y preguntá '¿Confirmo?'",
                }
            else:
                resultado = guardar_gasto(**args)
        elif nombre == "guardar_multiples_gastos":
            if args.pop("dry_run", False) and _chat_id_activo is not None:
                _gasto_pendiente[_chat_id_activo] = {"tool": "guardar_multiples_gastos", "args": dict(args)}
                resultado = {
                    "preview": True,
                    "gastos": args.get("gastos", []),
                    "total": len(args.get("gastos", [])),
                    "instruccion": f"Mostrá el listado al usuario y preguntá '¿Guardo los {len(args.get('gastos', []))} gastos?'",
                }
            else:
                resultado = guardar_multiples_gastos(args["gastos"])
        elif nombre == "guardar_gasto_recurrente":
            resultado = guardar_gasto_recurrente(**args)
        elif nombre == "editar_gasto":
            resultado = editar_gasto(**args)
        elif nombre == "eliminar_gasto":
            resultado = eliminar_gasto(**args)
        elif nombre == "consultar_gastos":
            resultado = consultar_gastos(args.get("filtros"))
        elif nombre == "resumen_mensual":
            resultado = resumen_mensual(**args)
        elif nombre == "comparar_meses":
            resultado = comparar_meses(**args)
        elif nombre == "gastos_recurrentes_activos":
            resultado = gastos_recurrentes_activos()
        elif nombre == "obtener_tipo_cambio":
            resultado = obtener_tipo_cambio(args.get("tipo", "oficial"))
        elif nombre == "obtener_categorias":
            resultado = {"categorias": obtener_categorias_activas()}
        elif nombre == "tendencia_gastos":
            resultado = tendencia_gastos(args.get("meses", 6))
        elif nombre == "top_comercios":
            resultado = top_comercios(
                mes=args.get("mes"),
                anio=args.get("anio"),
                limite=args.get("limite", 10),
            )
        elif nombre == "proyeccion_mensual":
            resultado = proyeccion_mensual()
        elif nombre == "previsualizar_pdf_bbva":
            resultado = _previsualizar_pdf_bbva()
        elif nombre == "confirmar_importacion_pdf_bbva":
            resultado = _confirmar_importacion_pdf_bbva()
        elif nombre == "historial_comercio":
            resultado = historial_comercio(**args)
        elif nombre == "subir_comprobante_a_drive":
            resultado = subir_comprobante_a_drive(chat_id=_chat_id_activo, **args)
        elif nombre == "vincular_comprobante_a_gasto":
            resultado = vincular_comprobante_a_gasto(**args)
        elif nombre == "buscar_comprobantes":
            resultado = buscar_comprobantes(**args)
        else:
            resultado = {"error": f"Función desconocida: {nombre}"}
    except Exception as e:
        logger.exception(f"Error ejecutando {nombre}")
        resultado = {"error": str(e)}

    return json.dumps(resultado, ensure_ascii=False, default=str)


# ──────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────

def _build_system_prompt() -> str:
    from bot.db.queries import obtener_comercios
    hoy = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y")
    try:
        comercios = obtener_comercios()
        comercios_str = ", ".join(comercios) if comercios else "ninguno aún"
    except Exception:
        comercios_str = ""

    comercios_section = (
        f"\nCOMERCIOS CONOCIDOS: {comercios_str}\n"
        "Cuando identifiques un comercio (desde texto del usuario, extracto bancario o PDF), "
        "usá el nombre exacto de esta lista si reconocés que es el mismo, sin importar cómo venga escrito. "
        "Por ejemplo, 'SUBE VIAJES - BUSE' → 'BUSES', 'UBER TRIP' → 'Uber'. "
        "Si no hay match claro, usá el nombre más limpio y legible posible.\n"
    ) if comercios_str else ""

    return f"""Sos un asistente financiero personal. Hoy es {hoy}.
{comercios_section}

REGLAS FUNDAMENTALES:
1. Respondés SIEMPRE en español argentino.
2. NUNCA guardás un gasto sin usar dry_run=True primero y recibir confirmación explícita del usuario.
   - 1 gasto → llamá guardar_gasto con dry_run=True y todos los campos inferidos. La función devuelve los datos; mostráselos al usuario y preguntá "¿Confirmo?"
   - 2+ gastos → llamá guardar_multiples_gastos con dry_run=True. Mostrá el listado y preguntá "¿Guardo los N gastos?"
   - El sistema procesará la confirmación automáticamente; no necesitás llamar la función de nuevo.
   - Si el usuario corrige algo ("sí pero X", "cambiá X"), actualizá los datos y llamá dry_run de nuevo.
3. Palabras de confirmación válidas: "sí", "si", "dale", "ok", "confirmado", "va", "sí dale", "confirmo", "listo".
   Si el usuario confirma con texto adicional ("sí pero X"), NO es confirmación pura: actualizá y hacé dry_run de nuevo.
   FALLBACK: si el usuario confirmó claramente pero el sistema no procesó la acción, llamá guardar_gasto sin dry_run.
4. Si el usuario corrige algo en su respuesta, actualizar los datos y volver a pedir confirmación.
5. Usás el tipo de cambio **oficial** por defecto para conversiones de USD a ARS, salvo que el usuario indique otro.
6. Siempre informás el tipo de cambio usado cuando guardás un gasto en USD.
7. Para categorías, medio de pago y nombre de comercio: si el usuario menciona un comercio específico,
   seguí estos pasos EN ORDEN:
   a) Primero buscá en COMERCIOS CONOCIDOS si el nombre (o parte de él) coincide con alguno de la lista,
      aunque venga escrito diferente o truncado (ej: "SUBE VIAJES - BUSE" → "BUSES", "UBER TRIP" → "Uber").
      Si hay match, usá ese nombre canónico de la lista.
   b) Luego llamá `historial_comercio` pasando el nombre NORMALIZADO (el de la lista, no el raw).
      NUNCA pasés el string crudo del email/extracto si ya encontraste un match en COMERCIOS CONOCIDOS.
   c) Si `historial_comercio` devuelve historial:
      - Usá el campo `comercio` devuelto como nombre canónico.
      - Usá la categoría y medio de pago más frecuentes directamente, sin preguntar.
   Si no hay historial, SIEMPRE llamá `obtener_categorias` para ver las categorías válidas disponibles.
   NUNCA inventes ni uses una categoría que no esté en esa lista. Solo preguntás al usuario si
   realmente no podés inferir la categoría correcta del contexto.
8. El campo `comercio` SIEMPRE debe completarse cuando hay un comercio, marca o servicio identificable
   (Cabify, Mercado Pago, Netflix, Farmacity, etc.). La `descripcion` es para el concepto del gasto
   ("Viaje al aeropuerto", "Suscripción mensual"), no para el nombre del negocio. Si el usuario dice
   algo como "almuerzo en McDonald's", comercio = "McDonald's" y descripcion = "Almuerzo".
   Para transferencias, el `comercio` es el destinatario (persona o negocio que recibió el dinero).
9. Las consultas y análisis responden con números concretos, no evasivas.
10. Sos conciso en las respuestas del día a día, más detallado en análisis financieros.

COMPROBANTES Y FACTURAS (Google Drive):
11. Cuando el usuario manda una foto o PDF de un comprobante/factura, los datos extraídos se incluyen
    en el mensaje junto con el nombre de archivo sugerido. Mostrá ese resumen al usuario incluyendo
    el nombre que se usará para guardarlo (campo "Nombre de archivo sugerido"). El usuario puede
    cambiarlo antes de confirmar; si lo hace, pasá el nuevo nombre en el parámetro nombre_archivo.
    Preguntá:
    - "¿Subo este comprobante a Drive?" (si solo quiere guardar el archivo)
    - "¿Subo a Drive y guardo el gasto también?" (si corresponde crear el gasto)
    Si el usuario dice "solo guardá esto en drive" o similar, subí sin crear gasto.
12. Al confirmar subida, llamá `subir_comprobante_a_drive` con los datos. Después de subir exitosamente,
    mostrá: nombre de archivo, ubicación en Drive y link.
    Si también se creó un gasto (con `guardar_gasto`), SIEMPRE vinculá el comprobante al gasto
    llamando `vincular_comprobante_a_gasto` con:
    - archivo_id = el campo "id" del resultado de subir_comprobante_a_drive (es un UUID, ej: "d20555aa-...")
    - gasto_id = el campo "id" del resultado de guardar_gasto
    NO uses el link ni el drive_file_id como archivo_id. Hacelo automáticamente sin preguntar.
13. Si el usuario pide buscar un comprobante ("mostrá la factura de Edenor de febrero"),
    usá `buscar_comprobantes` y devolvé nombre, fecha, monto y link de Drive.
14. Si al subir un comprobante detectás que hay un gasto del mismo comercio en fechas cercanas,
    vinculalos automáticamente con `vincular_comprobante_a_gasto` e informá al usuario.
15. Si se detecta un duplicado (mismo comercio, fecha y tipo), informá al usuario y no subas de nuevo.
16. Para la categoría de un comprobante: si el comprobante se vincula a un gasto, usá la misma categoría
    del gasto. Si no hay gasto, llamá `obtener_categorias` igual que para gastos. NUNCA uses categorías
    inventadas como "Servicios", "Salud" o "Impuestos" si no existen en la lista de categorías activas.
"""


# ──────────────────────────────────────────────
# Loop principal del agente
# ──────────────────────────────────────────────

def run_agent(
    user_message: str,
    history: list[dict] | None = None,
    chat_id: int | None = None,
) -> str:
    """
    Procesa un mensaje del usuario y devuelve la respuesta del agente.

    Args:
        user_message: Texto (o mensaje enriquecido) del usuario.
        history: Lista de dicts {"role": "user"|"model", "parts": [str]}.
        chat_id: ID del chat de Telegram (necesario para el contexto de PDF).
    """
    global _chat_id_activo
    _chat_id_activo = chat_id

    # ── Bypass de confirmación ────────────────────────────────────────────────
    # Si el mensaje es una confirmación pura y hay un gasto pendiente,
    # ejecutamos la tool directamente sin pasar por el modelo.
    if chat_id is not None and _es_pura_confirmacion(user_message):
        if chat_id in _gasto_pendiente:
            pending = _gasto_pendiente.pop(chat_id)
            resultado_str = _ejecutar_funcion(pending["tool"], pending["args"])
            resultado = json.loads(resultado_str)
            if "error" in resultado:
                logger.warning(f"[BYPASS ERROR] chat_id={chat_id} tool={pending['tool']} error={resultado['error']}")
                return f"Ocurrió un error al guardar: {resultado['error']}. Intentá de nuevo."
            logger.info(f"[BYPASS] chat_id={chat_id} tool={pending['tool']} OK")
            return _format_bypass_response(pending["tool"], pending["args"], resultado)
    # Cualquier mensaje que no sea bypass limpia el pending viciado
    if chat_id is not None:
        _gasto_pendiente.pop(chat_id, None)
    # ─────────────────────────────────────────────────────────────────────────

    config = types.GenerateContentConfig(
        system_instruction=_build_system_prompt(),
        tools=[TOOLS],
    )

    # Convertir historial al formato del nuevo SDK
    gemini_history = []
    for turn in (history or []):
        gemini_history.append(
            types.Content(role=turn["role"], parts=[types.Part(text=p) for p in turn["parts"]])
        )

    def _needs_paid_fallback(exc: Exception) -> bool:
        """True para errores que se resuelven cambiando a la API key paga."""
        if isinstance(exc, genai.errors.ClientError) and exc.code == 429:
            return True
        if isinstance(exc, genai.errors.ServerError) and exc.code == 503:
            return True
        return False

    def _send(chat_obj, payload):
        """Envía un mensaje con fallback automático a la key paga en 429/503."""
        nonlocal chat
        try:
            return chat_obj.send_message(payload)
        except Exception as e:
            if _needs_paid_fallback(e):
                logger.warning(f"Error {e.__class__.__name__} ({getattr(e, 'code', '?')}), reintentando con API key paga")
                chat = create_chat_with_fallback(
                    model=MODEL, config=config, history=gemini_history, force_paid=True
                )
                return chat.send_message(payload)
            raise

    chat = create_chat_with_fallback(model=MODEL, config=config, history=gemini_history)
    response = _send(chat, user_message)

    save_tool_called = False

    for _ in range(MAX_ITER):
        if not response.candidates or not response.candidates[0].content.parts:
            break

        function_calls = [
            part.function_call
            for part in response.candidates[0].content.parts
            if part.function_call and part.function_call.name
        ]

        if not function_calls:
            break

        function_response_parts = []
        for fc in function_calls:
            fc_args = dict(fc.args)
            if fc.name in _SAVE_TOOLS and not fc_args.get("dry_run"):
                save_tool_called = True
            resultado_str = _ejecutar_funcion(fc.name, fc_args)
            logger.info(f"Tool: {fc.name} → {resultado_str[:200]}")
            function_response_parts.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": resultado_str},
                )
            )

        response = _send(chat, function_response_parts)

    # ── Guardia anti-alucinación ──────────────────────────────────────────────
    # Si el usuario confirmó y el modelo afirmó haber guardado pero no llamó
    # ninguna save tool, inyectamos un mensaje de recovery forzado.
    try:
        final_text = response.text or ""
    except Exception:
        final_text = ""

    if _es_confirmacion(user_message) and not save_tool_called and _modelo_afirma_guardado(final_text):
        logger.warning(
            f"[ALUCINACION DETECTADA] chat_id={chat_id} | Usuario confirmó, modelo dijo 'guardado' "
            f"pero no llamó ninguna save tool. Ejecutando recovery."
        )
        recovery_msg = (
            "SISTEMA: Detecté que afirmaste haber guardado el gasto pero no llamaste a "
            "`guardar_gasto` ni `guardar_multiples_gastos`. El gasto AÚN NO fue guardado. "
            "Llamá AHORA MISMO a la función de guardado con los datos del gasto pendiente de confirmación."
        )
        try:
            response = chat.send_message(recovery_msg)
            if response.candidates and response.candidates[0].content.parts:
                recovery_calls = [
                    part.function_call
                    for part in response.candidates[0].content.parts
                    if part.function_call and part.function_call.name
                ]
                if recovery_calls:
                    recovery_parts = []
                    for fc in recovery_calls:
                        resultado_str = _ejecutar_funcion(fc.name, dict(fc.args))
                        logger.info(f"Tool (recovery): {fc.name} → {resultado_str[:200]}")
                        recovery_parts.append(
                            types.Part.from_function_response(
                                name=fc.name,
                                response={"result": resultado_str},
                            )
                        )
                    response = chat.send_message(recovery_parts)
                else:
                    logger.error(
                        f"[RECOVERY FALLIDO] chat_id={chat_id} | El modelo no llamó ninguna tool "
                        f"en el recovery. El gasto se perdió."
                    )
        except Exception:
            logger.exception(f"[RECOVERY ERROR] chat_id={chat_id} | Error en recovery de alucinación")
    # ─────────────────────────────────────────────────────────────────────────

    try:
        text = response.text
        if not text or not text.strip():
            return "Procesé tu solicitud pero no generé una respuesta. ¿Necesitás algo más?"
        return text
    except Exception:
        return "Lo siento, no pude procesar tu mensaje. Intentá de nuevo."
