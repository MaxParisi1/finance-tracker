"""
Descarga del PDF de la factura de AySA.

El aviso de "Factura Digital Disponible" trae un botón "Descargar" que sirve el
PDF sin login, pero su URL es la del redirector de tracking del proveedor de
mailing: de ahí salta al backend de la Oficina Virtual, que devuelve el archivo.
El token de acceso viaja ofuscado dentro del link de tracking, así que no se
puede saltear el redirector como sí se hace con el segundo salto de Personal:
hay que caminar la cadena entera.

Lo que se protege acá, en orden de importancia:

1. No seguir el link equivocado. El mismo mail trae, con una URL indistinguible,
   el link de BAJA de la factura digital. Seguirlo nos daría de baja justo del
   aviso que este bot existe para leer, y no habría error: dejarían de llegar
   mails. Por eso el botón se elige por lo que DICE —texto o title— y todo link
   que hable de baja queda excluido explícitamente (ver `facturas._urls_factura_aysa`).

2. No traer un archivo de cualquier lado. Cada salto se valida contra los
   dominios de AySA y su proveedor de mailing ANTES de pedirlo, así que un
   redirector abierto en el tracking no alcanza para colgar de tu factura un PDF
   ajeno, ni para filtrarle el token a un tercero.

3. No colgar el PDF equivocado. La verificación es por contenido y con dos
   señales independientes: el N° de LSP del mail tiene que aparecer en el PDF y
   el "Total a pagar" tiene que ser el mismo importe. El PDF del mes anterior
   falla las dos.

Como en Personal, esto es scraping de un flujo que AySA no documenta: si algo de
lo anterior no se cumple no se archiva nada. Que falte un PDF lo reclama el
recordatorio de los lunes; un PDF equivocado colgado de la factura equivocada no
lo detecta nadie.
"""

import io
import logging
import re
from urllib.parse import urljoin, urlparse

from bot.tools.montos import MontoInvalido, formatear_monto_ar, parse_monto_ar

logger = logging.getLogger(__name__)

__all__ = [
    "AysaPdfNoDisponible", "DOMINIOS_PERMITIDOS",
    "resolver_url_pdf", "texto_primera_pagina", "totales_a_pagar",
    "verificar_factura",
]

# Dominios por los que puede pasar la descarga. Es una lista de sufijos, no de
# hosts exactos, a propósito: el backend de la Oficina Virtual vive en SAP BTP y
# el nombre del tenant ya cambia entre un salto y el otro
# (aysaovservicehub….br1 → aysa-ov-service-hub-cf-prd.cfapps.br10), así que
# pinearlo exacto sería romperse solo en el próximo redeploy de AySA.
# Esta lista no es la que garantiza que el PDF sea el correcto —de eso se ocupa
# verificar_factura()—, solo evita que un redirector abierto nos mande a pedirle
# el archivo (y a mostrarle el token) a un dominio cualquiera.
DOMINIOS_PERMITIDOS = (
    "aysa.com.ar",
    "aysadigital.com.ar",
    "hana.ondemand.com",   # backend de la Oficina Virtual (SAP BTP)
    "musvc.com",           # proveedor de mailing (MailUp)
    "musvc2.net",
)

TIMEOUT_SEGUNDOS = 30

# La cadena real son dos saltos. El tope deja margen para que AySA agregue uno
# más sin que haya que tocar esto, y corta un bucle de redirecciones.
MAX_SALTOS = 5

_REDIRECCIONES = (301, 302, 303, 307, 308)

# El importe del PDF tiene que ser el mismo que el del mail. Son dos fuentes
# independientes de AySA: si no coinciden, alguna de las dos se leyó mal.
TOLERANCIA_MONTO = 0.01

# El campo autoritativo de la portada. pdfplumber la devuelve sin espacios entre
# palabras ("Totalapagarhastael10/09/2026 $31.356,27"), así que los separadores
# son opcionales y se tolera texto entre la etiqueta y el número.
#
# El (?!RECARGO) es el punto fino: la misma portada trae "Total a pagar con
# recargo hasta el 25/09 $31.765,53", que es el importe del 2° vencimiento. Sin
# excluirlo, ese número entraría como si fuera el total de la factura.
_RE_TOTAL = re.compile(
    r"TOTAL\s*A\s*PAGAR((?:(?!RECARGO)[^$\n]){0,40})\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
    re.IGNORECASE,
)


class AysaPdfNoDisponible(Exception):
    """No se pudo obtener el PDF de la factura, o el que llegó no es el esperado."""


def _host_permitido(url: str) -> bool:
    host = urlparse(url).netloc.lower().split(":")[0]
    return any(host == d or host.endswith("." + d) for d in DOMINIOS_PERMITIDOS)


def _validar(url: str) -> str:
    """Chequea el salto ANTES de pedirlo: un host raro no llega a recibir el token."""
    if urlparse(url).scheme.lower() != "https":
        raise AysaPdfNoDisponible(f"el salto no es https: {url[:60]!r}")
    if not _host_permitido(url):
        raise AysaPdfNoDisponible(
            f"el salto apunta a {urlparse(url).netloc!r}, fuera de los dominios de AySA"
        )
    return url


