-- ============================================================
-- 004 — Presupuestos por categoría y mes
-- ============================================================

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
