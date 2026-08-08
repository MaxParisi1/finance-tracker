"""
Parseo del PDF de expensas (liquidación por unidad funcional).

Dos problemas del PDF que obligan a trabajar a nivel de palabras y no de texto:

1. Los números de 6 cifras se parten en dos tokens con ~3pt de separación:
   el total "258.198,55" se extrae como "2" + "58.198,55". Con extract_text()
   plano se leería 2 y 58.198,55 como dos valores distintos.

2. La fila tiene ~20 columnas con encabezados multilínea, así que mapear por
   nombre de columna es frágil. En su lugar el total es el último numérico y se
   valida aritméticamente: tiene que ser igual a la suma de un sufijo de las
   columnas anteriores (expensa del mes + fondo + ajustes). Si no cierra, se
   levanta ExpensasNoParseable en vez de escribir un número dudoso.
"""

import io
import logging
import re
from dataclasses import dataclass

from bot.tools.montos import parse_monto_ar, parse_fecha_ar, MontoInvalido

logger = logging.getLogger(__name__)

__all__ = ["FilaUnidad", "ExpensasNoParseable", "unir_tokens_partidos",
           "parsear_fila_unidad", "parsear_pdf_unidades"]

# Separación máxima (en puntos) para considerar que dos tokens son en realidad
# un solo número partido por el renderer. Los tokens legítimamente distintos de
# esta tabla están a más de 20pt; los partidos, a ~3pt.
GAP_MAXIMO = 6.0

# Tolerancia al validar la suma (redondeos de centavos).
TOLERANCIA = 0.02


class ExpensasNoParseable(Exception):
    """No se pudo leer la fila de la unidad con confianza suficiente."""


@dataclass(frozen=True)
class FilaUnidad:
    unidad: str
    total: float
    vencimiento: object | None = None  # datetime.date


def unir_tokens_partidos(palabras: list[dict]) -> list[str]:
    """
    Une palabras contiguas cuando el hueco entre ellas es menor a GAP_MAXIMO.
    `palabras` son dicts de pdfplumber con x0, x1 y text, ordenados por x0.
    """
    if not palabras:
        return []

    ordenadas = sorted(palabras, key=lambda w: w["x0"])
    salida = [ordenadas[0]["text"]]
    anterior = ordenadas[0]

    for w in ordenadas[1:]:
        if (w["x0"] - anterior["x1"]) < GAP_MAXIMO:
            salida[-1] += w["text"]
        else:
            salida.append(w["text"])
        anterior = w

    return salida


def _numericos(tokens: list[str]) -> list[float]:
    """Montos de la fila, en orden. Descarta porcentajes, unidad, piso y nombre."""
    valores = []
    for tok in tokens:
        if "%" in tok or not re.search(r"\d", tok):
            continue
        if not re.fullmatch(r"-?[\d.,]+", tok):
            continue
        try:
            valores.append(parse_monto_ar(tok))
        except MontoInvalido:
            continue
    return valores


def _validar_total(valores: list[float]) -> float:
    """
    El último numérico es el Total. Se valida contra la suma de algún sufijo de
    las columnas previas; si ningún sufijo cierra, la fila se leyó mal.
    """
    if len(valores) < 3:
        raise ExpensasNoParseable(f"muy pocos valores en la fila ({len(valores)})")

    total = valores[-1]
    previos = valores[:-1]

    acumulado = 0.0
    for v in reversed(previos):
        acumulado += v
        if abs(acumulado - total) <= TOLERANCIA:
            return total

    raise ExpensasNoParseable(
        f"el total {total} no coincide con la suma de ninguna combinación de columnas "
        f"({previos[-6:]}) — el formato del PDF probablemente cambió"
    )


def parsear_fila_unidad(palabras_fila: list[dict], unidad: str) -> float:
    """Devuelve el total a pagar de la unidad, validado aritméticamente."""
    tokens = unir_tokens_partidos(palabras_fila)
    if not tokens or tokens[0].strip() != unidad:
        raise ExpensasNoParseable(f"la fila no arranca con la unidad {unidad!r}: {tokens[:3]}")
    return _validar_total(_numericos(tokens))


def parsear_pdf_unidades(pdf_bytes: bytes, unidad: str) -> FilaUnidad:
    """
    Busca la fila de `unidad` en el PDF de liquidación y devuelve su total.
    Se importa pdfplumber acá adentro para no pagarlo en el arranque del bot.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pagina in pdf.pages:
            palabras = pagina.extract_words()
            ancla = next(
                (w for w in palabras if w["text"].strip() == unidad and w["x0"] < 50),
                None,
            )
            if ancla is None:
                continue

            fila = [w for w in palabras if abs(w["top"] - ancla["top"]) < 3]
            total = parsear_fila_unidad(fila, unidad)

            texto = pagina.extract_text() or ""
            vto = re.search(r"Vencimiento:\s*(\d{2}/\d{2}/\d{4})", texto)
            vencimiento = parse_fecha_ar(vto.group(1)) if vto else None

            logger.info("Expensas UF %s: total=%s vence=%s", unidad, total, vencimiento)
            return FilaUnidad(unidad=unidad, total=total, vencimiento=vencimiento)

    raise ExpensasNoParseable(f"no encontré la unidad {unidad!r} en el PDF")
