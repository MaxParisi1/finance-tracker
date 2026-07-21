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
FUZZY_GEMINI = 55       # umbral para dejar que Gemini arbitre (antes 60)
MONTO_TOL = 0.20        # variación "cómoda"; dentro de esto no se penaliza
MONTO_TOL_HARD = 0.60   # rechazo duro solo si el monto difiere muchísimo
FECHA_WINDOW = 25       # días; ventana holgada para cadencias irregulares (antes 12)

# Confirmaciones pendientes de respuesta del usuario.
# key: "{gasto_id[:8]}:{rec_id[:8]}"  →  (gasto_id, rec_id, comercio, monto, fecha)
_pending: dict[str, tuple[str, str, str, float, str | None]] = {}


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

def _motivo_rechazo(gasto: dict, rec: dict, *, es_alias: bool = False) -> str | None:
    """
    Devuelve None si el recurrente es candidato viable, o un string con el
    motivo del descarte (para logging/observabilidad).

    Los alias aprendidos solo exigen coincidencia de moneda: se confía en el
    aprendizaje previo y se ignoran las variaciones de monto/fecha.
    """
    mon_g = (gasto.get('moneda') or 'ARS').upper()
    mon_r = (rec.get('moneda') or 'ARS').upper()
    if mon_g != mon_r:
        return f"moneda {mon_g}!={mon_r}"

    if es_alias:
        return None

    try:
        mg = float(gasto.get('monto_original') or 0)
        mr = float(rec.get('monto_original') or 0)
        if mr > 0 and abs(mg - mr) / mr > MONTO_TOL_HARD:
            return f"monto {mg} vs esperado {mr} (>{int(MONTO_TOL_HARD * 100)}%)"
    except (ValueError, ZeroDivisionError):
        pass

    prox = rec.get('proximo_vencimiento')
    if prox:
        try:
            dg = date.fromisoformat(str(gasto.get('fecha') or date.today()))
            dr = date.fromisoformat(str(prox))
            if abs((dg - dr).days) > FECHA_WINDOW:
                return f"fecha {dg} fuera de ±{FECHA_WINDOW}d de {dr}"
        except ValueError:
            pass

    return None


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
        logger.info("Match recurrente: no hay recurrentes activos")
        return None

    aliases = queries.obtener_aliases_recurrentes()
    comercio = gasto.get('comercio') or gasto.get('descripcion') or ''
    comercio_norm = _normalizar(comercio)

    logger.info(
        "Match recurrente: comercio=%r norm=%r monto=%s %s fecha=%s | %d activos",
        comercio, comercio_norm, gasto.get('monto_original'),
        gasto.get('moneda'), gasto.get('fecha'), len(recurrentes),
    )

    # Capa 1: alias exacto (bypass de monto/fecha; solo exige moneda)
    if comercio_norm in aliases:
        rec_id = aliases[comercio_norm]
        rec = next((r for r in recurrentes if str(r['id']) == rec_id), None)
        if rec is None:
            logger.info("  alias '%s' apunta a recurrente %s inactivo/eliminado", comercio_norm, rec_id)
        else:
            motivo = _motivo_rechazo(gasto, rec, es_alias=True)
            if motivo is None:
                logger.info("  → alias exacto → recurrente %s (%s)", rec_id, rec.get('descripcion'))
                return CandidatoMatch(recurrente=rec, confianza=1.0, metodo='alias')
            logger.info("  alias '%s' descartado: %s", comercio_norm, motivo)

    # Candidatos que pasan filtros duros (logueando cada descarte)
    candidatos: list[dict] = []
    for r in recurrentes:
        motivo = _motivo_rechazo(gasto, r)
        if motivo is None:
            candidatos.append(r)
        else:
            logger.debug("  descartado %r: %s", r.get('descripcion'), motivo)
    if not candidatos:
        logger.info("  → sin candidatos tras filtros duros")
        return None

    # Alias conocidos por recurrente, para enriquecer el fuzzy con lo aprendido
    aliases_por_rec: dict[str, list[str]] = {}
    for alias_norm, rid in aliases.items():
        aliases_por_rec.setdefault(str(rid), []).append(alias_norm)

    def _mejor_score(r: dict) -> int:
        objetivos = [_normalizar(r.get('descripcion', ''))]
        objetivos += aliases_por_rec.get(str(r['id']), [])
        objetivos = [o for o in objetivos if o]
        if not objetivos:
            return 0
        return max(
            max(
                fuzz.ratio(comercio_norm, o),
                fuzz.token_set_ratio(comercio_norm, o),
                fuzz.partial_ratio(comercio_norm, o),
            )
            for o in objetivos
        )

    # Capa 2: fuzzy (key= evita comparar dicts en empates de score)
    scored = sorted(((_mejor_score(r), r) for r in candidatos), key=lambda t: t[0], reverse=True)
    best_score, best_rec = scored[0]
    logger.info("  mejor fuzzy=%d → %r", best_score, best_rec.get('descripcion'))

    if best_score >= FUZZY_AUTO:
        logger.info("  → auto-vinculado por fuzzy (score=%d)", best_score)
        return CandidatoMatch(recurrente=best_rec, confianza=best_score / 100, metodo='fuzzy')

    # Capas 3-4: Gemini solo si hay candidato razonablemente cercano
    if best_score >= FUZZY_GEMINI:
        conf = _score_gemini(gasto, best_rec)
        logger.info("  Gemini confianza=%.2f", conf)
        if conf >= 0.80:
            return CandidatoMatch(recurrente=best_rec, confianza=conf, metodo='gemini')
        if conf >= 0.50:
            return CandidatoMatch(recurrente=best_rec, confianza=conf, metodo='usuario_pendiente')

    logger.info("  → sin match (mejor score=%d < %d)", best_score, FUZZY_GEMINI)
    return None


