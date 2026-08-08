"""
Poller de la etiqueta "Facturas": convierte avisos de factura en filas de la
tabla `facturas`, sin intervención y sin LLM.

Contrato de fallos, deliberado: un mail solo se marca como leído cuando quedó
resuelto (registrado o duplicado conocido). Cualquier otra cosa lo deja sin leer
y manda un aviso por Telegram, así el próximo ciclo lo reintenta y nunca se
pierde una factura en silencio.
"""

import asyncio
import html as html_lib
import logging
import re

from bot.db import queries
from bot.tools.alertas import alertar_error, escapar_md
from bot.tools.expensas_pdf import ExpensasNoParseable, parsear_pdf_unidades
from bot.tools.facturas import (
    FacturaIncompleta, FacturaIrrelevante, FacturaNoParseable, FacturaParseada,
    parsear_email,
)
from bot.tools.facturas_service import (
    FacturaSospechosa, ServicioDesconocido, registrar_factura,
)
from bot.tools.gmail_reader import get_unread_bank_emails, mark_as_read
from bot.tools.montos import formatear_monto_ar

logger = logging.getLogger(__name__)

LABEL_NAME_FACTURAS = "Facturas"

# Tope de descarga de un PDF de factura. Los reales pesan entre 50 KB y 1 MB;
# más que esto significa que la URL apunta a otra cosa.
MAX_PDF_BYTES = 15 * 1024 * 1024
TIMEOUT_DESCARGA = 60


def _a_texto(html: str) -> str:
    """Convierte HTML a texto conservando los saltos de línea entre celdas."""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    html = re.sub(r"</?(tr|td|br|p|div|table|span|li|h\d)[^>]*>", "\n", html, flags=re.I)
    texto = html_lib.unescape(re.sub(r"<[^>]+>", " ", html))
    texto = re.sub(r"[ \t\xa0]+", " ", texto)
    return re.sub(r"\n\s*\n+", "\n", texto).strip()


def _como_email_parseable(email: dict) -> dict:
    """Adapta el dict de gmail_reader al que esperan los parsers."""
    html = email.get("html") or ""
    return {
        "from": email.get("from", ""),
        "subject": email.get("subject", ""),
        "html": html,
        "texto": _a_texto(html) if html else email.get("body", ""),
        "remitentes_alternativos": email.get("remitentes_alternativos", []),
    }


def _slug_por_identificador(texto: str) -> str | None:
    """
    Último recurso cuando el remitente no se reconoce: buscar el número de
    cuenta dentro del cuerpo del mail.

    Esto hace que el circuito sobreviva a un reenvío desde otra casilla, donde
    el From: puede quedar reescrito. El número de cuenta, en cambio, viaja
    siempre dentro del mensaje.
    """
    from bot.tools.documentos import identificar_servicio

    try:
        ident = identificar_servicio(texto, queries.listar_identificadores_servicios())
    except Exception as exc:
        logger.info("Fallback por identificador no resolvió: %s", exc)
        return None
    return ident["servicio"]["slug"]


def parsear_con_fallback(email_parseable: dict):
    """
    Parsea por remitente y, si no se reconoce, reintenta identificando el
    servicio por el número de cuenta que aparece en el cuerpo.
    """
    try:
        return parsear_email(email_parseable)
    except FacturaNoParseable as exc:
        if "remitente no registrado" not in str(exc):
            raise
        slug = _slug_por_identificador(email_parseable.get("texto", ""))
        if slug is None:
            raise
        logger.info("Remitente desconocido; ruteado por identificador → %s", slug)
        return parsear_email(email_parseable, slug=slug)


def descargar_pdf(url: str) -> bytes:
    """
    Descarga un PDF verificando tipo y tamaño. Se importa requests acá adentro
    para no pagarlo en el arranque del bot.
    """
    import requests

    resp = requests.get(url, timeout=TIMEOUT_DESCARGA, stream=True)
    resp.raise_for_status()

    tipo = resp.headers.get("Content-Type", "")
    if "pdf" not in tipo.lower():
        raise ExpensasNoParseable(f"{url[-24:]} no es un PDF (Content-Type: {tipo!r})")

    datos = resp.content
    if len(datos) > MAX_PDF_BYTES:
        raise ExpensasNoParseable(f"PDF de {len(datos)} bytes, supera el tope")
    if not datos.startswith(b"%PDF"):
        raise ExpensasNoParseable("el archivo descargado no tiene cabecera PDF")

    return datos


