-- ============================================================
-- 015 — Estado persistente del bot
--
-- El bot guardaba en memoria cosas que tienen que sobrevivir a un reinicio: la
-- marca de "ya mandé el recordatorio de hoy" (cada deploy después de las 9 lo
-- reenviaba) y qué mails quedaron sin procesar. Esta tabla clave/valor es donde
-- viven ahora. La web la lee para armar la bandeja "Requiere tu atención".
--
-- Claves en uso:
--   recordatorio_diario   {"fecha": "YYYY-MM-DD"}
--   poller:<etiqueta>     {"ok": bool, "atascados": [{"id","asunto","motivo"}]}
-- ============================================================

CREATE TABLE IF NOT EXISTS bot_estado (
  clave TEXT PRIMARY KEY,
  valor JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Mismo criterio que la 010 y la 014: RLS activo y sin policies, solo
-- service_role (el bot y el servidor de la web) puede leer y escribir.
ALTER TABLE bot_estado ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- gastos.tarjeta: el poller la escribe desde hace meses pero se había agregado
-- a mano en Supabase y no figuraba en ninguna migración. En producción este
-- ALTER no hace nada; está para que el esquema se pueda reconstruir desde cero.
-- ------------------------------------------------------------
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS tarjeta TEXT;
