-- ============================================================
-- 002 — Soft delete en gastos
-- ============================================================

ALTER TABLE gastos ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ DEFAULT NULL;

-- Índice parcial: solo filas activas (no eliminadas)
CREATE INDEX IF NOT EXISTS idx_gastos_not_deleted ON gastos (fecha) WHERE deleted_at IS NULL;
