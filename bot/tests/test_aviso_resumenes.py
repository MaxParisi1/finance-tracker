"""
Escucha de avisos de resúmenes (LISTEN/NOTIFY) en lugar del poller de 10 s.

Bug real: desde el deploy del 09/11/2026 el bot preguntaba cada 10 segundos si
había un resumen pendiente (~17.000 consultas por día para algo mensual) y el
saldo de Disk IO de la instancia Free bajó de 99 % a 83 % en un día.

Lo que se protege: que un aviso dispare el ciclo, que una ráfaga de avisos (la
web marca los movimientos de a uno) se procese UNA vez y completa, que nada
quede colgado si se pierde un aviso o se corta la conexión, y que se pueda
volver al poller viejo con una variable de entorno.
"""

import asyncio
from unittest.mock import patch

import pytest

from bot.tools import aviso_resumenes as aviso


class Fin(BaseException):
    """Corta el loop infinito en los tests (el loop solo deja pasar BaseException)."""


class ConexionFalsa:
    """
    Conexión de psycopg simulada. `guion` es una lista de pasos que consume
    `notifies()` en orden: "aviso" entrega un aviso, "nada" vence el timeout
    sin avisos, "corte" simula que se cayó la conexión. Al terminar el guion
    corta el test.
    """

    def __init__(self, guion):
        self.guion = list(guion)
        self.ejecutado: list[str] = []
        self.timeouts: list[float] = []
        self.cuelga: set[str] = set()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql):
        self.ejecutado.append(sql)
        if sql in self.cuelga:
            await asyncio.Event().wait()

    async def notifies(self, *, timeout=None, stop_after=None):
        self.timeouts.append(timeout)
        if not self.guion:
            raise Fin()
        paso = self.guion.pop(0)
        if paso == "corte":
            raise OSError("server closed the connection unexpectedly")
        if paso == "aviso":
            yield object()


def _correr(conexiones, ciclos):
    """Corre el loop de escucha hasta que se acabe el guion; devuelve las esperas de reintento."""
    pendientes = list(conexiones)
    esperas = []

    async def conectar():
        if not pendientes:
            raise Fin()
        c = pendientes.pop(0)
        if isinstance(c, Exception):
            raise c
        return c

    async def dormir(seg):
        esperas.append(seg)

    with patch.object(aviso.resumenes, "procesar_ciclo", side_effect=lambda: ciclos.append(1)), \
         patch.object(aviso.asyncio, "sleep", side_effect=dormir):
        with pytest.raises(Fin):
            asyncio.run(aviso.escuchar(conectar))
    return esperas


def test_al_conectar_barre_lo_que_llego_sin_escuchar():
    """Un resumen subido durante un deploy-bot no tiene quién reciba el aviso."""
    ciclos = []
    conn = ConexionFalsa([])
    _correr([conn], ciclos)
    assert conn.ejecutado == ["LISTEN resumenes"]
    assert len(ciclos) == 1


def test_un_aviso_dispara_el_ciclo():
    ciclos = []
    # aviso → silencio (vence la espera corta) → ciclo
    _correr([ConexionFalsa(["aviso", "nada"])], ciclos)
    assert len(ciclos) == 2  # barrido inicial + el del aviso


def test_una_rafaga_de_avisos_se_procesa_una_sola_vez():
    """
    La web marca los movimientos con un UPDATE por fila. Si el bot procesara con
    el primer aviso, los impuestos de un resumen podrían quedar partidos en dos
    tandas y el gasto agrupado saldría con un total incompleto.
    """
    ciclos = []
    conn = ConexionFalsa(["aviso", "aviso", "aviso", "aviso", "nada"])
    _correr([conn], ciclos)
    assert len(ciclos) == 2
    # La primera espera es la larga (barrido); las siguientes, la de silencio.
    assert conn.timeouts[0] == aviso.BARRIDO
    assert conn.timeouts[1:5] == [aviso.SILENCIO] * 4


def test_una_rafaga_interminable_no_bloquea_el_ciclo():
    ciclos = []
    conn = ConexionFalsa(["aviso"] * 50)
    reloj = iter(range(10_000))
    with patch.object(aviso, "monotonic", side_effect=lambda: next(reloj)), \
         patch.object(aviso, "RAFAGA_MAX", 5):
        _correr([conn], ciclos)
    # Corta la ráfaga por tiempo y procesa, sin esperar a que haya silencio:
    # 50 avisos seguidos dan varios ciclos, no uno solo al final.
    assert len(ciclos) > 3


def test_sin_avisos_el_barrido_periodico_procesa_y_prueba_la_conexion():
    """Si un aviso se perdió, lo levanta el barrido; el SELECT 1 detecta una conexión muerta."""
    ciclos = []
    conn = ConexionFalsa(["nada"])
    _correr([conn], ciclos)
    assert conn.ejecutado == ["LISTEN resumenes", "SELECT 1"]
    assert len(ciclos) == 2


def test_si_se_corta_la_conexion_procesa_y_reconecta():
    ciclos = []
    primera = ConexionFalsa(["corte"])
    segunda = ConexionFalsa([])
    esperas = _correr([primera, segunda], ciclos)
    assert segunda.ejecutado == ["LISTEN resumenes"]
    # barrido al conectar + barrido tras el corte + barrido al reconectar
    assert len(ciclos) == 3
    assert esperas == [aviso.REINTENTO_MIN]


