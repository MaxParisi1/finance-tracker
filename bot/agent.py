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

from google import genai
from google.genai import types

from bot.tools.gastos import (
    guardar_gasto,
    guardar_gasto_recurrente,
    editar_gasto,
    eliminar_gasto,
    consultar_gastos,
    resumen_mensual,
    comparar_meses,
    gastos_recurrentes_activos,
)
from bot.tools.tipo_cambio import obtener_tipo_cambio
from bot.db.queries import obtener_categorias_activas

logger = logging.getLogger(__name__)

MAX_ITER = 5
MODEL = "gemini-2.5-flash"

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
                                                 description="TC a usar si moneda es USD. Default: blue."),
            },
            required=["descripcion", "monto", "moneda", "categoria", "medio_pago"],
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
                                     description="Tipo de cambio. Default: blue."),
            },
        ),
    ),

    types.FunctionDeclaration(
        name="obtener_categorias",
        description="Devuelve la lista de categorías activas disponibles en la base de datos.",
        parameters=types.Schema(type="OBJECT", properties={}),
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
            resultado = obtener_tipo_cambio(args.get("tipo", "blue"))
        elif nombre == "obtener_categorias":
            resultado = {"categorias": obtener_categorias_activas()}
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
1. Respondés SIEMPRE en español argentino informal (vos, che, dale, etc.).
2. NUNCA guardás un gasto sin mostrar primero un resumen y recibir confirmación explícita del usuario.
   Formato de confirmación: "Voy a guardar: **$MONTO MONEDA** en **DESCRIPCIÓN** (CATEGORÍA) · MEDIO_PAGO · FECHA. ¿Confirmo?"
3. Palabras de confirmación válidas: "sí", "si", "dale", "ok", "confirmado", "va", "sí dale", "confirmo".
4. Si el usuario corrige algo en su respuesta, actualizar los datos y volver a pedir confirmación.
5. Usás el tipo de cambio **blue** por defecto para conversiones de USD a ARS, salvo que el usuario indique otro.
6. Siempre informás el tipo de cambio usado cuando guardás un gasto en USD.
7. Para categorías, primero consultás las disponibles en la DB. Solo creás una nueva si ninguna aplica.
   Si no podés asignar con suficiente confianza, preguntás al usuario.
8. Las consultas y análisis responden con números concretos, no evasivas.
9. Sos conciso en las respuestas del día a día, más detallado en análisis financieros.
"""


# ──────────────────────────────────────────────
# Loop principal del agente
# ──────────────────────────────────────────────

def run_agent(user_message: str, history: list[dict] | None = None) -> str:
    """
    Procesa un mensaje del usuario y devuelve la respuesta del agente.

    history: lista de dicts {"role": "user"|"model", "parts": [str]}
    """
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

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

    chat = client.chats.create(model=MODEL, config=config, history=gemini_history)

    response = chat.send_message(user_message)

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

        response = chat.send_message(function_response_parts)

    try:
        return response.text
    except Exception:
        return "Lo siento, no pude procesar tu mensaje. Intentá de nuevo."
