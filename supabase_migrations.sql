-- ============================================================
-- finance-tracker: Migraciones incrementales
-- Ejecutar en el SQL Editor de Supabase (en orden)
-- ============================================================

-- ------------------------------------------------------------
-- MIGRACIÓN 1: Soft delete en gastos
-- ------------------------------------------------------------
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ DEFAULT NULL;

-- Índice parcial para queries eficientes (solo filas activas)
CREATE INDEX IF NOT EXISTS idx_gastos_not_deleted ON gastos (fecha) WHERE deleted_at IS NULL;

-- ------------------------------------------------------------
-- MIGRACIÓN 2: Historial de sesiones del bot de Telegram
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bot_sessions (
  chat_id BIGINT PRIMARY KEY,
  history JSONB NOT NULL DEFAULT '[]',
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- MIGRACIÓN 3: Presupuestos por categoría
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS presupuestos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  categoria VARCHAR(100) NOT NULL,
  mes INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
  anio INTEGER NOT NULL,
  monto_limite NUMERIC(12, 2) NOT NULL CHECK (monto_limite > 0),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(categoria, mes, anio)
);

CREATE INDEX IF NOT EXISTS idx_presupuestos_mes_anio ON presupuestos (mes, anio);
