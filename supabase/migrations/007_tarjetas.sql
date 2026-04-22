-- ============================================================
-- 007 — Tabla de tarjetas (mapeo sufijo → crédito/débito)
-- ============================================================

CREATE TABLE IF NOT EXISTS tarjetas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sufijo VARCHAR(4) UNIQUE NOT NULL,
  nombre VARCHAR(100),
  tipo VARCHAR(10) NOT NULL DEFAULT 'credito' CHECK (tipo IN ('credito', 'debito')),
  red VARCHAR(20) DEFAULT 'visa',
  pendiente_clasificacion BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tarjetas_sufijo ON tarjetas (sufijo);
