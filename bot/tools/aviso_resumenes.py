"""
Despierta el ciclo de resúmenes cuando la base avisa que hay trabajo.

La web y el bot no tienen API entre ellos. Antes el bot preguntaba cada 10
segundos si había algo (~17.000 consultas por día para algo que pasa una vez
por mes, y la instancia Free lo sintió en el saldo de Disk IO). Ahora la base
avisa por el canal `resumenes` (migración 019) y el bot escucha con LISTEN en
una conexión Postgres propia.

El aviso es solo un despertador; el trabajo lo sigue haciendo
`resumenes.procesar_ciclo`, que lee las tablas como siempre. Por eso perder un
aviso no rompe nada, solo demora:

  - Al conectar (arranque, deploy-bot, reconexión) se barre una vez: lo que se
    subió mientras nadie escuchaba.
  - Cada BARRIDO sin avisos se barre igual y se prueba la conexión.
  - Si la conexión se cae, se barre en cada reintento, espaciándolos.

Rollback: `RESUMENES_MODO=poll` en el .env del bot vuelve al poller de 10 s.
Sin `SUPABASE_DB_URL` también cae al poller, avisando en el log.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from bot.tools import resumenes

logger = logging.getLogger(__name__)

CANAL = "resumenes"
BARRIDO = 15 * 60  # segundos sin avisos hasta barrer igual
# La web marca los movimientos con un UPDATE por fila: cada uno avisa. Se
# espera a que haya SILENCIO segundos sin avisos para procesar la tanda entera
# (si no, los impuestos de un resumen podrían cargarse partidos en dos gastos),
# pero nunca más de RAFAGA_MAX.
SILENCIO = 3
RAFAGA_MAX = 30
REINTENTO_MIN = 10
REINTENTO_MAX = 5 * 60
# Si un ciclo dejó un movimiento 'a_cargar' por un error (Drive, la base), no
# va a llegar otro aviso: se reintenta a este ritmo hasta que salga.
REINTENTO_CICLO = 60
# Una conexión que se cae antes de esto no cuenta como recuperada: si el pooler
# la corta enseguida una y otra vez, los reintentos se siguen espaciando.
VIDA_SANA = 60
# Tope para LISTEN y SELECT 1: en un socket muerto con datos sin confirmar,
# TCP puede tardar muchos minutos en rendirse.
TIMEOUT_SQL = 20

Conectar = Callable[[], Awaitable[Any]]


async def loop_resumenes() -> None:
    """Punto de entrada que arranca el bot: escucha avisos, o el poller si se pidió rollback."""
    url = os.environ.get("SUPABASE_DB_URL", "").strip()
    if os.environ.get("RESUMENES_MODO", "").strip().lower() == "poll":
        logger.info("Resúmenes en modo poller (RESUMENES_MODO=poll)")
        await resumenes.loop_resumenes()
        return
    if not url:
        logger.warning("Falta SUPABASE_DB_URL: los resúmenes vuelven al poller de %ds", resumenes.INTERVALO)
        await resumenes.loop_resumenes()
        return
    try:
        import psycopg  # noqa: F401
    except ImportError:
        logger.warning("Falta psycopg (pip install -r requirements.txt): los resúmenes vuelven al poller")
        await resumenes.loop_resumenes()
        return
    await escuchar(lambda: _conectar(url))


async def _conectar(url: str) -> Any:
    import psycopg

    return await psycopg.AsyncConnection.connect(
        url,
        autocommit=True,  # LISTEN fuera de una transacción: si no, los avisos no llegan
        connect_timeout=15,
        application_name="finance-bot-resumenes",
        # Que una conexión muerta (el pooler la soltó, se cayó la red) se note
        # en un par de minutos y no recién en el próximo barrido.
        keepalives=1,
        keepalives_idle=60,
        keepalives_interval=15,
        keepalives_count=4,
        # Y si hay datos enviados sin confirmar (un SELECT 1 a un socket muerto).
        tcp_user_timeout=30_000,
    )


async def escuchar(conectar: Conectar) -> None:
    espera = REINTENTO_MIN
    while True:
        try:
            async with await conectar() as conn:
                await asyncio.wait_for(conn.execute(f"LISTEN {CANAL}"), TIMEOUT_SQL)
                logger.info("Escuchando avisos de resúmenes (barrido cada %ds)", BARRIDO)
                conectado = monotonic()
                fallo = await _ciclo()
                while True:
                    if conectado is not None and monotonic() - conectado >= VIDA_SANA:
                        espera, conectado = REINTENTO_MIN, None
                    if await _esperar_aviso(conn, REINTENTO_CICLO if fallo else BARRIDO):
                        await _esperar_silencio(conn)
                    else:
                        await asyncio.wait_for(conn.execute("SELECT 1"), TIMEOUT_SQL)
                    fallo = await _ciclo()
        except Exception:
            logger.exception("Se cortó la escucha de resúmenes; reintento en %ds", espera)
        # Mientras no hay escucha, que nada quede colgado.
        await _ciclo()
        await asyncio.sleep(espera)
        espera = min(espera * 2, REINTENTO_MAX)


async def _esperar_aviso(conn: Any, timeout: float) -> bool:
    hubo = False
    # Se deja terminar el generador (stop_after=1) en vez de salir con return:
    # abandonarlo a mitad de camino puede dejar tomada la conexión.
    async for _ in conn.notifies(timeout=timeout, stop_after=1):
        hubo = True
    return hubo


async def _esperar_silencio(conn: Any) -> None:
    fin = monotonic() + RAFAGA_MAX
    while monotonic() < fin:
        if not await _esperar_aviso(conn, SILENCIO):
            return


async def _ciclo() -> bool:
    """Corre el ciclo; True si hay que reintentar pronto."""
    try:
        return bool(await asyncio.to_thread(resumenes.procesar_ciclo))
    except Exception:
        logger.exception("Error en el ciclo de resúmenes")
        return True
