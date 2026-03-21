"""
Parseo de resúmenes de tarjeta BBVA Argentina (PDF).

Estrategia:
  1. pdfplumber → extraer texto
  2. Si el texto es legible → Gemini estructura los datos
  3. Fallback → pdf2image convierte páginas a imágenes → Gemini Vision extrae la tabla

Detección de duplicados: fecha exacta + monto exacto + similitud descripción >= 80%
"""

import io
import os
import json
import re
import difflib
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"

# ──────────────────────────────────────────────
# Prompt compartido para texto y visión
# ──────────────────────────────────────────────

_PROMPT_BBVA = """
Analizá este resumen de tarjeta de crédito BBVA Argentina y extraé TODOS los movimientos de compras.

Devolvé ÚNICAMENTE un JSON array con esta estructura (sin texto adicional):
[
  {
    "fecha": "YYYY-MM-DD",
    "descripcion": "nombre del comercio o descripción del movimiento",
    "monto": <número float, positivo para compras, negativo para pagos/créditos>,
    "moneda": "ARS o USD",
    "cuotas": <número entero total de cuotas, 1 si es al contado>,
    "cuota_actual": <número de cuota actual, 1 si es al contado>,
    "tipo": "compra | cuota | pago | ajuste"
  }
]

Reglas importantes:
- Incluir TODOS los movimientos: compras, cuotas, pagos, ajustes.
- Para movimientos en cuotas, detectar el patrón "(X/N)" o "CTA X/N" en la descripción.
  Extraer X como cuota_actual y N como cuotas. NO duplicar los registros.
- Si el año no aparece en la fecha, inferirlo del contexto del resumen.
- Montos en USD si la descripción indica USD o la columna es en dólares.
- Los pagos del resumen anterior deben tener monto negativo y tipo "pago".
- Clasificar como tipo "ajuste" TODO lo que NO sea una compra real: impuestos (IMPUESTO DE SELLOS, IVA, IIBB), cargos (DB.RG, retenciones, percepciones), intereses, financiación, comisiones, bonificaciones, acreditaciones, y cualquier cargo administrativo del banco.
- Respondé ÚNICAMENTE con el JSON array válido, sin markdown ni texto adicional.
"""


# ──────────────────────────────────────────────
# Evaluación de calidad del texto extraído
# ──────────────────────────────────────────────

def _texto_es_usable(texto: str) -> bool:
    """
    Determina si el texto extraído por pdfplumber es suficientemente legible
    para pasárselo a Gemini.
    """
    if not texto or len(texto.strip()) < 200:
        return False
    # Verificar que haya al menos varios montos con formato de número
    montos = re.findall(r"\d{1,3}(?:[.,]\d{3})*[.,]\d{2}", texto)
    if len(montos) < 3:
        return False
    # Verificar que haya alguna fecha
    fechas = re.findall(r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?", texto)
    return len(fechas) >= 1


# ──────────────────────────────────────────────
# Parsing con texto (pdfplumber)
# ──────────────────────────────────────────────

def _parsear_con_texto(texto: str) -> list[dict]:
    """Llama a Gemini con el texto extraído y devuelve los movimientos."""
    from bot.gemini_client import generate_with_fallback

    contenido = f"{_PROMPT_BBVA}\n\nTexto del resumen:\n{texto}"

    response = generate_with_fallback(
        model=MODEL,
        contents=contenido,
    )

    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw)


# ──────────────────────────────────────────────
# Fallback: parsing con visión (pdf2image)
# ──────────────────────────────────────────────

def _parsear_con_vision(pdf_bytes: bytes) -> list[dict]:
    """
    Convierte cada página del PDF a imagen y usa Gemini Vision para extraer datos.
    Combina resultados de todas las páginas.
    """
    from google.genai import types
    from pdf2image import convert_from_bytes
    from PIL import Image
    from bot.gemini_client import generate_with_fallback

    # Convertir PDF a imágenes (DPI 150 es suficiente para texto)
    imagenes = convert_from_bytes(pdf_bytes, dpi=150)
    logger.info(f"PDF fallback: {len(imagenes)} páginas convertidas a imagen")

    todos_movimientos = []

    for i, imagen in enumerate(imagenes):
        # Convertir PIL Image a bytes JPEG
        buffer = io.BytesIO()
        imagen.save(buffer, format="JPEG", quality=85)
        img_bytes = buffer.getvalue()

        response = generate_with_fallback(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                types.Part(text=_PROMPT_BBVA),
            ],
        )

        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

        try:
            movimientos = json.loads(raw)
            if isinstance(movimientos, list):
                todos_movimientos.extend(movimientos)
        except json.JSONDecodeError:
            logger.warning(f"Página {i+1}: JSON inválido en respuesta de visión")

    return todos_movimientos


# ──────────────────────────────────────────────
# Detección de duplicados
# ──────────────────────────────────────────────

