-- ============================================================
-- 017 — Conciliación de resúmenes de tarjeta
--
-- Desde el 24/07/2026 Payway dejó de avisar por mail los débitos automáticos
-- de la Visa, así que Mapfre, ACA, YouTube y los peajes no se registraban. El
-- resumen mensual es la única fuente completa: la web lo sube, el bot lo lee
-- (parser determinista, validado contra los totales del propio resumen) y lo
-- concilia contra los gastos; el usuario elige qué cargar.
--
-- Flujo:
--   web   → sube el PDF al bucket `resumenes` e inserta la fila 'pendiente'
--   bot   → la toma, la procesa y la deja 'procesado' (o 'error' con el motivo)
--   web   → muestra los movimientos; al cargar, crea los gastos y los vincula
-- ============================================================

-- ------------------------------------------------------------
-- tarjetas.cuenta: el resumen no imprime los últimos 4 dígitos de la tarjeta,
-- sino el número de cuenta. Es lo que identifica de qué tarjeta es.
-- ------------------------------------------------------------
ALTER TABLE tarjetas ADD COLUMN IF NOT EXISTS cuenta TEXT UNIQUE;

UPDATE tarjetas SET cuenta = '1077662388' WHERE sufijo = '1670' AND cuenta IS NULL;

-- La Mastercard nunca se dio de alta: sus gastos llegan por el poller genérico,
-- que escribe la tarjeta como texto ("BBVA Mastercard 3327").
INSERT INTO tarjetas (sufijo, nombre, tipo, red, pendiente_clasificacion, cuenta)
VALUES ('3327', 'BBVA Mastercard', 'credito', 'mastercard', FALSE, '1269406479')
ON CONFLICT (sufijo) DO UPDATE SET cuenta = EXCLUDED.cuenta
  WHERE tarjetas.cuenta IS NULL;

-- ------------------------------------------------------------
-- Un resumen subido. `sha256` hace que subir dos veces el mismo PDF no
-- duplique nada; (tarjeta_id, cierre) cubre el mismo resumen bajado dos veces.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resumenes_tarjeta (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sha256           TEXT NOT NULL UNIQUE,
  storage_path     TEXT NOT NULL,
  nombre_archivo   TEXT,
  estado           TEXT NOT NULL DEFAULT 'pendiente'
                   CHECK (estado IN ('pendiente', 'procesado', 'error')),
  error            TEXT,
  tarjeta_id       UUID REFERENCES tarjetas(id),
  cierre           DATE,
  cierre_anterior  DATE,
  vencimiento      DATE,
  saldo_actual     JSONB,
  -- Gastos de la tarjeta dentro del período que no aparecen en el resumen
  -- (un reverso, o algo que entra en el siguiente): [{id, fecha, comercio, monto, moneda}]
  sin_movimiento   JSONB NOT NULL DEFAULT '[]',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  procesado_at     TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS resumenes_tarjeta_por_cierre
  ON resumenes_tarjeta (tarjeta_id, cierre)
  WHERE tarjeta_id IS NOT NULL AND cierre IS NOT NULL;

-- ------------------------------------------------------------
-- Cada línea del resumen y qué se decidió con ella.
--   estado: coincide | falta | cuota_registrada | impuesto | percepcion
--           | reintegro | pago | cargado (el usuario lo cargó) | descartado
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resumen_movimientos (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  resumen_id          UUID NOT NULL REFERENCES resumenes_tarjeta(id) ON DELETE CASCADE,
  orden               INT NOT NULL,
  seccion             TEXT NOT NULL CHECK (seccion IN ('pago', 'consumo', 'impuesto')),
  fecha               DATE NOT NULL,
  descripcion         TEXT NOT NULL,
  cupon               TEXT,
  monto               NUMERIC(14, 2) NOT NULL,
  moneda              TEXT NOT NULL CHECK (moneda IN ('ARS', 'USD')),
  cuota_actual        INT,
  cuotas_total        INT,
  estado              TEXT NOT NULL,
  gasto_id            UUID REFERENCES gastos(id),
  -- Sugerencias para cargar un faltante; el usuario las puede cambiar.
  categoria_sugerida  TEXT,
  recurrente_id       UUID REFERENCES gastos_recurrentes(id),
  UNIQUE (resumen_id, orden)
);

-- Mismo criterio que la 010, 014 y 015: RLS activo y sin policies, solo
-- service_role (el bot y el servidor de la web) puede leer y escribir.
ALTER TABLE resumenes_tarjeta   ENABLE ROW LEVEL SECURITY;
ALTER TABLE resumen_movimientos ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- Bucket privado para los PDFs. Trae nombre, dirección y número de cuenta:
-- nada público, se accede solo con la service key.
-- ------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public)
VALUES ('resumenes', 'resumenes', FALSE)
ON CONFLICT (id) DO NOTHING;
