"""
Recordatorios de vencimiento y de documentación faltante.

Invierte la iniciativa: en vez de que te tengas que acordar de revisar, el bot
te dice qué vence y qué falta archivar. Es la pieza que convierte "registro
total" de una intención en algo que el sistema sostiene.

La lógica de qué avisar es pura y está separada del envío, así que se puede
testear con fechas fijas sin tocar Telegram ni la base.

Cadencia pensada para no volverse ruido: los avisos de vencimiento salen en
días puntuales (3 y 1 antes, el día mismo) y después cada 3 días mientras siga
impaga. Los de documentación faltante, una vez por semana.
"""

import logging
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)

__all__ = [
    "Aviso", "calcular_avisos", "formatear_avisos",
    "DIAS_AVISO_PREVIO", "CADENCIA_VENCIDA", "DIA_REVISION_SEMANAL",
]

# Días antes del vencimiento en los que se avisa.
DIAS_AVISO_PREVIO = (3, 1, 0)

# Ya vencida e impaga: se insiste cada tantos días.
CADENCIA_VENCIDA = 3

# Día de la semana para el repaso de documentación faltante (0 = lunes).
DIA_REVISION_SEMANAL = 0

# Cuánto para atrás se revisa la documentación faltante.
MESES_REVISION = 3

TIPO_VENCE = "vence"
TIPO_VENCIDA = "vencida"
TIPO_FALTA_FACTURA = "falta_factura"
TIPO_FALTA_COMPROBANTE = "falta_comprobante"


@dataclass(frozen=True)
class Aviso:
    tipo: str
    servicio: str
    monto: float
    vencimiento: date
    dias: int          # negativo = ya venció
    factura_id: str


def _tipos_de_archivo(factura: dict) -> set[str]:
    return {a.get("tipo") for a in (factura.get("archivos_drive") or [])}


def _fecha(valor) -> date | None:
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None


def _monto(factura: dict) -> float:
    try:
        return float(factura.get("monto") or 0)
    except (TypeError, ValueError):
        return 0.0


def _nombre(factura: dict) -> str:
    return (factura.get("servicios") or {}).get("nombre") or "(servicio desconocido)"


