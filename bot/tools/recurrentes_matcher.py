"""
Matching entre gastos de Gmail y gastos_recurrentes en 4 capas:
  1. Alias exacto    → auto-vincular (confianza 1.0)
  2. Fuzzy ≥ 85      → auto-vincular (confianza alta)
  3. Gemini ≥ 0.80   → auto-vincular (Gemini lo confirma)
  4. Gemini 0.50-0.79 → pedir confirmación al usuario vía Telegram

Filtros duros previos: moneda exacta, monto ±20%, fecha ±12 días del proximo_vencimiento.
"""

import calendar
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

from rapidfuzz import fuzz
from google.genai import types

from bot.db import queries
from bot.gemini_client import generate_with_fallback

logger = logging.getLogger(__name__)

FUZZY_AUTO = 85
FUZZY_GEMINI = 60
MONTO_TOL = 0.20
FECHA_WINDOW = 12  # días

# Confirmaciones pendientes de respuesta del usuario.
# key: "{gasto_id[:8]}:{rec_id[:8]}"  →  (gasto_id, rec_id, comercio_norm)
_pending: dict[str, tuple[str, str, str]] = {}


# ──────────────────────────────────────────────
# Tipos
# ──────────────────────────────────────────────

@dataclass
class CandidatoMatch:
    recurrente: dict
    confianza: float  # 0-1
    metodo: str       # 'alias' | 'fuzzy' | 'gemini' | 'usuario_pendiente'


# ──────────────────────────────────────────────
# Normalización
# ──────────────────────────────────────────────

