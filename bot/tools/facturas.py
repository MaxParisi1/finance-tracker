"""
Parseo determinístico de mails de "factura disponible" de servicios fijos.

Un parser por remitente, elegido por el dominio del From. Sin LLM: estos mails
llegan con formato idéntico todos los meses, así que un regex anclado en labels
es más confiable que un modelo (falla ruidosamente en vez de inventar un número).

Si un parser no reconoce el formato NO hay fallback a IA: se levanta
FacturaNoParseable, el mail queda sin leer y se avisa por Telegram. Un formato
nuevo debe ser una señal para escribir un parser, no un costo invisible.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date

from bot.tools.montos import parse_monto_ar, parse_fecha_ar, MontoInvalido

logger = logging.getLogger(__name__)

__all__ = [
    "FacturaParseada", "FacturaNoParseable", "FacturaIncompleta",
    "FacturaIrrelevante", "SERVICIOS",
    "parsear_email", "servicio_de_remitente",
]


class FacturaNoParseable(Exception):
    """El mail vino de un remitente conocido pero no se pudo extraer la factura."""


class FacturaIrrelevante(Exception):
    """
    El mail vino de un remitente conocido pero NO es un aviso de factura.

    Los proveedores mandan promociones desde la misma casilla: Personal usa
    facturacion@email.personal.com.ar tanto para la factura como para "Ahorrá
    hasta $6.000 con débito automático". Sin esta distinción, cada promo
    generaría una falsa alarma, y las falsas alarmas hacen que dejes de leer
    las verdaderas.
    """


class FacturaIncompleta(Exception):
    """
    El mail identifica la factura pero los datos están en un PDF enlazado.
    Lleva las URLs para que el caller las descargue y complete el parseo.
    """

    def __init__(self, pdf_urls: tuple[str, ...]):
        super().__init__(f"datos en PDF ({len(pdf_urls)} archivos)")
        self.pdf_urls = pdf_urls


@dataclass(frozen=True)
class FacturaParseada:
    servicio: str                  # slug estable, nunca el nombre visible
    identificador: str             # cuenta/cliente/referente — la clave de matching
    monto: float
    vencimiento: date
    periodo_desde: date | None = None
    periodo_hasta: date | None = None
    nro_factura: str | None = None
    pdf_urls: tuple[str, ...] = ()


# ──────────────────────────────────────────────
# Registry: dominio del remitente → slug de servicio
# El nombre visible del recurrente ("Consorcio Gallo", "Metrogas") vive en la DB;
# acá solo se usan slugs e identificadores.
# ──────────────────────────────────────────────

SERVICIOS: dict[str, str] = {
    "edenor.com": "edenor",
    "metrogas.com.ar": "metrogas",
    "aysadigital.com.ar": "aysa",
    "email.personal.com.ar": "personal",
    "simplesolutions.com.ar": "consorcio_gallo",
}


def servicio_de_remitente(*remitentes: str) -> str | None:
    """
    Devuelve el slug del servicio a partir de una o más cabeceras de remitente.

    Se aceptan varias porque los mails pueden llegar reenviados desde otra
    casilla: el reenvío automático de Gmail preserva el From: original, pero
    otros esquemas dejan el emisor real en Reply-To o X-Forwarded-For.
    """
    for remitente in remitentes:
        for m in re.finditer(r"@([\w.\-]+)", remitente or ""):
            dominio = m.group(1).lower().rstrip(">").rstrip(".")
            for sufijo, slug in SERVICIOS.items():
                if dominio == sufijo or dominio.endswith("." + sufijo):
                    return slug
    return None


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _norm_id(valor: str) -> str:
    """
    Normaliza un identificador para comparación.
    Edenor lo escribe espaciado ('5 255 064 586'), AySA con ceros a la izquierda
    en el mail ('000001929557') y sin ellos en el PDF ('1929557').
    """
    limpio = re.sub(r"[^\dA-Za-z]", "", valor or "")
    solo_digitos = limpio.isdigit()
    return limpio.lstrip("0") if solo_digitos else limpio.upper()


def _buscar(patron: str, texto: str, campo: str) -> re.Match:
    m = re.search(patron, texto, re.IGNORECASE)
    if not m:
        raise FacturaNoParseable(f"no encontré {campo}")
    return m


def _monto(raw: str, campo: str = "monto") -> float:
    try:
        return parse_monto_ar(raw)
    except MontoInvalido as e:
        raise FacturaNoParseable(f"{campo} ilegible: {raw!r}") from e


def _fecha(raw: str, campo: str = "vencimiento") -> date:
    try:
        return parse_fecha_ar(raw)
    except MontoInvalido as e:
        raise FacturaNoParseable(f"{campo} ilegible: {raw!r}") from e


# Monto seguido de fecha: el layout de tabla que usan MetroGAS y AySA, donde el
# importe y el vencimiento son celdas contiguas.
_MONTO_LUEGO_FECHA = r"\$\s*([\d.,]+)\s*\n\s*(\d{2}/\d{2}/\d{4})"


# ──────────────────────────────────────────────
# Parsers por servicio
# ──────────────────────────────────────────────

def _parse_edenor(email: dict) -> FacturaParseada:
    t = email["texto"]
    cuenta = _buscar(r"N[úu]mero de cuenta\s*\n\s*([\d\s]{6,20})", t, "número de cuenta")
    # Ojo: Edenor lista 1er y 2do vencimiento (el 2do con recargo). Va el primero.
    monto = _buscar(r"TOTAL A PAGAR\s*\n?\s*\$\s*([\d.,]+)", t, "total a pagar")
    vto = _buscar(r"VENCIMIENTO\s*\n\s*(\d{2}/\d{2}/\d{4})", t, "vencimiento")
    return FacturaParseada(
        servicio="edenor",
        identificador=_norm_id(cuenta.group(1)),
        monto=_monto(monto.group(1)),
        vencimiento=_fecha(vto.group(1)),
    )


def _parse_metrogas(email: dict) -> FacturaParseada:
    t = email["texto"]
    cliente = _buscar(r"N[úu]mero de cliente:\s*(\d+)", t, "número de cliente")
    par = _buscar(_MONTO_LUEGO_FECHA, t, "importe y vencimiento")

    desde = hasta = None
    periodo = re.search(
        r"Per[íi]odo de liquidaci[óo]n:\s*(\d{2}/\d{2}/\d{4})\s*A\s*(\d{2}/\d{2}/\d{4})", t, re.I
    )
    if periodo:
        desde, hasta = _fecha(periodo.group(1), "período desde"), _fecha(periodo.group(2), "período hasta")

    return FacturaParseada(
        servicio="metrogas",
        identificador=_norm_id(cliente.group(1)),
        monto=_monto(par.group(1)),
        vencimiento=_fecha(par.group(2)),
        periodo_desde=desde,
        periodo_hasta=hasta,
    )


def _parse_aysa(email: dict) -> FacturaParseada:
    t = email["texto"]
    # AySA arma una tabla con TODOS los encabezados primero y después los valores,
    # así que la cuenta y el N° de factura son las dos primeras celdas tras el
    # último encabezado ("Vencimiento").
    valores = _buscar(
        r"Vencimiento\s*\n\s*(\d{6,14})\s*\n\s*(\S+)", t, "cuenta y número de factura"
    )
    par = _buscar(_MONTO_LUEGO_FECHA, t, "importe y vencimiento")
    return FacturaParseada(
        servicio="aysa",
        identificador=_norm_id(valores.group(1)),
        monto=_monto(par.group(1)),
        vencimiento=_fecha(par.group(2)),
        nro_factura=valores.group(2).strip(),
    )


def _parse_personal(email: dict) -> FacturaParseada:
    # Personal pone monto y vencimiento en el asunto: es la fuente más estable,
    # inmune a cualquier rediseño del cuerpo del mail.
    asunto = email.get("subject", "")
    m = _buscar(
        r"saldo total es\s*\$?\s*([\d.,]+)\s*y vence el\s*(\d{2}/\d{2}/\d{4})",
        asunto, "saldo y vencimiento en el asunto",
    )
    ref = _buscar(r"Referente de pago\s*\n\s*(\d{10,20})", email["texto"], "referente de pago")
    return FacturaParseada(
        servicio="personal",
        identificador=_norm_id(ref.group(1)),
        monto=_monto(m.group(1)),
        vencimiento=_fecha(m.group(2)),
    )


def _parse_consorcio_gallo(email: dict) -> FacturaParseada:
    """
    Expensas: el mail no trae monto ni vencimiento, solo links a los PDFs en S3
    (públicos, sin auth). Este parser devuelve la factura *incompleta* con las
    URLs; el monto sale de expensas_pdf.parsear_unidades().
    """
    # Solo href: el mismo bucket sirve también el logo del mail vía <img src>.
    urls = tuple(dict.fromkeys(
        re.findall(
            r"href=[\"'](https://simplesolutionscloud\.s3\.[\w.\-]+/[\w/\-]+)",
            email.get("html", ""),
            re.IGNORECASE,
        )
    ))
    if not urls:
        raise FacturaNoParseable("no encontré los links a los PDFs de expensas")
    raise FacturaIncompleta(urls)


# Marcadores que identifican un aviso de factura frente al resto de lo que manda
# el mismo remitente (promos, encuestas, avisos de corte).
#
# Criterio deliberadamente PERMISIVO: alcanza con que aparezca uno. Un falso
# positivo cuesta una alerta molesta; un falso negativo descarta una factura
# real en silencio, que es el error caro. Ante la duda, se procesa.
_MARCADORES: dict[str, tuple[str, ...]] = {
    "edenor":          ("total a pagar", "totalapagar", "número de cuenta"),
    "metrogas":        ("número de cliente", "numero de cliente", "período de liquidación"),
    "aysa":            ("factura n", "importe", "cuenta:"),
    "personal":        ("saldo total es", "referente de pago"),
    "consorcio_gallo": ("simplesolutionscloud.s3", "expensa"),
}


def _es_aviso_de_factura(slug: str, email: dict) -> bool:
    """True si el mail parece un aviso de factura y no otra cosa del mismo emisor."""
    marcadores = _MARCADORES.get(slug)
    if not marcadores:
        return True  # servicio sin marcadores definidos: no filtramos nada

    heno = " ".join((
        email.get("subject", ""), email.get("texto", ""), email.get("html", ""),
    )).lower()
    return any(m in heno for m in marcadores)


_PARSERS = {
    "edenor": _parse_edenor,
    "metrogas": _parse_metrogas,
    "aysa": _parse_aysa,
    "personal": _parse_personal,
    "consorcio_gallo": _parse_consorcio_gallo,
}


def parsear_email(email: dict, slug: str | None = None) -> FacturaParseada:
    """
    Parsea un mail de factura.

    `email` necesita: from, subject, texto (cuerpo ya convertido a texto plano) y
    opcionalmente html (para extraer links) y remitentes_alternativos.

    `slug` fuerza un parser concreto: lo usa el poller cuando el remitente no se
    reconoce (mail reenviado) pero sí encontró el número de cuenta en el cuerpo.

    Levanta FacturaNoParseable si el remitente es desconocido o el formato cambió,
    y FacturaIncompleta si los datos están en un PDF enlazado.
    """
    if slug is None:
        slug = servicio_de_remitente(
            email.get("from", ""), *email.get("remitentes_alternativos", [])
        )
    if slug is None:
        raise FacturaNoParseable(f"remitente no registrado: {email.get('from')!r}")
    if slug not in _PARSERS:
        raise FacturaNoParseable(f"no hay parser para el servicio {slug!r}")

    if not _es_aviso_de_factura(slug, email):
        raise FacturaIrrelevante(
            f"mail de {slug} sin marcadores de factura (asunto: {email.get('subject', '')[:60]!r})"
        )

    factura = _PARSERS[slug](email)
    logger.info(
        "Factura parseada: %s · %s · $%s · vence %s",
        factura.servicio, factura.identificador, factura.monto, factura.vencimiento,
    )
    return factura
