"""
Cliente LLM para las tareas de extracción estructurada de los pollers.

Cadena de proveedores gratuitos: Groq (primario) → Cerebras (secundario).
Ambos exponen API compatible con OpenAI, así que se usan con el mismo SDK
cambiando `base_url`.

Por qué no Gemini: su free tier quedó en ~5 requests/día y el fallback a una key
paga ahora exige prepago (mínimo USD 10, con vencimiento a 12 meses). Dos free
tiers independientes dan mucho más margen que cualquiera de los dos solo, y no
requieren cargar plata por adelantado.

Criterio de errores: si TODOS los proveedores fallan por una causa transitoria
(cuota, red, 5xx), se levanta `LLMUnavailable`. El caller debe tratar eso como
"reintentar después", nunca como "no hay dato". Un email sin procesar se
reintenta gratis en el ciclo siguiente; un gasto guardado con la categoría
equivocada queda mal para siempre.
"""

import json
import logging
import os
import re
from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 30.0


class LLMUnavailable(Exception):
    """Ningún proveedor pudo responder por una causa transitoria. Reintentar más tarde."""


class LLMNoConfigurado(Exception):
    """No hay ninguna API key de proveedor configurada."""


@dataclass(frozen=True)
class Proveedor:
    nombre: str
    env_key: str
    base_url: str
    modelo_default: str

    @property
    def modelo(self) -> str:
        return os.environ.get(f"{self.nombre.upper()}_MODEL", self.modelo_default)

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.env_key)


# El orden es el de preferencia. Groq primero por tener el límite diario más alto.
PROVEEDORES: tuple[Proveedor, ...] = (
    # Ojo: los proveedores dan de baja modelos sin aviso. Groq retiró toda la
    # familia Llama 3.3 en agosto de 2026 y los pollers empezaron a comer 404.
    # Si esto vuelve a pasar, `python -m bot.llm_client` lista los modelos vivos.
    Proveedor(
        nombre="groq",
        env_key="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        modelo_default="openai/gpt-oss-120b",
    ),
    Proveedor(
        nombre="cerebras",
        env_key="CEREBRAS_API_KEY",
        base_url="https://api.cerebras.ai/v1",
        modelo_default="llama-3.3-70b",
    ),
)

_clientes: dict[str, OpenAI] = {}


def _get_cliente(p: Proveedor) -> OpenAI:
    if p.nombre not in _clientes:
        _clientes[p.nombre] = OpenAI(
            api_key=p.api_key, base_url=p.base_url, timeout=TIMEOUT_SEGUNDOS, max_retries=0
        )
    return _clientes[p.nombre]


def proveedores_configurados() -> list[Proveedor]:
    """Los proveedores que tienen API key seteada, en orden de preferencia."""
    return [p for p in PROVEEDORES if p.api_key]


def _es_transitorio(exc: Exception) -> bool:
    """
    True si el error se resuelve reintentando (con otro proveedor ahora, o con el
    mismo más tarde). Cuota agotada, red caída o servidor saturado entran acá.
    Un 400 por prompt inválido NO: eso no lo arregla el reintento.
    """
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return False


def _es_del_proveedor(exc: Exception) -> bool:
    """
    True si el problema es con ESTE proveedor, no con el pedido: modelo dado de
    baja (404), key inválida o sin permisos (401/403).

    Reintentar más tarde no lo arregla, pero otro proveedor sí puede responder,
    así que no cortamos la cadena. Si no queda ninguno, el error se propaga tal
    cual porque dice exactamente qué hay que ir a arreglar.
    """
    return isinstance(exc, APIStatusError) and exc.status_code in (401, 403, 404)


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _limpiar_json(texto: str) -> str:
    """Saca los bloques de código markdown que algunos modelos agregan igual."""
    return _FENCE_RE.sub("", texto).strip()