def test_si_no_puede_conectar_sigue_barriendo_y_espacia_los_reintentos():
    """Sin escucha el bot no deja colgado un resumen: barre en cada reintento."""
    ciclos = []
    caida = OSError("connection refused")
    esperas = _correr([caida] * 12, ciclos)
    assert len(ciclos) == 12
    assert esperas[:3] == [aviso.REINTENTO_MIN, aviso.REINTENTO_MIN * 2, aviso.REINTENTO_MIN * 4]
    assert max(esperas) == aviso.REINTENTO_MAX


def test_un_error_del_ciclo_no_corta_la_escucha():
    ciclos = []

    def falla():
        ciclos.append(1)
        raise RuntimeError("Supabase 503")

    conn = ConexionFalsa(["aviso", "nada"])

    async def conectar():
        if conn.guion or not ciclos:
            return conn
        raise Fin()

    async def dormir(_):
        pass

    with patch.object(aviso.resumenes, "procesar_ciclo", side_effect=falla), \
         patch.object(aviso.asyncio, "sleep", side_effect=dormir):
        with pytest.raises(Fin):
            asyncio.run(aviso.escuchar(conectar))
    assert len(ciclos) == 2


@pytest.mark.parametrize("entorno", [
    {"RESUMENES_MODO": "poll", "SUPABASE_DB_URL": "postgresql://x"},
    {"SUPABASE_DB_URL": ""},
])
def test_rollback_o_sin_url_vuelve_al_poller_viejo(entorno):
    """RESUMENES_MODO=poll es el rollback: el bot vuelve a preguntar cada 10 s como antes."""
    llamadas = []

    async def poller():
        llamadas.append("poll")

    async def escuchar(_):
        llamadas.append("escucha")

    with patch.dict("os.environ", entorno, clear=False), \
         patch.object(aviso.resumenes, "loop_resumenes", side_effect=poller), \
         patch.object(aviso, "escuchar", side_effect=escuchar):
        asyncio.run(aviso.loop_resumenes())
    assert llamadas == ["poll"]


def test_con_url_y_sin_rollback_escucha():
    llamadas = []

    async def escuchar(_):
        llamadas.append("escucha")

    with patch.dict("os.environ", {"SUPABASE_DB_URL": "postgresql://x"}, clear=False), \
         patch.dict("os.environ", {}, clear=False) as env, \
         patch.object(aviso, "escuchar", side_effect=escuchar):
        env.pop("RESUMENES_MODO", None)
        asyncio.run(aviso.loop_resumenes())
    assert llamadas == ["escucha"]


def test_si_un_ciclo_deja_errores_reintenta_pronto_y_no_en_15_minutos():
    """Un movimiento que falló al cargarse queda 'a_cargar' y ya no va a llegar otro aviso."""
    ciclos = []
    conn = ConexionFalsa(["nada"])
    with patch.object(aviso.resumenes, "procesar_ciclo", side_effect=lambda: ciclos.append(1) or True), \
         patch.object(aviso.asyncio, "sleep", side_effect=lambda s: None):
        with pytest.raises(Fin):
            asyncio.run(aviso.escuchar(_conectar_una(conn)))
    assert conn.timeouts[0] == aviso.REINTENTO_CICLO


def test_una_conexion_que_se_cae_enseguida_no_resetea_la_espera():
    """Si el pooler corta cada pocos segundos, el bot no puede volver a ser un poller de 10 s."""
    ciclos = []
    esperas = _correr([ConexionFalsa(["corte"]), ConexionFalsa(["corte"]), ConexionFalsa([])], ciclos)
    assert esperas == [aviso.REINTENTO_MIN, aviso.REINTENTO_MIN * 2]


def test_un_select_1_colgado_en_un_socket_muerto_reconecta():
    ciclos = []
    colgada = ConexionFalsa(["nada"])
    colgada.cuelga = {"SELECT 1"}
    nueva = ConexionFalsa([])
    with patch.object(aviso, "TIMEOUT_SQL", 0.01):
        esperas = _correr([colgada, nueva], ciclos)
    assert nueva.ejecutado == ["LISTEN resumenes"]
    assert esperas == [aviso.REINTENTO_MIN]


def test_sin_psycopg_instalado_vuelve_al_poller():
    """Olvidarse el pip install antes del deploy-bot no puede dejar los resúmenes sin procesar."""
    import builtins

    llamadas = []
    importar = builtins.__import__

    def sin_psycopg(nombre, *args, **kwargs):
        if nombre == "psycopg":
            raise ImportError(nombre)
        return importar(nombre, *args, **kwargs)

    async def poller():
        llamadas.append("poll")

    with patch.dict("os.environ", {"SUPABASE_DB_URL": "postgresql://x", "RESUMENES_MODO": ""}), \
         patch.object(builtins, "__import__", side_effect=sin_psycopg), \
         patch.object(aviso.resumenes, "loop_resumenes", side_effect=poller):
        asyncio.run(aviso.loop_resumenes())
    assert llamadas == ["poll"]


def _conectar_una(conn):
    usada = []

    async def conectar():
        if usada:
            raise Fin()
        usada.append(1)
        return conn

    return conectar