# ──────────────────────────────────────────────
# Vinculación
# ──────────────────────────────────────────────

def confirmar_vinculacion(
    gasto_id: str,
    rec: dict,
    comercio: str,
    guardar_alias: bool,
    confirmado_usuario: bool = False,
    nuevo_monto: float | None = None,
    fecha_pago: str | None = None,
) -> None:
    """
    Vincula el gasto al recurrente, actualiza su monto esperado al último
    observado y avanza proximo_vencimiento (anclado a la fecha del pago).
    """
    queries.vincular_gasto_recurrente(gasto_id, rec['id'])

    if nuevo_monto is not None:
        try:
            queries.actualizar_monto_recurrente(rec['id'], float(nuevo_monto))
        except (ValueError, TypeError):
            logger.warning("nuevo_monto inválido (%r), no se actualizó el recurrente %s", nuevo_monto, rec['id'])

    if rec.get('proximo_vencimiento'):
        queries.avanzar_proximo_vencimiento(
            rec['id'], rec.get('frecuencia', 'mensual'), rec['proximo_vencimiento'], fecha_pago=fecha_pago
        )

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
    _pending[key] = (gasto_id, rec_id, comercio, gasto.get('monto_original', 0), gasto.get('fecha'))

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

    gasto_id, rec_id, comercio, monto, fecha = ids

    if accion == 'n':
        return "Entendido, no se vinculó."

    rec = next(
        (r for r in queries.obtener_recurrentes_activos() if str(r['id']) == rec_id),
        None,
    )
    if rec is None:
        return "No encontré el recurrente, puede haber sido eliminado."

    guardar_alias = (accion == 'a')
    confirmar_vinculacion(
        gasto_id, rec, comercio=comercio, guardar_alias=guardar_alias,
        confirmado_usuario=guardar_alias, nuevo_monto=monto, fecha_pago=fecha,
    )
    sufijo = " (alias guardado para próximas veces)" if guardar_alias else ""
    return f"✅ Vinculado a *{rec['descripcion']}*{sufijo}"
