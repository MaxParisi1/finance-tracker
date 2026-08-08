"""
Tests del armado del mail que consume el poller.

Contexto: las facturas llegan a una casilla de Outlook y se reenvían al Gmail
configurado. Outlook tiene tres modos de reenvío y cada uno deja el mensaje de
forma distinta; el objetivo es que los tres terminen funcionando.
"""

import base64

import pytest

from bot.tools.gmail_reader import _extract_body, _find_part, desanidar_reenvio


def _b64(texto: str) -> str:
    return base64.urlsafe_b64encode(texto.encode()).decode()


def _parte(mime, texto=None, partes=None, headers=None):
    p = {"mimeType": mime}
    if texto is not None:
        p["body"] = {"data": _b64(texto)}
    if partes is not None:
        p["parts"] = partes
    if headers is not None:
        p["headers"] = [{"name": k, "value": v} for k, v in headers.items()]
    return p


ORIGINAL = _parte(
    "multipart/alternative",
    partes=[_parte("text/html", "<p>TOTAL A PAGAR $13.405,84</p>")],
    headers={"From": "Edenor <facturadigital@edenor.com>", "Subject": "Tu factura"},
)


# ──────────────────────────────────────────────
# Redirigir / reenvío inline: el payload no está anidado
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_mensaje_normal_no_se_toca():
    """Redirect de Outlook llega como un mail común: no hay nada que desanidar."""
    assert desanidar_reenvio(ORIGINAL) is ORIGINAL


@pytest.mark.unit
def test_mensaje_sin_partes_no_rompe():
    plano = _parte("text/plain", "hola")
    assert desanidar_reenvio(plano) is plano


# ──────────────────────────────────────────────
# Reenviar como adjunto: el original va en message/rfc822
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_reenvio_como_adjunto_devuelve_el_mensaje_original():
    """
    Sin esto, 'Reenviar como adjunto' de Outlook dejaría el bot ciego: el From:
    sería tu casilla y el cuerpo, el texto vacío del reenvío.
    """
    envoltorio = _parte("multipart/mixed", partes=[
        _parte("text/plain", "Te reenvío esto"),
        _parte("message/rfc822", partes=[ORIGINAL]),
    ])
    interno = desanidar_reenvio(envoltorio)
    assert "13.405,84" in _find_part(interno, "text/html")


@pytest.mark.unit
def test_reenvio_como_adjunto_con_headers_en_la_parte_rfc822():
    """Algunos clientes ponen las cabeceras del original en la parte message/rfc822."""
    rfc = _parte("message/rfc822",
                 partes=[_parte("text/html", "<p>TOTAL A PAGAR $5.266,75</p>")],
                 headers={"From": "MetroGAS <facturadigital@metrogas.com.ar>"})
    envoltorio = _parte("multipart/mixed", partes=[_parte("text/plain", "fwd"), rfc])
    interno = desanidar_reenvio(envoltorio)
    cabeceras = {h["name"]: h["value"] for h in interno.get("headers", [])}
    assert "metrogas" in cabeceras.get("From", "")


@pytest.mark.unit
def test_reenvio_anidado_dos_veces_se_desanida_hasta_el_fondo():
    """Un reenvío de un reenvío: se baja hasta el mensaje real."""
    nivel1 = _parte("message/rfc822", partes=[ORIGINAL])
    nivel2 = _parte("multipart/mixed", partes=[
        _parte("text/plain", "fwd"),
        _parte("message/rfc822", partes=[
            _parte("multipart/mixed", partes=[_parte("text/plain", "fwd"), nivel1])
        ]),
    ])
    assert "13.405,84" in _find_part(desanidar_reenvio(nivel2), "text/html")


# ──────────────────────────────────────────────
# Extracción de cuerpo
# ──────────────────────────────────────────────

@pytest.mark.unit
def test_prefiere_text_plain_sobre_html():
    p = _parte("multipart/alternative", partes=[
        _parte("text/plain", "plano"),
        _parte("text/html", "<p>html</p>"),
    ])
    assert _extract_body(p) == "plano"


@pytest.mark.unit
def test_cae_a_html_si_no_hay_plano():
    p = _parte("multipart/alternative", partes=[_parte("text/html", "<p>hola</p>")])
    assert "hola" in _extract_body(p)


@pytest.mark.unit
def test_sin_cuerpo_devuelve_vacio():
    assert _extract_body(_parte("multipart/mixed", partes=[])) == ""
