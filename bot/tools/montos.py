"""
Parseo de montos y fechas en formato argentino, tolerante a los defectos de
extracción de PDF que aparecen en facturas y comprobantes reales.

Casos cubiertos (todos observados en documentos reales):
  "13.405,84"    → 13405.84   formato AR estándar
  "30562,17"     → 30562.17   sin separador de miles
  "13.40584"     → 13405.84   Mercado Pago: pierde la coma (centavos en tipografía chica)
  "2 58.198,55"  → 258198.55  expensas: el PDF parte el número en dos tokens
  "$ 0,00"       → 0.0
  "-4.000,01"    → -4000.01

La ambigüedad real es "13.40584": ¿son 13405.84 o 1340584? Se resuelve por
longitud del último grupo — si tiene más de 3 dígitos no puede ser un grupo de
miles, así que los 2 últimos son centavos.
"""

import re
from datetime import date

__all__ = ["parse_monto_ar", "parse_fecha_ar", "montos_en_texto", "formatear_monto_ar",
           "MontoInvalido"]


class MontoInvalido(ValueError):
    """El token no representa un monto reconocible. Nunca se devuelve un valor inventado."""


# Un monto dentro de un texto libre. Se acepta UN espacio interno porque los PDFs
# parten tokens ("2 58.198,55"), pero los lookarounds impiden capturar fragmentos
# de fecha: en "05/08/2026" ningún grupo puede empezar ni terminar pegado a "/".
_MONTO_RE = re.compile(
    r"(?<![\d/])"              # no arrancar pegado a dígito ni a una barra de fecha
    r"(?:\$\s*)?"              # símbolo de moneda opcional
    r"-?\s*"                   # signo
    r"\d[\d.]*(?:\s\d[\d.]*)?" # dígitos, con a lo sumo un corte de token
    r"(?:,\d+)?"               # decimales
    r"(?![\d/])"               # no terminar pegado a dígito ni a barra
)

_MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}


def parse_monto_ar(token: str) -> float:
    """
    Convierte un monto argentino a float.

    Espera UN solo monto. No pasarle una línea con varios montos: los espacios
    internos se colapsan (para reparar tokens partidos por el PDF) y dos montos
    contiguos se fusionarían. Para eso está montos_en_texto().
    """
    if token is None:
        raise MontoInvalido("token vacío")

    s = str(token).strip()

    # El signo puede ir antes o después del símbolo de moneda ("-$1,00", "$-1,00"),
    # así que se busca en todo lo que precede al primer dígito.
    primer_digito = re.search(r"\d", s)
    negativo = "-" in (s[: primer_digito.start()] if primer_digito else s)

    # Descartar símbolos de moneda y cualquier cosa que no sea dígito/separador.
    s = re.sub(r"[^\d.,]", "", s)
    if not s or not any(c.isdigit() for c in s):
        raise MontoInvalido(f"sin dígitos: {token!r}")

    if "," in s:
        # Coma presente → es el decimal. Los puntos son miles.
        entero, _, dec = s.rpartition(",")
        entero = entero.replace(".", "") or "0"
        dec = dec or "0"
        valor = float(f"{entero}.{dec}")
    elif "." in s:
        grupos = s.split(".")
        ultimo = grupos[-1]
        if len(ultimo) > 3:
            # Un grupo de miles nunca tiene más de 3 dígitos → se perdió la coma
            # decimal (caso Mercado Pago). Los 2 últimos dígitos son centavos.
            crudo = "".join(grupos)
            valor = float(f"{crudo[:-2]}.{crudo[-2:]}")
        else:
            # Separadores de miles legítimos.
            valor = float("".join(grupos))
    else:
        valor = float(s)

    return -valor if negativo else valor


def montos_en_texto(texto: str) -> list[float]:
    """Devuelve todos los montos de un texto, en orden de aparición."""
    salida = []
    for m in _MONTO_RE.finditer(texto):
        try:
            salida.append(parse_monto_ar(m.group()))
        except MontoInvalido:
            continue
    return salida


def parse_fecha_ar(token: str) -> date:
    """
    Convierte una fecha argentina a date.
    Acepta "13/08/2026" y "13/ago/2026" (Mercado Pago abrevia el mes).
    """
    s = str(token).strip().lower()
    m = re.search(r"(\d{1,2})\s*[/\-]\s*([a-záéíóú]{3,}|\d{1,2})\s*[/\-]\s*(\d{2,4})", s)
    if not m:
        raise MontoInvalido(f"fecha no reconocida: {token!r}")

    dia, mes_raw, anio = m.groups()

    if mes_raw.isdigit():
        mes = int(mes_raw)
    else:
        mes = _MESES.get(mes_raw[:3])
        if mes is None:
            raise MontoInvalido(f"mes no reconocido: {mes_raw!r}")

    anio = int(anio)
    if anio < 100:
        anio += 2000

    return date(anio, mes, int(dia))


def formatear_monto_ar(valor: float) -> str:
    """
    Formatea para mostrar en Argentina: 13405.84 → '13.405,84'.
    Python formatea al revés ('{:,.2f}' da '13,405.84'), así que se invierten
    los separadores.
    """
    return f"{valor:,.2f}".translate(str.maketrans({",": ".", ".": ","}))
