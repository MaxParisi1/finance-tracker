"""
Reversos de Prisma: un consumo anulado llega como un mail aparte, con la misma
estructura que el consumo original, así que el regex lo matchea igual.

Fixture real: el reverso de Cabify del 18/08/2026, que en producción se registró
como un segundo gasto idéntico al que anulaba.
"""

import email as email_lib
import re
from email import policy
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.gmail_poller import _es_prisma_reverso, _parse_prisma_email

FIXTURES = Path(__file__).parent / "fixtures"


def _cuerpo(nombre: str) -> str:
    """Replica el HTML→texto de gmail_reader._extract_body sobre un .eml real."""
    ruta = FIXTURES / "emails" / f"{nombre}.eml"
    if not ruta.exists():
        # Los .eml traen datos personales y están en .gitignore, así que no viajan
        # con el repo. Fuera de la máquina donde se guardaron, se saltea en vez de
        # romper la colección del suite entero.
        pytest.skip(f"falta el fixture {ruta.name}", allow_module_level=True)
    msg = email_lib.message_from_string(
        ruta.read_text(encoding="utf-8", errors="replace"), policy=policy.default
    )
    html = ""
    for parte in msg.walk():
        if parte.get_content_type() == "text/html":
            carga = parte.get_payload(decode=True)
            if carga:
                html = carga.decode(parte.get_content_charset() or "utf-8", errors="replace")
                break
    html = re.sub(r"</?(tr|td|br|p|div|table|span)[^>]*>", "\n", html, flags=re.IGNORECASE)
    texto = re.sub(r"<[^>]+>", "", html)
    texto = re.sub(r"\n[ \t]*\n+", "\n", texto)
    return re.sub(r"[ \t]+", " ", texto).strip()


CUERPO_REVERSO = _cuerpo("prisma_reverso")

CUERPO_CONSUMO = (
    "Aviso de Consumo\n"
    "Queremos informarte que registramos un consumo de\n$\n4.680,46\n"
    " en el establecimiento \nCabify2634c4VrbvXS \n , el día \n"
    "18/08/2026 a las \n23:30hs\n , con la tarjeta de \nMAXIMO PARISI\n"
    " finalizada en \n1670\n."
)


@pytest.mark.unit
def test_el_mail_real_se_reconoce_como_reverso():
    assert _es_prisma_reverso(CUERPO_REVERSO)


@pytest.mark.unit
def test_un_consumo_normal_no_es_reverso():
    assert not _es_prisma_reverso(CUERPO_CONSUMO)


@pytest.mark.unit
def test_el_reverso_parsea_los_mismos_campos_y_queda_marcado():
    """
    El reverso tiene que parsear igual que un consumo: sus datos son los que
    identifican al gasto a anular. Lo único que cambia es la bandera.
    """
    parsed = _parse_prisma_email({"body": CUERPO_REVERSO, "subject": "Novedades"})
    assert parsed["_reverso"] is True
    assert parsed["monto"] == 4680.46
    assert parsed["comercio"] == "Cabify2634C4Vrbvxs"
    assert parsed["fecha"] == "2026-08-18"
    assert parsed["sufijo"] == "1670"


@pytest.mark.unit
def test_el_consumo_no_queda_marcado_como_reverso():
    parsed = _parse_prisma_email({"body": CUERPO_CONSUMO, "subject": "Novedades"})
    assert parsed["_reverso"] is False
    assert parsed["monto"] == 4680.46


@pytest.mark.unit
def test_una_transaccion_denegada_sigue_teniendo_prioridad():
    """Un rechazo nunca creó un gasto, así que no hay nada que anular."""
    cuerpo = CUERPO_REVERSO.replace("reverso", "consumo denegado")
    assert _parse_prisma_email({"body": cuerpo, "subject": "x"}) == {"_denied": True}


