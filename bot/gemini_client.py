"""
Cliente Gemini centralizado con fallback de API keys.

Usa GOOGLE_API_KEY (free tier) como primaria.
Si falla por quota (429), reintenta con GOOGLE_API_KEY_PAID.
"""

import os
import logging

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_client_free: genai.Client | None = None
_client_paid: genai.Client | None = None


def _get_free_client() -> genai.Client:
    global _client_free
    if _client_free is None:
        _client_free = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _client_free


def _get_paid_client() -> genai.Client | None:
    global _client_paid
    paid_key = os.environ.get("GOOGLE_API_KEY_PAID")
    if not paid_key:
        return None
    if _client_paid is None:
        _client_paid = genai.Client(api_key=paid_key)
    return _client_paid


def get_client() -> genai.Client:
    """Devuelve el cliente free tier."""
    return _get_free_client()


def generate_with_fallback(model: str, **kwargs):
    """
    Llama a models.generate_content con fallback a la key paga si hay 429.

    Acepta los mismos kwargs que client.models.generate_content().
    """
    client = _get_free_client()
    try:
        return client.models.generate_content(model=model, **kwargs)
    except Exception as e:
        if _needs_paid_fallback(e):
            paid = _get_paid_client()
            if paid:
                logger.warning(f"Error {e.__class__.__name__} ({getattr(e, 'code', '?')}), usando API key paga")
                return paid.models.generate_content(model=model, **kwargs)
            logger.error("Fallback a key paga necesario pero no hay GOOGLE_API_KEY_PAID configurada")
        raise


def _needs_paid_fallback(exc: Exception) -> bool:
    """True para errores que se resuelven cambiando a la API key paga (quota o servidor saturado)."""
    if isinstance(exc, genai.errors.ClientError) and exc.code == 429:
        return True
    if isinstance(exc, genai.errors.ServerError) and exc.code == 503:
        return True
    return False


def create_chat_with_fallback(model: str, config, history, force_paid: bool = False):
    """
    Crea un chat de Gemini. Si force_paid=True, o el free tier da 429/503, usa la key paga.
    """
    if force_paid:
        paid = _get_paid_client()
        if paid:
            logger.warning("Usando API key paga (forzado)")
            return paid.chats.create(model=model, config=config, history=history)
        raise RuntimeError("Se requiere GOOGLE_API_KEY_PAID pero no está configurada")

    client = _get_free_client()
    try:
        return client.chats.create(model=model, config=config, history=history)
    except Exception as e:
        if _needs_paid_fallback(e):
            paid = _get_paid_client()
            if paid:
                logger.warning(f"Error {e.__class__.__name__} ({getattr(e, 'code', '?')}) al crear chat, usando API key paga")
                return paid.chats.create(model=model, config=config, history=history)
            logger.error("Fallback a key paga necesario pero no hay GOOGLE_API_KEY_PAID configurada")
        raise
