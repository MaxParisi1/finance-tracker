-- ============================================================
-- 006 — Planes de cuota
-- ============================================================
-- Tabla para trackear cuotas existentes (hipoteca, créditos, etc.)
-- Separada de gastos.cuotas que maneja compras nuevas divididas en X pagos.

CREATE TABLE IF NOT EXISTS planes_cuota (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  descripcion          TEXT NOT NULL,
  comercio             VARCHAR(200),
  categoria            VARCHAR(100),
  medio_pago           VARCHAR(50) DEFAULT 'debito',

  -- Monto: fijo tiene valor, variable es NULL (varía cada mes)
  monto_cuota          NUMERIC(12, 2),
  moneda               VARCHAR(3) NOT NULL DEFAULT 'ARS',

  -- Progreso
  cuotas_total         INTEGER NOT NULL CHECK (cuotas_total >= 1),
  cuota_actual         INTEGER NOT NULL DEFAULT 1 CHECK (cuota_actual >= 1),

  -- Vencimiento
  dia_del_mes          INTEGER NOT NULL DEFAULT 1 CHECK (dia_del_mes BETWEEN 1 AND 31),
  proximo_vencimiento  DATE NOT NULL,

  -- Tipo: fijo (sin interés, se auto-registra) / variable (con interés, se registra manualmente)
  tipo                 VARCHAR(10) NOT NULL DEFAULT 'fijo' CHECK (tipo IN ('fijo', 'variable')),

  activo               BOOLEAN DEFAULT TRUE,
  created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_planes_cuota_activo    ON planes_cuota (activo);
CREATE INDEX IF NOT EXISTS idx_planes_cuota_vencimiento ON planes_cuota (proximo_vencimiento);
