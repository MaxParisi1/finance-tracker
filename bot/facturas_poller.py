"""
Poller de la etiqueta "Facturas": convierte avisos de factura en filas de la
tabla `facturas`, sin intervención y sin LLM.

Contrato de fallos, deliberado: un mail solo se marca como leído cuando quedó
resuelto (registrado o duplicado conocido). Cualquier otra cosa lo deja sin leer
y manda un aviso por Telegram, así el próximo ciclo lo reintenta y nunca se
pierde una factura en silencio.

Única excepción, también deliberada: si falla la descarga del PDF adjunto el
mail SÍ se marca leído. Para entonces el importe ya está guardado, que es el
dato caro; reintentar un flujo de descarga roto alertaría en cada ciclo para
siempre, y el repaso semanal de documentación ya reclama lo que falte archivar.
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
    plano = email.get("body", "")
    return {
        "from": email.get("from", ""),
        "subject": email.get("subject", ""),
        "html": html,
        "texto": _a_texto(html) if html else plano,
        # La parte text/plain sin tocar. No es lo mismo que `texto`: cuando hay
        # HTML, `texto` sale de convertirlo, y ahí se pierde todo lo que viva
        # solo en el text/plain — como el link de descarga de Personal.
        "plano": plano,
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


def descargar_pdf(url: str, headers: dict | None = None) -> bytes:
    """
    Descarga un PDF verificando tipo y tamaño. Se importa requests acá adentro
    para no pagarlo en el arranque del bot.

    `headers` lo usa Edenor, cuya API pide una cabecera de tenant para responder.
    """
    import requests

    resp = requests.get(url, timeout=TIMEOUT_DESCARGA, stream=True, headers=headers)
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

        # `pdf_urls` lleva SOLO la URL que resultó ser la liquidación de la
        # unidad, no las dos del mail: es la que después se archiva. Sin esto el
        # PDF de expensas se bajaba, se parseaba y se tiraba, y la factura del
        # consorcio quedaba para siempre sin documento en la grilla de Registro.
        return FacturaParseada(
            servicio="consorcio_gallo",
            identificador="",  # el mail no trae número: se rutea por slug
            monto=fila.total,
            vencimiento=fila.vencimiento,
            pdf_urls=(url,),
        )

    raise ExpensasNoParseable(
        f"ninguno de los {len(urls)} PDFs tenía la unidad {unidad}: {'; '.join(errores)}"
    )


def descargar_factura_personal(url: str, monto: float) -> bytes:
    """
    Los dos saltos de Personal más la verificación de que el PDF sea el de esta
    factura. Cualquier fallo sale como PersonalPdfNoDisponible para que el caller
    no tenga que distinguir en cuál de los pasos se rompió.
    """
    from bot.tools.personal_pdf import (
        PersonalPdfNoDisponible, resolver_url_pdf, verificar_monto,
    )

    try:
        pdf = descargar_pdf(resolver_url_pdf(url))
    except PersonalPdfNoDisponible:
        raise
    except Exception as exc:
        raise PersonalPdfNoDisponible(f"falló la descarga: {exc}") from exc

    verificar_monto(pdf, monto)
    return pdf


def descargar_factura_aysa(url: str, nro_factura: str | None, monto: float) -> bytes:
    """
    La cadena de redirecciones de AySA más la verificación de que el PDF sea el
    de esta factura. Cualquier fallo sale como AysaPdfNoDisponible para que el
    caller no tenga que distinguir en cuál de los pasos se rompió.
    """
    from bot.tools.aysa_pdf import (
        AysaPdfNoDisponible, resolver_url_pdf, verificar_factura,
    )

    try:
        pdf = descargar_pdf(resolver_url_pdf(url))
    except AysaPdfNoDisponible:
        raise
    except Exception as exc:
        raise AysaPdfNoDisponible(f"falló la descarga: {exc}") from exc

    verificar_factura(pdf, nro_factura, monto)
    return pdf


def descargar_factura_edenor(url: str, identificador: str, monto: float) -> bytes:
    """
    El pedido a la API pública de la Oficina Virtual más la verificación de que
    el PDF sea el de esta factura. Cualquier fallo sale como EdenorPdfNoDisponible
    para que el caller no tenga que distinguir en cuál de los pasos se rompió.
    """
    from bot.tools.edenor_pdf import (
        CABECERAS, EdenorPdfNoDisponible, token_de_url, url_del_pdf,
        verificar_cuenta, verificar_factura,
    )

    try:
        token = token_de_url(url)
        verificar_cuenta(token, identificador)
        pdf = descargar_pdf(url_del_pdf(token), headers=CABECERAS)
    except EdenorPdfNoDisponible:
        raise
    except Exception as exc:
        raise EdenorPdfNoDisponible(f"falló la descarga: {exc}") from exc

    verificar_factura(pdf, identificador, monto)
    return pdf


def descargar_factura_consorcio(url: str, monto: float) -> bytes:
    """
    Re-baja la liquidación de expensas y confirma que siga siendo la de esta
    factura antes de archivarla.

    Se vuelve a bajar en vez de arrastrar los bytes que ya tenía resolver_expensas:
    mantiene un solo contrato en pdf_de_factura (URL adentro, bytes afuera) y el
    archivo es público y chico. La verificación es la misma que hizo el parseo,
    así que si el consorcio republica el PDF entre una descarga y la otra no pasa
    desapercibido.
    """
    servicio = queries.obtener_servicio_por_slug("consorcio_gallo")
    unidad = (servicio or {}).get("unidad_funcional")
    if not unidad:
        raise ExpensasNoParseable(
            "el servicio 'consorcio_gallo' no tiene unidad_funcional configurada"
        )

    pdf = descargar_pdf(url)
    fila = parsear_pdf_unidades(pdf, unidad)
    if abs(fila.total - monto) > 0.01:
        raise ExpensasNoParseable(
            f"el PDF dice ${formatear_monto_ar(fila.total)} y la factura "
            f"${formatear_monto_ar(monto)}"
        )
    return pdf


def pdf_de_factura(parseada: FacturaParseada) -> bytes:
    """
    Baja el PDF con el flujo del servicio que corresponda.

    Personal, AySA y Edenor enlazan el PDF con un token que no pide login, cada
    uno con su flujo. El consorcio es el más directo: el PDF está en un bucket S3
    público y resolver_expensas ya lo bajó para sacarle el monto. MetroGAS es el
    único que no se puede: su portal es público pero el endpoint del PDF valida un
    reCAPTCHA en el servidor, así que ese sigue entrando a mano por Telegram. Si
    mañana se suma otro, acá va el ruteo.
    """
    if parseada.servicio == "personal":
        return descargar_factura_personal(parseada.pdf_urls[0], parseada.monto)
    if parseada.servicio == "aysa":
        return descargar_factura_aysa(parseada.pdf_urls[0], parseada.nro_factura,
                                      parseada.monto)
    if parseada.servicio == "edenor":
        return descargar_factura_edenor(parseada.pdf_urls[0], parseada.identificador,
                                        parseada.monto)
    if parseada.servicio == "consorcio_gallo":
        return descargar_factura_consorcio(parseada.pdf_urls[0], parseada.monto)
    raise ValueError(
        f"el servicio {parseada.servicio!r} trae link al PDF pero no tiene "
        f"descarga automática implementada"
    )


def archivar_pdf_de_factura(parseada: FacturaParseada, factura: dict) -> dict:
    """
    Baja el PDF que enlaza el mail y lo cuelga de la factura recién registrada,
    con la misma estructura de carpetas que usa el archivado por Telegram.

    Qué servicio se puede bajar solo lo decide pdf_de_factura().
    """
    from bot.tools.archivado import subir_a_drive

    servicio = queries.obtener_servicio_por_slug(parseada.servicio)
    if servicio is None:
        raise ServicioDesconocido(f"el servicio {parseada.servicio!r} no está registrado")

    pdf = pdf_de_factura(parseada)
    subido = subir_a_drive(pdf, "application/pdf", servicio["nombre"],
                           "factura", parseada.vencimiento)

    return queries.insertar_archivo_drive({
        "tipo": "factura",
        "comercio": servicio["nombre"],
        "fecha": parseada.vencimiento.isoformat(),
        "categoria": None,
        "monto": parseada.monto,
        "moneda": "ARS",
        "drive_file_id": subido["file_id"],
        "drive_file_name": subido["file_name"],
        "drive_web_view_link": subido["web_view_link"],
        "drive_folder_path": subido["folder_path"],
        "mime_type": "application/pdf",
        "factura_id": factura["id"],
        # Un reintento puede llegar con la factura ya paga: hereda su gasto.
        "gasto_id": factura.get("gasto_id"),
    })


async def _avisar_pdf_no_archivado(bot, chat_id: int, parseada: FacturaParseada,
                                   exc: Exception) -> None:
    """
    Aviso suave: la factura SÍ quedó registrada, solo falta el documento.

    No usa alertar_error a propósito: ese formato cierra con "nada se guardó",
    que acá sería mentira y te haría revisar algo que está bien.
    """
    detalle = str(exc)[:200]
    texto = (
        f"\U0001f4ce *No pude bajar el PDF de {escapar_md(parseada.servicio)}*\n"
        f"La factura quedó registrada igual; solo falta el documento.\n"
        f"Mandámelo por acá cuando puedas.\n"
        f"• Detalle: {escapar_md(detalle)}"
    )
    try:
        await bot.send_message(chat_id=chat_id, text=texto, parse_mode="Markdown")
    except Exception:
        logger.exception("No pude avisar que faltó el PDF")


def _resumen(factura: FacturaParseada, nombre: str, archivada: bool = False) -> str:
    lineas = [
        "\U0001f9fe *Factura registrada*",
        f"• *{escapar_md(nombre)}*",
        f"• ${formatear_monto_ar(factura.monto)}",
        f"• Vence: {factura.vencimiento}",
    ]
    if archivada:
        lineas.append("• \U0001f4ce PDF archivado en Drive")
    return "\n".join(lineas)


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

    # El PDF es opcional: la factura ya está guardada, así que un fallo acá se
    # avisa pero NO deja el mail sin leer. Si lo reintentáramos, un flujo de
    # descarga roto alertaría en cada ciclo para siempre; el repaso de los lunes
    # ya reclama la documentación faltante, que es la cadencia correcta.
    archivada = False
    if parseada.pdf_urls:
        try:
            await asyncio.to_thread(archivar_pdf_de_factura, parseada, resultado.factura)
            archivada = True
        except Exception as exc:
            logger.warning("No pude archivar el PDF de %s: %s", parseada.servicio, exc)
            await _avisar_pdf_no_archivado(bot, chat_id, parseada, exc)

    servicio = resultado.factura.get("servicios") or {}
    nombre = servicio.get("nombre") or parseada.servicio
    try:
        await bot.send_message(chat_id=chat_id, text=_resumen(parseada, nombre, archivada),
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