@pytest.mark.unit
@pytest.mark.parametrize("palabra", ["reverso", "devolución", "anulación", "reintegro", "contracargo"])
def test_variantes_de_anulacion(palabra):
    """
    Prisma no siempre dice "reverso". Todas estas significan lo mismo: la plata
    vuelve, y el gasto no debe quedar registrado.
    """
    assert _es_prisma_reverso(f"Registramos un {palabra} por la autorización del consumo")


# ──────────────────────────────────────────────
# Efecto del reverso sobre el gasto original
# ──────────────────────────────────────────────

import asyncio

from bot import gmail_poller


class BotFalso:
    def __init__(self):
        self.mensajes = []

    async def send_message(self, **kw):
        self.mensajes.append(kw)


MAIL_REVERSO = {"id": "msg-rev", "subject": "Novedades de tus transacciones",
                "body": CUERPO_REVERSO}

PARSED = {"monto": 4680.46, "moneda": "ARS", "comercio": "Cabify2634C4Vrbvxs",
          "fecha": "2026-08-18", "sufijo": "1670", "_reverso": True}


@pytest.fixture(autouse=True)
def _limpiar_alertados():
    gmail_poller._emails_alertados.clear()
    yield
    gmail_poller._emails_alertados.clear()


@pytest.mark.unit
def test_el_reverso_anula_el_gasto_original_y_marca_leido():
    bot_ = BotFalso()
    with patch.object(gmail_poller, "buscar_gasto_para_reverso",
                      return_value={"id": "gasto-77"}) as buscar, \
         patch.object(gmail_poller, "eliminar_gasto") as eliminar, \
         patch.object(gmail_poller, "mark_as_read") as marcar:
        ok = asyncio.run(gmail_poller._procesar_reverso(bot_, 1, MAIL_REVERSO, PARSED))

    assert ok is True
    buscar.assert_called_once_with("Cabify2634C4Vrbvxs", 4680.46, "1670", "2026-08-18")
    eliminar.assert_called_once_with("gasto-77")
    marcar.assert_called_once_with("msg-rev")
    assert "Reverso registrado" in bot_.mensajes[0]["text"]


@pytest.mark.unit
def test_sin_consumo_original_no_marca_leido():
    """
    Si el reverso se procesa antes que su consumo, el mail queda sin leer para
    reintentar. Marcarlo perdería la anulación para siempre.
    """
    bot_ = BotFalso()
    with patch.object(gmail_poller, "buscar_gasto_para_reverso", return_value=None), \
         patch.object(gmail_poller, "eliminar_gasto") as eliminar, \
         patch.object(gmail_poller, "mark_as_read") as marcar:
        ok = asyncio.run(gmail_poller._procesar_reverso(bot_, 1, MAIL_REVERSO, PARSED))

    assert ok is False
    eliminar.assert_not_called()
    marcar.assert_not_called()
    assert "sin consumo asociado" in bot_.mensajes[0]["text"].lower()


@pytest.mark.unit
def test_no_repite_la_alerta_del_reverso_huerfano():
    """El poller corre cada 15 minutos; sin dedup serían 96 alertas por día."""
    bot_ = BotFalso()
    with patch.object(gmail_poller, "buscar_gasto_para_reverso", return_value=None), \
         patch.object(gmail_poller, "mark_as_read"):
        for _ in range(3):
            asyncio.run(gmail_poller._procesar_reverso(bot_, 1, MAIL_REVERSO, PARSED))

    assert len(bot_.mensajes) == 1


@pytest.mark.unit
def test_los_reversos_se_procesan_despues_de_los_consumos():
    """
    Consumo y reverso suelen llegar juntos. Si el reverso va primero no encuentra
    nada que anular y el gasto sobrevive un ciclo entero.
    """
    lote = [
        {"id": "rev", "body": CUERPO_REVERSO},
        {"id": "con", "body": CUERPO_CONSUMO},
    ]
    lote.sort(key=lambda e: gmail_poller._es_prisma_reverso(e.get("body", "")))
    assert [e["id"] for e in lote] == ["con", "rev"]
