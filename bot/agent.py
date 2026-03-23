"""
Agente financiero con Function Calling nativo de Gemini.
Loop manual: sin LangChain ni frameworks intermedios.
Máximo MAX_ITER iteraciones por mensaje para evitar loops infinitos.
SDK: google-genai (nuevo, reemplaza google-generativeai)
"""

import os
import json
import logging
from datetime import date

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
            "Guarda un gasto en la base de datos. "
            "SIEMPRE mostrar un resumen al usuario y esperar confirmación antes de llamar esta función."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
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
            "Guarda varios gastos de una sola vez, tras recibir confirmación explícita del usuario. "
            "Usá esta tool cuando el usuario menciona 2 o más gastos en el mismo mensaje. "
            "SIEMPRE mostrar el listado completo y pedir confirmación antes de llamarla."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
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
                "comercio":  types.Schema(type="STRING", description="Nombre del comercio/emisor"),
                "fecha":     types.Schema(type="STRING", description="Fecha del documento YYYY-MM-DD"),
                "tipo":      types.Schema(type="STRING", description="factura, comprobante, ticket, recibo o resumen"),
                "categoria": types.Schema(type="STRING", description="Categoría: Servicios, Salud, Impuestos u Otros"),
                "monto":     types.Schema(type="NUMBER", description="Monto si es visible"),
                "moneda":    types.Schema(type="STRING", enum=["ARS", "USD"]),
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
                "archivo_id": types.Schema(type="STRING", description="UUID del archivo en archivos_drive"),
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


# ──────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────

def _ejecutar_funcion(nombre: str, args: dict) -> str:
    try:
        if nombre == "guardar_gasto":
            resultado = guardar_gasto(**args)
        elif nombre == "guardar_multiples_gastos":
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
    hoy = date.today().strftime("%d/%m/%Y")
    return f"""Sos un asistente financiero personal. Hoy es {hoy}.

REGLAS FUNDAMENTALES:
1. Respondés SIEMPRE en español argentino.
2. NUNCA guardás un gasto sin mostrar primero un resumen y recibir confirmación explícita del usuario.
   - 1 gasto → formato: "Voy a guardar: **$MONTO MONEDA** en **DESCRIPCIÓN** (CATEGORÍA) · MEDIO_PAGO · FECHA. ¿Confirmo?"
   - 2+ gastos → listado numerado + total, luego "¿Guardo los N gastos?". Usar guardar_multiples_gastos, no llamar guardar_gasto N veces.
3. Palabras de confirmación válidas: "sí", "si", "dale", "ok", "confirmado", "va", "sí dale", "confirmo".
4. Si el usuario corrige algo en su respuesta, actualizar los datos y volver a pedir confirmación.
5. Usás el tipo de cambio **oficial** por defecto para conversiones de USD a ARS, salvo que el usuario indique otro.
6. Siempre informás el tipo de cambio usado cuando guardás un gasto en USD.
7. Para categorías, medio de pago y nombre de comercio: si el usuario menciona un comercio específico,
   primero llamá `historial_comercio` para ver si hay gastos previos. Si hay historial:
   - Usá el campo `comercio` devuelto como nombre canónico (no el que mencionó el usuario ni el que
     parseaste vos), para mantener consistencia en los datos.
   - Usá la categoría y medio de pago más frecuentes directamente, sin preguntar.
   Si no hay historial, consultá las categorías disponibles e inferí por contexto. Solo preguntás
   si realmente no podés determinarlo.
8. El campo `comercio` SIEMPRE debe completarse cuando hay un comercio, marca o servicio identificable
   (Cabify, Mercado Pago, Netflix, Farmacity, etc.). La `descripcion` es para el concepto del gasto
   ("Viaje al aeropuerto", "Suscripción mensual"), no para el nombre del negocio. Si el usuario dice
   algo como "almuerzo en McDonald's", comercio = "McDonald's" y descripcion = "Almuerzo".
   Para transferencias, el `comercio` es el destinatario (persona o negocio que recibió el dinero).
9. Las consultas y análisis responden con números concretos, no evasivas.
10. Sos conciso en las respuestas del día a día, más detallado en análisis financieros.

COMPROBANTES Y FACTURAS (Google Drive):
11. Cuando el usuario manda una foto o PDF de un comprobante/factura, los datos extraídos se incluyen
    en el mensaje. Mostrá un resumen al usuario (comercio, fecha, tipo, monto si hay) y preguntá:
    - "¿Subo este comprobante a Drive?" (si solo quiere guardar el archivo)
    - "¿Subo a Drive y guardo el gasto también?" (si corresponde crear el gasto)
    Si el usuario dice "solo guardá esto en drive" o similar, subí sin crear gasto.
12. Al confirmar subida, llamá `subir_comprobante_a_drive` con los datos. Después de subir exitosamente,
    mostrá: nombre de archivo, ubicación en Drive y link.
    Si también se creó un gasto (con `guardar_gasto`), SIEMPRE vinculá el comprobante al gasto
    llamando `vincular_comprobante_a_gasto` con el archivo_id (devuelto por subir_comprobante_a_drive)
    y el gasto_id (devuelto por guardar_gasto). Hacelo automáticamente sin preguntar.
13. Si el usuario pide buscar un comprobante ("mostrá la factura de Edenor de febrero"),
    usá `buscar_comprobantes` y devolvé nombre, fecha, monto y link de Drive.
14. Si al subir un comprobante detectás que hay un gasto del mismo comercio en fechas cercanas,
    vinculalos automáticamente con `vincular_comprobante_a_gasto` e informá al usuario.
15. Si se detecta un duplicado (mismo comercio, fecha y tipo), informá al usuario y no subas de nuevo.
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

    chat = create_chat_with_fallback(model=MODEL, config=config, history=gemini_history)

    try:
        response = chat.send_message(user_message)
    except genai.errors.ClientError as e:
        if e.code == 429:
            chat = create_chat_with_fallback(
                model=MODEL, config=config, history=gemini_history, force_paid=True
            )
            response = chat.send_message(user_message)
        else:
            raise

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
            resultado_str = _ejecutar_funcion(fc.name, dict(fc.args))
            logger.info(f"Tool: {fc.name} → {resultado_str[:200]}")
            function_response_parts.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": resultado_str},
                )
            )

        try:
            response = chat.send_message(function_response_parts)
        except genai.errors.ClientError as e:
            if e.code == 429:
                chat = create_chat_with_fallback(
                    model=MODEL, config=config, history=gemini_history, force_paid=True
                )
                response = chat.send_message(function_response_parts)
            else:
                raise

    try:
        text = response.text
        if not text or not text.strip():
            return "Procesé tu solicitud pero no generé una respuesta. ¿Necesitás algo más?"
        return text
    except Exception:
        return "Lo siento, no pude procesar tu mensaje. Intentá de nuevo."
