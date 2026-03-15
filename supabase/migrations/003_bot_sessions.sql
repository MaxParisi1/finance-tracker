-- ============================================================
-- 003 — Historial de sesiones del bot de Telegram
-- ============================================================

CREATE TABLE IF NOT EXISTS bot_sessions (
  chat_id BIGINT PRIMARY KEY,
  history JSONB NOT NULL DEFAULT '[]',
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