def _normalizar(text: str) -> str:
    text = text.lower()
    text = re.sub(r'\.(com|net|org|ar|io)\b', '', text)
    text = re.sub(r'[*.\-_/\\]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ──────────────────────────────────────────────
# Filtros duros
# ──────────────────────────────────────────────

def _pasa_filtros_duros(gasto: dict, rec: dict) -> bool:
    mon_g = (gasto.get('moneda') or 'ARS').upper()
    mon_r = (rec.get('moneda') or 'ARS').upper()
    if mon_g != mon_r:
        return False

    try:
        mg = float(gasto.get('monto_original') or 0)
        mr = float(rec.get('monto_original') or 0)
        if mr > 0 and abs(mg - mr) / mr > MONTO_TOL:
            return False
    except (ValueError, ZeroDivisionError):
        pass

    prox = rec.get('proximo_vencimiento')
    if prox:
        try:
            dg = date.fromisoformat(str(gasto.get('fecha') or date.today()))
            dr = date.fromisoformat(str(prox))
            if abs((dg - dr).days) > FECHA_WINDOW:
                return False
        except ValueError:
            pass

    return True


# ──────────────────────────────────────────────
# Gemini arbiter
# ──────────────────────────────────────────────

def _score_gemini(gasto: dict, rec: dict) -> float:
    prompt = f"""¿Este pago corresponde al recurrente indicado? Respondé SOLO con JSON.

Pago recibido:
- Comercio: {gasto.get('comercio') or gasto.get('descripcion')}
- Monto: {gasto.get('monto_original')} {gasto.get('moneda')}
- Fecha: {gasto.get('fecha')}

Recurrente esperado:
- Descripción: {rec.get('descripcion')}
- Monto esperado: {rec.get('monto_original')} {rec.get('moneda')}
- Próximo vencimiento: {rec.get('proximo_vencimiento')}

{{"match": true, "confianza": 0.0-1.0, "razon": "..."}}"""

    try:
        resp = generate_with_fallback(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        data = json.loads(resp.text)
        return float(data.get('confianza', 0)) if data.get('match') else 0.0
    except Exception:
        logger.warning("Gemini falló al evaluar match recurrente")
        return 0.0


# ──────────────────────────────────────────────
# Motor de matching principal
# ──────────────────────────────────────────────

def encontrar_candidato_db(gasto: dict) -> CandidatoMatch | None:
    """
    Consulta DB y corre el pipeline de matching.
    Llamar con asyncio.to_thread desde código async.
    """
    recurrentes = queries.obtener_recurrentes_activos()
    if not recurrentes:
        return None

    aliases = queries.obtener_aliases_recurrentes()
    comercio = gasto.get('comercio') or gasto.get('descripcion') or ''
    comercio_norm = _normalizar(comercio)

    # Capa 1: alias exacto
    if comercio_norm in aliases:
        rec_id = aliases[comercio_norm]
        rec = next((r for r in recurrentes if str(r['id']) == rec_id), None)
        if rec and _pasa_filtros_duros(gasto, rec):
            return CandidatoMatch(recurrente=rec, confianza=1.0, metodo='alias')

    # Candidatos que pasan filtros duros
    candidatos = [r for r in recurrentes if _pasa_filtros_duros(gasto, r)]
    if not candidatos:
        return None

    # Capa 2: fuzzy
    scored = sorted(
        ((fuzz.ratio(comercio_norm, _normalizar(r.get('descripcion', ''))), r) for r in candidatos),
        reverse=True,
    )
    best_score, best_rec = scored[0]

    if best_score >= FUZZY_AUTO:
        return CandidatoMatch(recurrente=best_rec, confianza=best_score / 100, metodo='fuzzy')

    # Capas 3-4: Gemini sólo si hay candidato razonablemente cercano
    if best_score >= FUZZY_GEMINI:
        conf = _score_gemini(gasto, best_rec)
        if conf >= 0.80:
            return CandidatoMatch(recurrente=best_rec, confianza=conf, metodo='gemini')
        if conf >= 0.50:
            return CandidatoMatch(recurrente=best_rec, confianza=conf, metodo='usuario_pendiente')

    return None


# ──────────────────────────────────────────────
# Vinculación
# ──────────────────────────────────────────────

def confirmar_vinculacion(gasto_id: str, rec: dict, comercio: str, guardar_alias: bool, confirmado_usuario: bool = False) -> None:
    """Vincula el gasto al recurrente y avanza proximo_vencimiento."""
    queries.vincular_gasto_recurrente(gasto_id, rec['id'])
    queries.avanzar_proximo_vencimiento(rec['id'], rec.get('frecuencia', 'mensual'), rec['proximo_vencimiento'])
    if guardar_alias and comercio:
        queries.upsert_alias_recurrente(rec['id'], _normalizar(comercio), confirmado_por_usuario=confirmado_usuario)


# ──────────────────────────────────────────────
# Confirmación por Telegram
# ──────────────────────────────────────────────

def _pending_key(gasto_id: str, rec_id: str) -> str:
    return f"{gasto_id[:8]}:{rec_id[:8]}"


async def solicitar_confirmacion_telegram(bot, chat_id: int, gasto: dict, candidato: CandidatoMatch) -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    gasto_id = gasto['id']
    rec_id = candidato.recurrente['id']
    comercio = gasto.get('comercio') or gasto.get('descripcion') or ''
    key = _pending_key(gasto_id, rec_id)
    _pending[key] = (gasto_id, rec_id, comercio)

    comercio = gasto.get('comercio') or gasto.get('descripcion') or '?'
    monto = gasto.get('monto_original', 0)
    moneda_sym = 'USD ' if gasto.get('moneda') == 'USD' else '$'
    rec_desc = candidato.recurrente['descripcion']

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Sí, vincular", callback_data=f"mr:y:{key}"),
            InlineKeyboardButton("❌ No es este", callback_data=f"mr:n:{key}"),
        ],
        [InlineKeyboardButton("🔗 Sí, y recordar siempre", callback_data=f"mr:a:{key}")],
    ])

    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🔍 *¿Vincular pago a recurrente?*\n"
            f"• Pago: *{comercio}* · {moneda_sym}{monto:,.2f}\n"
            f"• Recurrente: _{rec_desc}_\n"
            f"• Confianza: {int(candidato.confianza * 100)}%"
        ),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def procesar_callback(query) -> str:
    """
    Procesa un CallbackQuery de confirmación de match.
    Retorna texto de respuesta para editar el mensaje original.
    """
    data = query.data  # "mr:{accion}:{key}"
    parts = data.split(':', 2)
    if len(parts) != 3 or parts[0] != 'mr':
        return "Acción desconocida."

    _, accion, key = parts
    ids = _pending.pop(key, None)
    if ids is None:
        return "Esta confirmación ya fue procesada o expiró."

    gasto_id, rec_id, comercio = ids

    if accion == 'n':
        return "Entendido, no se vinculó."

    rec = next(
        (r for r in queries.obtener_recurrentes_activos() if str(r['id']) == rec_id),
        None,
    )
    if rec is None:
        return "No encontré el recurrente, puede haber sido eliminado."

    guardar_alias = (accion == 'a')
    confirmar_vinculacion(gasto_id, rec, comercio=comercio, guardar_alias=guardar_alias, confirmado_usuario=guardar_alias)
    sufijo = " (alias guardado para próximas veces)" if guardar_alias else ""
    return f"✅ Vinculado a *{rec['descripcion']}*{sufijo}"
