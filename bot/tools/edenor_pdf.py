"""
Descarga del PDF de la factura de Edenor.

El aviso trae un botón "Ver factura" que es una imagen: no dice nada que sirva
para elegirlo. Pero el link de tracking de Edenor lleva el destino real adentro,
en base64 —{"linkUrl": "https://edenordigital.com/descarga_de_factura?token=…"}—
así que el criterio no es lo que dice el link sino A DÓNDE VA: se decodifica y
se toma solo lo que apunte a la página de descarga (ver
`facturas._urls_factura_edenor`). De paso, no hace falta pasar por el tracker.

Esa página no es el PDF: es la Oficina Virtual, una SPA que hace Widergy y que
dibuja la factura con pdf.js. El archivo sale de la misma API pública que usa
ella, sin login:

    GET https://utilitygo.widergy.com/api/v1/bills/public_pdf?token=<JWT>
        Utility-ID: 19        ← el tenant de Edenor; sin esta cabecera devuelve 400

El token es un JWT firmado por ellos, pero su payload se lee sin la clave y trae
{"cuenta_id": …, "factura_id": …}. Eso permite algo que los otros servicios no
dan: chequear que la cuenta del token sea la del mail ANTES de pedir nada.

Dos avisos para el día que se rompa:

- Le pegamos a la API interna de un proveedor tercero con un tenant hardcodeado.
  Si Widergy la cambia, esto falla; existe una /api/v2/bills/public_pdf que hace
  lo mismo pero asincrónica (devuelve un job para pollear), y es el fallback
  natural.
- La verificación del PDF NO puede apoyarse en la cuenta: es la misma todos los
  meses, así que confirma que la factura sea tuya pero no que sea la de ESTE
  mes. Lo único que distingue un mes de otro es el importe, y por eso el chequeo
  del total es obligatorio acá aunque en AySA se pueda degradar.
"""

import base64
import binascii
import io
import json
import logging
import re
from urllib.parse import parse_qs, quote, urlparse

from bot.tools.montos import MontoInvalido, formatear_monto_ar, parse_monto_ar

logger = logging.getLogger(__name__)

__all__ = [
    "EdenorPdfNoDisponible", "CABECERAS", "HOST_DESCARGA", "RUTA_DESCARGA",
    "es_url_de_descarga", "token_de_url", "cuenta_del_token", "verificar_cuenta",
    "url_del_pdf", "texto_primera_pagina", "totales_a_pagar", "verificar_factura",
]

# La página de descarga de la Oficina Virtual. El link del mail tiene que
# terminar acá: cualquier otro destino del tracking (el portal, las redes, los
# términos y condiciones) no es una factura.
HOST_DESCARGA = "edenordigital.com"
RUTA_DESCARGA = "/descarga_de_factura"

API_PDF = "https://utilitygo.widergy.com/api/v1/bills/public_pdf"

# Utility-ID es el tenant en la plataforma de Widergy (REACT_APP_UTILITY_ID en
# el bundle de la Oficina Virtual). Sin esta cabecera la API responde 400.
CABECERAS = {"Utility-ID": "19", "Accept": "application/pdf"}

TOLERANCIA_MONTO = 0.01

# El campo autoritativo de la portada. pdfplumber la devuelve sin espacios entre
# palabras ("TOTALAPAGAR $ 14.574,69"), así que los separadores son opcionales.
#
# El (?!RECARGO) es la misma precaución que en AySA: la portada trae también el
# importe del 2° vencimiento, que es el mismo número con recargo.
_RE_TOTAL = re.compile(
    r"TOTAL\s*A\s*PAGAR((?:(?!RECARGO)[^$\n]){0,40})\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
    re.IGNORECASE,
)


class EdenorPdfNoDisponible(Exception):
    """No se pudo obtener el PDF de la factura, o el que llegó no es el esperado."""


def es_url_de_descarga(url: str) -> bool:
    """True si la URL es la página de descarga de factura de la Oficina Virtual."""
    partes = urlparse(url or "")
    host = partes.netloc.lower().split(":")[0]
    if partes.scheme.lower() != "https":
        return False
    if not (host == HOST_DESCARGA or host.endswith("." + HOST_DESCARGA)):
        return False
    return partes.path.rstrip("/").lower() == RUTA_DESCARGA


def token_de_url(url: str) -> str:
    """
    El token de la factura, revalidando el destino.

    Se vuelve a chequear acá —ya lo hizo el parser al elegir el link— porque
    esta función es la que arma el pedido a la API: no puede confiar en que
    quien la llame haya validado la URL.
    """
    if not es_url_de_descarga(url):
        raise EdenorPdfNoDisponible(
            f"el link no es la descarga de factura de {HOST_DESCARGA}: {url[:80]!r}"
        )
    token = parse_qs(urlparse(url).query).get("token", [""])[0]
    if not token:
        raise EdenorPdfNoDisponible("el link de descarga no trae token")
    return token