def resolver_expensas(urls: tuple[str, ...]) -> FacturaParseada:
    """
    El mail de expensas enlaza dos PDFs (gastos del consorcio y liquidación por
    unidad) sin decir cuál es cuál. Se prueban por CONTENIDO: el bueno es el que
    contiene la fila de la unidad funcional. Así el orden de los adjuntos o un
    cambio de nombre de archivo no rompen nada.
    """
    servicio = queries.obtener_servicio_por_slug("consorcio_gallo")
    if servicio is None:
        raise ServicioDesconocido("el servicio 'consorcio_gallo' no está registrado")

    unidad = servicio.get("unidad_funcional")
    if not unidad:
        raise ExpensasNoParseable(
            "el servicio 'consorcio_gallo' no tiene unidad_funcional configurada"
        )

    errores = []
    for url in urls:
        try:
            fila = parsear_pdf_unidades(descargar_pdf(url), unidad)
        except Exception as exc:
            errores.append(f"{url[-16:]}: {exc}")
            continue

        if fila.vencimiento is None:
            errores.append(f"{url[-16:]}: encontré la unidad pero no el vencimiento")
            continue

        return FacturaParseada(
            servicio="consorcio_gallo",
            identificador="",  # el mail no trae número: se rutea por slug
            monto=fila.total,
            vencimiento=fila.vencimiento,
        )

    raise ExpensasNoParseable(
        f"ninguno de los {len(urls)} PDFs tenía la unidad {unidad}: {'; '.join(errores)}"
    )


def _resumen(factura: FacturaParseada, nombre: str) -> str:
    return (
        f"\U0001f9fe *Factura registrada*\n"
        f"• *{escapar_md(nombre)}*\n"
        f"• ${formatear_monto_ar(factura.monto)}\n"
        f"• Vence: {factura.vencimiento}"
    )


async def procesar_email_factura(bot, chat_id: int, email: dict) -> bool:
    """
    Procesa un mail. Devuelve True si quedó resuelto (y se marcó leído).

    Cada rama de error avisa con el detalle exacto de qué se rompió y deja el
    mail sin leer para reintentar.
    """
    eid = email["id"]
    contexto = {"Asunto": email.get("subject"), "De": email.get("from")}

    try:
        parseada = await asyncio.to_thread(parsear_con_fallback, _como_email_parseable(email))

    except FacturaIncompleta as incompleta:
        # Expensas: los datos están en un PDF enlazado.
        try:
            parseada = await asyncio.to_thread(resolver_expensas, incompleta.pdf_urls)
        except Exception as exc:
            await alertar_error(
                bot, chat_id, titulo="No pude leer el PDF de expensas",
                contexto=contexto, exc=exc, clave=f"expensas:{eid}",
            )
            return False

    except FacturaIrrelevante as exc:
        # Promo, encuesta o aviso de corte del mismo remitente. No es un error:
        # se marca leído y se sigue, sin molestar.
        logger.info("Mail descartado por no ser aviso de factura: %s", exc)
        await asyncio.to_thread(mark_as_read, eid)
        return True

    except FacturaNoParseable as exc:
        await alertar_error(
            bot, chat_id, titulo="Factura sin parsear",
            contexto=contexto, exc=exc, clave=f"parse:{eid}",
        )
        return False

    except Exception as exc:
        await alertar_error(
            bot, chat_id, titulo="Error inesperado parseando una factura",
            contexto=contexto, exc=exc, clave=f"parse-raro:{eid}",
        )
        return False

    try:
        resultado = await asyncio.to_thread(registrar_factura, parseada, eid)
    except (ServicioDesconocido, FacturaSospechosa) as exc:
        await alertar_error(
            bot, chat_id, titulo="Factura no registrada",
            contexto={**contexto, "Servicio": parseada.servicio,
                      "Monto leído": f"${formatear_monto_ar(parseada.monto)}",
                      "Vencimiento leído": parseada.vencimiento},
            exc=exc, clave=f"registro:{eid}",
        )
        return False
    except Exception as exc:
        await alertar_error(
            bot, chat_id, titulo="Error guardando una factura",
            contexto={**contexto, "Servicio": parseada.servicio},
            exc=exc, clave=f"guardar:{eid}",
        )
        return False

    await asyncio.to_thread(mark_as_read, eid)

    if resultado.ya_existia:
        logger.info("Factura de %s ya estaba registrada; mail marcado leído", parseada.servicio)
        return True

    servicio = resultado.factura.get("servicios") or {}
    nombre = servicio.get("nombre") or parseada.servicio
    try:
        await bot.send_message(chat_id=chat_id, text=_resumen(parseada, nombre),
                               parse_mode="Markdown")
    except Exception:
        # La factura ya está guardada: no avisar es molesto, no grave.
        logger.exception("No pude notificar la factura registrada")

    return True


async def poll_facturas_once(bot, chat_id: int) -> bool:
    """
    Un ciclo sobre la etiqueta Facturas.
    Devuelve False solo si falló el fetch a Gmail (señal de salud del poller).
    """
    try:
        emails = await asyncio.to_thread(get_unread_bank_emails, LABEL_NAME_FACTURAS)
    except Exception:
        logger.exception("Error al consultar Gmail (Facturas)")
        return False

    for email in emails:
        try:
            await procesar_email_factura(bot, chat_id, email)
        except Exception:
            # Un mail que rompe de forma imprevista no puede frenar a los demás.
            logger.exception("Error procesando el mail de factura %s", email.get("id"))

    return True
