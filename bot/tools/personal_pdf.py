"""
Descarga del PDF de la factura de Personal.

El mail trae un link con token que sirve el PDF sin login —Telecom lo etiqueta
así en su propio tracking: "factura sin login"— pero en dos saltos. La URL del
mail devuelve un HTML de ~4 KB que dice "Descargando..." y salta a la URL real
por JavaScript. No hace falta un navegador: alcanza con leer el location.replace().

AySA también se automatiza, con otro flujo (ver aysa_pdf.py). Edenor y MetroGAS
solo enlazan su portal con login, así que esos PDFs siguen entrando a mano por
Telegram.

Esto es scraping de un flujo que Telecom no documenta y puede cambiar sin aviso,
así que la regla es fallar ruidosamente: si el HTML intermedio no trae el salto,
si el salto apunta fuera del dominio de Personal, o si el PDF no habla del mismo
monto que el mail, no se archiva nada. Que falte un PDF lo reclama el
recordatorio de los lunes; un PDF equivocado colgado de la factura equivocada no
lo detecta nadie.
"""

import html as html_lib
import io
import logging
import re
from urllib.parse import urlparse

from bot.tools.montos import MontoInvalido, formatear_monto_ar, parse_monto_ar

logger = logging.getLogger(__name__)

__all__ = [
    "PersonalPdfNoDisponible", "HOST_PERSONAL",
    "extraer_url_pdf", "resolver_url_pdf",
    "texto_primera_pagina", "total_a_pagar", "importes", "verificar_monto",
]

# El salto tiene que quedarse dentro del dominio de Personal. Sin este chequeo,
# cualquiera que pudiera alterar el HTML intermedio nos haría descargar (y colgar
# de tu factura) un archivo de otro lado.
HOST_PERSONAL = "tufactura.personal.com.ar"

TIMEOUT_SEGUNDOS = 30

# El monto del PDF tiene que ser el mismo que el del mail. Son dos fuentes
# independientes de Telecom: si no coinciden, alguna de las dos se leyó mal.
TOLERANCIA_MONTO = 0.01

_RE_REDIRECT = re.compile(r"""location\.replace\(\s*["']([^"']+)["']\s*\)""", re.IGNORECASE)

# Montos con formato argentino: 72.711,49
_RE_MONTO = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")

# El campo autoritativo de la portada. pdfplumber la devuelve sin espacios entre
# palabras ("TOTALAPAGAR $72.711,49"), así que los separadores son opcionales.
_RE_TOTAL = re.compile(
    r"TOTAL\s*A\s*PAGAR[^\d\-]{0,12}(\d{1,3}(?:\.\d{3})*,\d{2})", re.IGNORECASE
)


class PersonalPdfNoDisponible(Exception):
    """No se pudo obtener el PDF de la factura, o el que llegó no es el esperado."""


def extraer_url_pdf(html: str) -> str:
    """
    Saca la URL del PDF del HTML intermedio, validando que siga en Personal.

    Función pura: se testea con el HTML guardado, sin tocar la red.
    """
    m = _RE_REDIRECT.search(html or "")
    if not m:
        raise PersonalPdfNoDisponible(
            "la página intermedia no trae el location.replace() al PDF "
            "— Personal probablemente cambió el flujo de descarga"
        )

    url = html_lib.unescape(m.group(1)).strip()
    host = urlparse(url).netloc.lower()
    if host != HOST_PERSONAL:
        raise PersonalPdfNoDisponible(
            f"el salto apunta a {host!r} y no a {HOST_PERSONAL}"
        )
    return url


def resolver_url_pdf(url: str) -> str:
    """Primer salto: pide la página intermedia y devuelve la URL real del PDF."""
    import requests

    resp = requests.get(url, timeout=TIMEOUT_SEGUNDOS)
    resp.raise_for_status()
    return extraer_url_pdf(resp.text)


def texto_primera_pagina(pdf_bytes: bytes) -> str:
    """
    El texto de la portada, que es donde Personal pone el resumen de importes.
    Se importa pdfplumber acá adentro para no pagarlo en el arranque del bot.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if not pdf.pages:
            return ""
        return pdf.pages[0].extract_text() or ""


def total_a_pagar(texto: str) -> float | None:
    """
    El importe del campo TOTAL A PAGAR, o None si la etiqueta no está.

    pdfplumber devuelve la portada sin espacios entre palabras ("TOTALAPAGAR
    $72.711,49"), de ahí los \\s* entre las tres palabras.
    """
    m = _RE_TOTAL.search(texto or "")
    if not m:
        return None
    try:
        return parse_monto_ar(m.group(1))
    except MontoInvalido:
        return None


def importes(texto: str) -> set[float]:
    """Todos los importes del texto, sin signo."""
    valores = set()
    for crudo in _RE_MONTO.findall(texto or ""):
        try:
            valores.add(parse_monto_ar(crudo))
        except MontoInvalido:
            continue
    return valores


def verificar_monto(pdf_bytes: bytes, esperado: float) -> None:
    """
    Confirma que el PDF descargado sea el de ESTA factura y no el de otro mes.

    Se compara contra TOTAL A PAGAR y no contra "algún importe de la página":
    la portada también lista el SaldoAnterior, que es el total del mes pasado,
    así que un chequeo laxo daría por bueno el PDF del mes equivocado.

    Si la etiqueta no aparece —Personal rediseñó la portada— se degrada al
    chequeo laxo en vez de bloquear el archivado: que el importe del mail figure
    en algún lado sigue descartando el error que importa, y queda el warning en
    el log para ir a mirar el nuevo formato.
    """
    texto = texto_primera_pagina(pdf_bytes)

    total = total_a_pagar(texto)
    if total is not None:
        if abs(total - esperado) > TOLERANCIA_MONTO:
            raise PersonalPdfNoDisponible(
                f"el PDF dice TOTAL A PAGAR ${formatear_monto_ar(total)} y el mail "
                f"${formatear_monto_ar(esperado)} — es de otra factura"
            )
        logger.info("PDF de Personal verificado contra TOTAL A PAGAR: $%s", total)
        return

    todos = importes(texto)
    if not todos:
        raise PersonalPdfNoDisponible(
            "no pude leer ningún importe de la primera página del PDF"
        )
    if not any(abs(m - esperado) <= TOLERANCIA_MONTO for m in todos):
        raise PersonalPdfNoDisponible(
            f"el PDF no menciona ${formatear_monto_ar(esperado)} — es de otra factura "
            f"(importes leídos: {sorted(todos)[-4:]})"
        )
    logger.warning(
        "El PDF de Personal no trae TOTAL A PAGAR; el monto se validó de forma laxa. "
        "Probablemente cambió la portada."
    )