def _normalizar_cuenta(valor: str) -> str:
    """Edenor escribe la cuenta espaciada en el PDF ('5 255 064 586')."""
    return re.sub(r"[^\d]", "", valor or "").lstrip("0")


def cuenta_del_token(token: str) -> str | None:
    """
    El número de cuenta que declara el JWT, o None si no se puede leer.

    Solo se decodifica el payload: la firma es de Edenor y no tenemos con qué
    validarla, así que esto no es una prueba de nada por sí solo — sirve para
    detectar que estamos por pedir la factura de otra cuenta, no para confiar.
    """
    partes = (token or "").split(".")
    if len(partes) < 2:
        return None
    crudo = partes[1]
    try:
        datos = json.loads(base64.urlsafe_b64decode(crudo + "=" * (-len(crudo) % 4)))
    except (ValueError, binascii.Error):
        return None
    cuenta = datos.get("cuenta_id") if isinstance(datos, dict) else None
    return str(cuenta) if cuenta is not None else None


def verificar_cuenta(token: str, identificador: str) -> None:
    """
    Corta antes de descargar si el token es de otra cuenta.

    Que el token no se pueda leer no bloquea: el formato es de ellos y puede
    cambiar. La verificación que manda es la del PDF; esta solo evita el pedido
    inútil y deja el warning para ir a mirar.
    """
    cuenta = cuenta_del_token(token)
    if cuenta is None:
        logger.warning("No pude leer la cuenta del token de Edenor; sigo con la descarga")
        return
    if _normalizar_cuenta(cuenta) != _normalizar_cuenta(identificador):
        raise EdenorPdfNoDisponible(
            f"el token es de la cuenta {cuenta} y el mail de la {identificador}"
        )


def url_del_pdf(token: str) -> str:
    """La URL de la API que devuelve el PDF. Va con CABECERAS o responde 400."""
    return f"{API_PDF}?token={quote(token, safe='')}"


def texto_primera_pagina(pdf_bytes: bytes) -> str:
    """
    El texto de la portada, que es donde Edenor pone la cuenta y el total.
    Se importa pdfplumber acá adentro para no pagarlo en el arranque del bot.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if not pdf.pages:
            return ""
        return pdf.pages[0].extract_text() or ""


def totales_a_pagar(texto: str) -> set[float]:
    """Los importes etiquetados "Total a pagar", sin el del 2° vencimiento."""
    valores = set()
    for m in _RE_TOTAL.finditer(texto or ""):
        try:
            valores.add(parse_monto_ar(m.group(2)))
        except MontoInvalido:
            continue
    return valores


def _cuenta_en(texto: str, cuenta: str) -> bool:
    """La cuenta aparece espaciada ('5 255 064 586') y junta según el renglón."""
    return _normalizar_cuenta(cuenta) in _normalizar_cuenta(texto)


def _coincide(valor: float, esperado: float) -> bool:
    """
    Compara importes a nivel centavo. El redondeo es necesario: restar dos floats
    que difieren en un centavo da 0.010000000000218, que sin esto quedaría afuera
    de la tolerancia por ruido binario y no por el dato.
    """
    return abs(round(valor - esperado, 2)) <= TOLERANCIA_MONTO


def verificar_factura(pdf_bytes: bytes, cuenta: str | None, monto: float) -> None:
    """
    Confirma que el PDF descargado sea el de ESTA factura y no el de otro mes.

    El importe es obligatorio y la cuenta es el extra, al revés que en AySA: la
    cuenta es la misma todos los meses, así que descarta la factura de otro
    cliente pero daría por buena la del mes pasado. Si la etiqueta del total no
    está —Edenor rediseñó la portada— se degrada a que el importe figure en
    algún lado, pero figurar tiene que figurar.
    """
    from bot.tools.montos import montos_en_texto

    texto = texto_primera_pagina(pdf_bytes)
    if not texto.strip():
        raise EdenorPdfNoDisponible(
            "no pude leer texto en la primera página del PDF "
            "— puede ser un escaneado o una página de error"
        )

    if cuenta and not _cuenta_en(texto, cuenta):
        raise EdenorPdfNoDisponible(
            f"el PDF no menciona la cuenta {cuenta} — es de otro cliente"
        )

    totales = totales_a_pagar(texto)
    if totales:
        if not any(_coincide(t, monto) for t in totales):
            raise EdenorPdfNoDisponible(
                f"el PDF dice total a pagar ${formatear_monto_ar(min(totales))} y el "
                f"mail ${formatear_monto_ar(monto)} — es de otra factura"
            )
        logger.info("PDF de Edenor verificado por total a pagar y cuenta %s", cuenta)
        return

    if not any(_coincide(m, monto) for m in montos_en_texto(texto)):
        raise EdenorPdfNoDisponible(
            f"el PDF no menciona ${formatear_monto_ar(monto)} — es de otra factura"
        )
    logger.warning(
        "El PDF de Edenor no trae la etiqueta del total a pagar; el importe se "
        "validó de forma laxa. Probablemente cambió la portada."
    )