def resolver_url_pdf(url: str) -> str:
    """
    Camina la cadena de redirecciones del link del mail y devuelve la URL final.

    Se sigue salto a salto (allow_redirects=False) en vez de dejar que requests
    los siga solo: así cada host se valida antes de pedirle nada. Se usa
    stream=True y se cierra la respuesta para no bajar el PDF dos veces — el
    cuerpo lo trae después descargar_pdf(), que es quien valida tipo y tamaño.
    """
    import requests

    actual = _validar(url)
    for _ in range(MAX_SALTOS):
        resp = requests.get(actual, timeout=TIMEOUT_SEGUNDOS,
                            allow_redirects=False, stream=True)
        try:
            es_salto = resp.status_code in _REDIRECCIONES
            destino = resp.headers.get("Location") if es_salto else None
            if destino is None:
                resp.raise_for_status()
                return actual
        finally:
            resp.close()
        actual = _validar(urljoin(actual, destino))

    raise AysaPdfNoDisponible(
        f"la descarga dio más de {MAX_SALTOS} saltos sin llegar al PDF"
    )


def texto_primera_pagina(pdf_bytes: bytes) -> str:
    """
    El texto de la portada, que es donde AySA pone la LSP y el total a pagar.
    Se importa pdfplumber acá adentro para no pagarlo en el arranque del bot.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if not pdf.pages:
            return ""
        return pdf.pages[0].extract_text() or ""


def _solo_alfanumerico(valor: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", valor or "").upper()


def totales_a_pagar(texto: str) -> set[float]:
    """
    Los importes etiquetados como "Total a pagar", sin el del 2° vencimiento.

    Son varios porque la portada repite el total ("Total a pagar $31.356,27" y
    "Total a pagar hasta el 10/09/2026 $31.356,27"); se devuelven todos y basta
    con que el monto del mail sea uno de ellos.
    """
    valores = set()
    for m in _RE_TOTAL.finditer(texto or ""):
        try:
            valores.add(parse_monto_ar(m.group(2)))
        except MontoInvalido:
            continue
    return valores


def _coincide(valor: float, esperado: float) -> bool:
    """
    Compara importes a nivel centavo. El redondeo es necesario: restar dos floats
    que difieren en un centavo da 0.010000000000218, que sin esto quedaría afuera
    de la tolerancia por ruido binario y no por el dato.
    """
    return abs(round(valor - esperado, 2)) <= TOLERANCIA_MONTO


def verificar_factura(pdf_bytes: bytes, nro_factura: str | None, monto: float) -> None:
    """
    Confirma que el PDF descargado sea el de ESTA factura y no el de otro mes.

    Dos señales independientes, y las dos son excluyentes cuando se pueden leer:
    si el N° de LSP no está, o si el total no coincide, no se archiva. Que falte
    una —AySA rediseñó la portada— se degrada a verificar con la otra y queda el
    warning en el log; que falten las dos es un error: archivar a ciegas un PDF
    que no se pudo leer es exactamente el fallo silencioso que hay que evitar.
    """
    from bot.tools.montos import montos_en_texto

    texto = texto_primera_pagina(pdf_bytes)
    if not texto.strip():
        raise AysaPdfNoDisponible(
            "no pude leer texto en la primera página del PDF "
            "— puede ser un escaneado o una página de error"
        )

    verificado = []

    if nro_factura and _solo_alfanumerico(nro_factura) in _solo_alfanumerico(texto):
        verificado.append(f"LSP {nro_factura}")
    elif nro_factura:
        raise AysaPdfNoDisponible(
            f"el PDF no menciona la LSP {nro_factura} del mail — es de otra factura"
        )

    totales = totales_a_pagar(texto)
    if totales:
        if any(_coincide(t, monto) for t in totales):
            verificado.append(f"total a pagar ${formatear_monto_ar(monto)}")
        elif verificado:
            # El PDF es el de esta LSP pero el importe no es el que se registró:
            # lo que está mal es el dato del mail, no el archivo.
            raise AysaPdfNoDisponible(
                f"el PDF de la {verificado[0]} dice "
                f"${formatear_monto_ar(min(totales))} y el mail "
                f"${formatear_monto_ar(monto)} — revisá el importe registrado"
            )
        else:
            raise AysaPdfNoDisponible(
                f"el PDF dice total a pagar ${formatear_monto_ar(min(totales))} y el "
                f"mail ${formatear_monto_ar(monto)} — es de otra factura"
            )
    elif not verificado:
        # Sin LSP y sin la etiqueta del total: última red, que el importe figure
        # en algún lado de la portada.
        if not any(_coincide(m, monto) for m in montos_en_texto(texto)):
            raise AysaPdfNoDisponible(
                f"no pude verificar el PDF: no menciona ni la factura {nro_factura} "
                f"ni ${formatear_monto_ar(monto)}"
            )
        verificado.append(f"${formatear_monto_ar(monto)} en la portada")

    if len(verificado) < 2:
        logger.warning(
            "El PDF de AySA se verificó con una sola señal (%s). "
            "Probablemente cambió la portada: conviene mirar el formato nuevo.",
            verificado[0],
        )
    logger.info("PDF de AySA verificado por %s", " y ".join(verificado))