def generar_json(prompt: str, *, max_tokens: int = 1024) -> dict:
    """
    Pide una respuesta JSON al primer proveedor que responda y la devuelve parseada.

    Recorre la cadena de proveedores: si uno falla por causa transitoria, prueba
    el siguiente. Si todos fallan así, levanta `LLMUnavailable`.

    Levanta:
        LLMNoConfigurado: no hay ninguna API key seteada.
        LLMUnavailable:   todos los proveedores fallaron por causa transitoria,
                          o devolvieron algo que no es JSON válido.
        APIStatusError:   401/403/404 en todos los proveedores — configuración
                          rota (modelo dado de baja, key inválida). Se propaga
                          sin disfrazar porque hay que ir a arreglarlo a mano.
        Exception:        el resto de los errores no transitorios, tal cual.
    """
    disponibles = proveedores_configurados()
    if not disponibles:
        raise LLMNoConfigurado(
            f"Ninguna API key configurada. Seteá al menos una de: "
            f"{', '.join(p.env_key for p in PROVEEDORES)}"
        )

    ultimo_error: Exception | None = None
    error_config: Exception | None = None

    for p in disponibles:
        try:
            respuesta = _get_cliente(p).chat.completions.create(
                model=p.modelo,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=max_tokens,
            )
            contenido = respuesta.choices[0].message.content or ""
            datos = json.loads(_limpiar_json(contenido))
            logger.info("LLM: %s/%s respondió OK", p.nombre, p.modelo)
            return datos

        except json.JSONDecodeError as e:
            # JSON inválido pese a pedir json_object: lo tratamos como transitorio
            # y dejamos que otro proveedor (o el próximo ciclo) lo intente. Preferimos
            # reintentar antes que descartar un gasto real.
            logger.warning("LLM: %s devolvió JSON inválido: %s", p.nombre, contenido[:300])
            ultimo_error = e

        except Exception as e:
            if _es_del_proveedor(e):
                # Config rota de este proveedor. Guardamos el error para propagarlo
                # si nadie más responde: es accionable y no queremos disfrazarlo de
                # "reintentá más tarde", porque solo, nunca se va a arreglar.
                logger.error("LLM: %s mal configurado: %s", p.nombre, e)
                error_config = e
                continue
            if not _es_transitorio(e):
                logger.error("LLM: %s falló con error no transitorio: %s", p.nombre, e)
                raise
            logger.warning(
                "LLM: %s no disponible (%s), probando siguiente proveedor", p.nombre, e.__class__.__name__
            )
            ultimo_error = e

    if error_config is not None and ultimo_error is None:
        raise error_config

    raise LLMUnavailable(
        f"Ningún proveedor pudo responder ({len(disponibles)} intentados). "
        f"Último error: {ultimo_error or error_config}"
    ) from (ultimo_error or error_config)


# ──────────────────────────────────────────────
# Smoke test: python -m bot.llm_client
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Corriendo suelto no pasó por main.py, así que el .env no está cargado.
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    disponibles = proveedores_configurados()
    if not disponibles:
        print("✗ No hay ninguna API key configurada.")
        print(f"  Seteá al menos una de: {', '.join(p.env_key for p in PROVEEDORES)}")
        sys.exit(1)

    for p in PROVEEDORES:
        if not p.api_key:
            print(f"○ {p.nombre}: sin API key ({p.env_key} no seteada), se saltea")
            continue

        print(f"\n── {p.nombre} (modelo configurado: {p.modelo}) ──")
        try:
            modelos = sorted(m.id for m in _get_cliente(p).models.list().data)
            print(f"   modelos disponibles: {', '.join(modelos)}")
            if p.modelo not in modelos:
                print(f"   ⚠  '{p.modelo}' NO está en la lista. Seteá {p.nombre.upper()}_MODEL a uno de arriba.")
        except Exception as e:
            print(f"   ⚠  no pude listar modelos: {e}")

    print("\n── prueba de extracción end-to-end ──")
    try:
        datos = generar_json(
            'Devolvé SOLO este JSON, sin agregar nada: {"ok": true, "moneda": "ARS", "monto": 1234.56}'
        )
        print(f"✓ respuesta parseada: {datos}")
    except Exception as e:
        print(f"✗ falló: {e.__class__.__name__}: {e}")
        sys.exit(1)
