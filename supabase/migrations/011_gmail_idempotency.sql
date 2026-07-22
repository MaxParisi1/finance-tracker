-- ============================================================
-- 011 — Idempotencia de gastos importados desde Gmail
-- Evita gastos duplicados si el proceso muere entre guardar_gasto()
-- y mark_as_read(): el email queda "unread" y se reprocesaría, pero el
-- índice único garantiza que cada email genera a lo sumo un gasto.
-- ============================================================

ALTER TABLE gastos ADD COLUMN IF NOT EXISTS email_message_id TEXT;

-- Índice único parcial: solo aplica a gastos que vinieron de un email.
-- Los gastos manuales / de tickets (email_message_id NULL) no se ven afectados.
CREATE UNIQUE INDEX IF NOT EXISTS idx_gastos_email_message_id
  ON gastos (email_message_id)
  WHERE email_message_id IS NOT NULL;
