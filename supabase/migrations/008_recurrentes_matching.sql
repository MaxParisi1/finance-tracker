-- Vincula un gasto (de Gmail u otro origen) al recurrente que lo originó/matcheó
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS recurrente_id UUID REFERENCES gastos_recurrentes(id) ON DELETE SET NULL;

-- no_materializar: si es true, el recurrente no se materializa automáticamente
-- (se espera que llegue vía Gmail). Añadido aquí para completar el schema.
ALTER TABLE gastos_recurrentes ADD COLUMN IF NOT EXISTS no_materializar BOOLEAN DEFAULT FALSE;

-- Aliases aprendidos: mapeo comercio_normalizado → recurrente
-- Permite auto-matching exacto en futuros pagos del mismo comercio.
CREATE TABLE IF NOT EXISTS recurrentes_aliases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recurrente_id UUID NOT NULL REFERENCES gastos_recurrentes(id) ON DELETE CASCADE,
  comercio_normalizado TEXT NOT NULL UNIQUE,
  confirmado_por_usuario BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