def _meses_atras(referencia: date, meses: int) -> date:
    """Primer día del mes que está `meses` antes del de `referencia`."""
    total = referencia.year * 12 + (referencia.month - 1) - meses
    return date(total // 12, total % 12 + 1, 1)


def calcular_avisos(facturas: list[dict], hoy: date) -> list[Aviso]:
    """
    Decide qué avisar hoy. Función pura: mismas facturas y misma fecha, mismo
    resultado.

    Devuelve los avisos ordenados por urgencia (lo más vencido primero).
    """
    avisos: list[Aviso] = []
    es_dia_de_repaso = hoy.weekday() == DIA_REVISION_SEMANAL
    limite_revision = _meses_atras(hoy, MESES_REVISION)

    for f in facturas:
        vto = _fecha(f.get("vencimiento"))
        if vto is None:
            logger.warning("Factura %s sin vencimiento válido; se omite", f.get("id"))
            continue

        dias = (vto - hoy).days
        estado = f.get("estado")
        tipos = _tipos_de_archivo(f)
        base = dict(servicio=_nombre(f), monto=_monto(f), vencimiento=vto,
                    dias=dias, factura_id=f.get("id"))

        if estado == "pendiente":
            if dias >= 0 and dias in DIAS_AVISO_PREVIO:
                avisos.append(Aviso(tipo=TIPO_VENCE, **base))
            elif dias < 0 and (-dias) % CADENCIA_VENCIDA == 0:
                avisos.append(Aviso(tipo=TIPO_VENCIDA, **base))

        # Documentación faltante: repaso semanal, solo de los últimos meses.
        if es_dia_de_repaso and vto >= limite_revision:
            if "factura" not in tipos:
                avisos.append(Aviso(tipo=TIPO_FALTA_FACTURA, **base))
            if estado == "pagada" and "comprobante" not in tipos:
                avisos.append(Aviso(tipo=TIPO_FALTA_COMPROBANTE, **base))

    return sorted(avisos, key=lambda a: (a.dias, a.servicio))


def formatear_avisos(avisos: list[Aviso]) -> str | None:
    """Arma el mensaje de Telegram. Devuelve None si no hay nada que decir."""
    from bot.tools.montos import formatear_monto_ar

    if not avisos:
        return None

    def linea_pago(a: Aviso) -> str:
        if a.tipo == TIPO_VENCIDA:
            return f"🔴 *{a.servicio}* · ${formatear_monto_ar(a.monto)} · venció hace {-a.dias} días"
        if a.dias == 0:
            return f"🟠 *{a.servicio}* · ${formatear_monto_ar(a.monto)} · vence *hoy*"
        return f"🟡 *{a.servicio}* · ${formatear_monto_ar(a.monto)} · vence en {a.dias} días"

    pagos = [a for a in avisos if a.tipo in (TIPO_VENCE, TIPO_VENCIDA)]
    faltantes = [a for a in avisos if a.tipo in (TIPO_FALTA_FACTURA, TIPO_FALTA_COMPROBANTE)]

    bloques = []
    if pagos:
        total = sum(a.monto for a in pagos)
        bloques.append(
            "*Vencimientos*\n" + "\n".join(linea_pago(a) for a in pagos)
            + (f"\n_Total: ${formatear_monto_ar(total)}_" if len(pagos) > 1 else "")
        )
    if faltantes:
        detalle = "\n".join(
            f"📄 *{a.servicio}* {a.vencimiento.strftime('%m/%Y')} · "
            f"falta {'la factura' if a.tipo == TIPO_FALTA_FACTURA else 'el comprobante'}"
            for a in faltantes
        )
        bloques.append("*Documentación pendiente*\n" + detalle)

    return "\n\n".join(bloques)


# ──────────────────────────────────────────────
# Envío
# ──────────────────────────────────────────────

HORA_ENVIO = 9  # hora local del recordatorio diario


async def enviar_recordatorios(bot, chat_id: int, hoy: date | None = None) -> bool:
    """
    Calcula y envía los avisos del día. Devuelve True si mandó algo.
    Nunca propaga: un fallo acá no puede tumbar el bot.
    """
    import asyncio

    from bot.db import queries
    from bot.tools.alertas import alertar_error

    hoy = hoy or date.today()

    try:
        facturas = await asyncio.to_thread(
            queries.obtener_facturas_con_archivos, _meses_atras(hoy, MESES_REVISION).isoformat()
        )
    except Exception as exc:
        await alertar_error(bot, chat_id, titulo="No pude calcular los recordatorios",
                            exc=exc, clave="recordatorios-fetch")
        return False

    mensaje = formatear_avisos(calcular_avisos(facturas, hoy))
    if mensaje is None:
        logger.info("Sin recordatorios para %s", hoy)
        return False

    try:
        await bot.send_message(chat_id=chat_id, text=mensaje, parse_mode="Markdown")
        return True
    except Exception:
        logger.exception("No pude enviar los recordatorios")
        return False


async def loop_recordatorios(bot, chat_id: int) -> None:
    """
    Dispara los recordatorios una vez por día a HORA_ENVIO.

    Se despierta cada media hora en vez de dormir hasta la hora exacta: así un
    reinicio del bot no se saltea el aviso del día. La marca del último envío
    evita duplicar si se reinicia varias veces.
    """
    import asyncio
    from datetime import datetime

    ultimo_envio: date | None = None
    logger.info("Loop de recordatorios iniciado (envío diario a las %d:00)", HORA_ENVIO)

    while True:
        try:
            ahora = datetime.now()
            if ahora.hour >= HORA_ENVIO and ultimo_envio != ahora.date():
                await enviar_recordatorios(bot, chat_id, ahora.date())
                ultimo_envio = ahora.date()
        except Exception:
            logger.exception("Error en el loop de recordatorios")

        await asyncio.sleep(1800)