def _similitud(a: str, b: str) -> float:
    """Calcula similitud entre dos strings (0.0 a 1.0)."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def detectar_duplicados(
    movimientos: list[dict],
    gastos_existentes: list[dict],
    umbral_similitud: float = 0.8,
) -> tuple[list[dict], list[dict]]:
    """
    Separa movimientos en nuevos y duplicados comparando contra gastos existentes.

    Criterio de duplicado: misma fecha + mismo monto + similitud descripción >= umbral.

    Returns:
        (nuevos, duplicados)
    """
    nuevos = []
    duplicados = []

    for mov in movimientos:
        es_duplicado = False
        for gasto in gastos_existentes:
            # Comparar fecha
            if str(gasto.get("fecha", ""))[:10] != str(mov.get("fecha", ""))[:10]:
                continue
            # Comparar monto
            if abs(float(gasto.get("monto_original", 0)) - abs(float(mov.get("monto", 0)))) > 0.01:
                continue
            # Comparar descripción
            sim = _similitud(
                str(gasto.get("descripcion", "")),
                str(mov.get("descripcion", "")),
            )
            if sim >= umbral_similitud:
                es_duplicado = True
                break

        if es_duplicado:
            duplicados.append(mov)
        else:
            nuevos.append(mov)

    return nuevos, duplicados


# ──────────────────────────────────────────────
# Función principal
# ──────────────────────────────────────────────

def importar_pdf_bbva(pdf_bytes: bytes, gastos_existentes: list[dict] | None = None) -> dict:
    """
    Parsea un resumen de tarjeta BBVA y devuelve los movimientos listos para importar.

    Args:
        pdf_bytes: Bytes del archivo PDF.
        gastos_existentes: Lista de gastos ya en la DB para detección de duplicados.

    Returns:
        {
            "movimientos_nuevos": [...],
            "movimientos_duplicados": [...],
            "total_encontrados": int,
            "total_nuevos": int,
            "total_duplicados": int,
            "fecha_desde": "YYYY-MM-DD" o None,
            "fecha_hasta": "YYYY-MM-DD" o None,
            "metodo_usado": "texto" o "vision",
        }
    """
    import pdfplumber

    gastos_existentes = gastos_existentes or []
    metodo = "texto"
    movimientos = []

    # ── Estrategia primaria: pdfplumber ──
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            texto_completo = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )

        if _texto_es_usable(texto_completo):
            logger.info("PDF BBVA: usando extracción de texto con pdfplumber")
            movimientos = _parsear_con_texto(texto_completo)
        else:
            logger.info("PDF BBVA: texto no usable, usando fallback visión")
            metodo = "vision"
            movimientos = _parsear_con_vision(pdf_bytes)

    except Exception as e:
        logger.warning(f"pdfplumber falló ({e}), intentando visión")
        metodo = "vision"
        movimientos = _parsear_con_vision(pdf_bytes)

    # ── Marcar fuente y filtrar pagos/créditos ──
    for mov in movimientos:
        mov["fuente"] = "pdf_bbva"

    # Excluir pagos y créditos: solo importar compras y cuotas
    movimientos = [
        m for m in movimientos
        if m.get("tipo", "compra") not in ("pago", "ajuste") and float(m.get("monto", 0)) > 0
    ]

    # ── Detección de duplicados ──
    nuevos, duplicados = detectar_duplicados(movimientos, gastos_existentes)

    # ── Rango de fechas ──
    fechas = [m["fecha"] for m in movimientos if m.get("fecha")]
    fecha_desde = min(fechas) if fechas else None
    fecha_hasta = max(fechas) if fechas else None

    return {
        "movimientos_nuevos": nuevos,
        "movimientos_duplicados": duplicados,
        "total_encontrados": len(movimientos),
        "total_nuevos": len(nuevos),
        "total_duplicados": len(duplicados),
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "metodo_usado": metodo,
    }


# ──────────────────────────────────────────────
# Guardar movimientos confirmados en la DB
# ──────────────────────────────────────────────

def guardar_movimientos_bbva(movimientos: list[dict]) -> int:
    """
    Guarda en la DB los movimientos confirmados del PDF BBVA.
    Maneja conversión de moneda si corresponde.
    Devuelve la cantidad de registros insertados.
    """
    from bot.tools.gastos import guardar_gasto
    from bot.tools.tipo_cambio import obtener_tipo_cambio

    # Obtener TC blue una sola vez para toda la importación
    tc_blue = None

    guardados = 0
    for mov in movimientos:
        try:
            moneda = (mov.get("moneda") or "ARS").upper()
            monto = abs(float(mov.get("monto", 0)))

            descripcion = mov.get("descripcion", "Sin descripción")
            cuotas = int(mov.get("cuotas", 1))
            cuota_actual = int(mov.get("cuota_actual", 1))

            # Agregar indicador de cuota a la descripción si aplica
            if cuotas > 1:
                descripcion = f"{descripcion} ({cuota_actual}/{cuotas})"

            guardar_gasto(
                descripcion=descripcion,
                monto=monto,
                moneda=moneda,
                categoria="Otros",  # El agente puede sugerir después
                medio_pago="credito_ars" if moneda == "ARS" else "credito_usd",
                fecha=mov.get("fecha"),
                cuotas=cuotas,
                cuota_actual=cuota_actual,
                fuente="pdf_bbva",
            )
            guardados += 1
        except Exception as e:
            logger.error(f"Error guardando movimiento BBVA: {e} | {mov}")

    return guardados
