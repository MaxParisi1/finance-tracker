-- ============================================================
-- 012 — Facturas de servicios fijos
--
-- Modela la FACTURA como entidad propia, independiente del pago. Hasta ahora
-- los PDFs colgaban de `gastos` (archivos_drive.gasto_id), así que una factura
-- recibida y todavía impaga no tenía dónde vivir: por eso el archivo quedaba
-- incompleto.
--
-- El matching NUNCA usa nombre ni dirección (los proveedores discrepan: Gallo
-- 1636 / 1648 / 1650 para el mismo edificio, y Edenor factura a nombre de un
-- tercero). Siempre por identificador numérico.
-- ============================================================

-- ------------------------------------------------------------
-- servicios: un servicio fijo, atado a un recurrente existente
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS servicios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug VARCHAR(50) UNIQUE NOT NULL,          -- 'edenor', 'aysa', 'consorcio_gallo', ...
  nombre VARCHAR(100) NOT NULL,              -- solo para mostrar, nunca para matchear
  recurrente_id UUID REFERENCES gastos_recurrentes(id) ON DELETE SET NULL,
  unidad_funcional VARCHAR(20),              -- expensas: qué fila del PDF leer
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- servicios_identificadores: las claves de ruteo
--
-- UNIQUE(valor) global: un identificador no puede apuntar a dos servicios. Es
-- lo que garantiza que rutear un PDF suelto sea determinístico y no ambiguo.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS servicios_identificadores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  servicio_id UUID NOT NULL REFERENCES servicios(id) ON DELETE CASCADE,
  tipo VARCHAR(30) NOT NULL,                 -- 'cuenta','cliente','referente','cbu','cuit'
  valor TEXT NOT NULL UNIQUE,                -- YA NORMALIZADO (sin espacios/puntos/ceros a izq.)
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_serv_ident_servicio ON servicios_identificadores (servicio_id);

-- ------------------------------------------------------------
-- facturas
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS facturas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  servicio_id UUID NOT NULL REFERENCES servicios(id) ON DELETE CASCADE,
  monto NUMERIC(12, 2) NOT NULL CHECK (monto >= 0),
  moneda VARCHAR(3) NOT NULL DEFAULT 'ARS',
  vencimiento DATE NOT NULL,
  periodo_desde DATE,
  periodo_hasta DATE,
  nro_factura TEXT,                          -- AySA lo trae; sirve de join con el PDF
  email_message_id TEXT,                     -- idempotencia con el poller
  gasto_id UUID REFERENCES gastos(id) ON DELETE SET NULL,  -- el pago que la saldó
  estado VARCHAR(20) NOT NULL DEFAULT 'pendiente'
    CHECK (estado IN ('pendiente', 'pagada', 'anulada')),
  fecha_pago DATE,
  created_at TIMESTAMPTZ DEFAULT NOW(),

  -- Una factura pagada tiene que tener con qué haberse pagado.
  CONSTRAINT factura_pagada_tiene_gasto
    CHECK (estado <> 'pagada' OR gasto_id IS NOT NULL)
);

-- Dos facturas del mismo servicio con el mismo vencimiento son un duplicado.
-- Se elige vencimiento y no mes calendario para no bloquear una refacturación
-- legítima dentro del mismo mes.
CREATE UNIQUE INDEX IF NOT EXISTS idx_facturas_servicio_vto
  ON facturas (servicio_id, vencimiento);

-- Un mail genera a lo sumo una factura, aunque el proceso muera entre el insert
-- y el mark_as_read (mismo patrón que gastos.email_message_id en la 011).
CREATE UNIQUE INDEX IF NOT EXISTS idx_facturas_email_message_id
  ON facturas (email_message_id)
  WHERE email_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_facturas_estado_vto ON facturas (estado, vencimiento);
CREATE INDEX IF NOT EXISTS idx_facturas_gasto ON facturas (gasto_id);

-- ------------------------------------------------------------
-- archivos_drive: permitir colgar un PDF de la factura ANTES de que exista el
-- gasto. Este era el gap estructural que dejaba facturas sin archivar.
-- ------------------------------------------------------------
ALTER TABLE archivos_drive
  ADD COLUMN IF NOT EXISTS factura_id UUID REFERENCES facturas(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_archivos_factura ON archivos_drive (factura_id);

-- ------------------------------------------------------------
-- RLS: mismo criterio que la 010 — activo y sin policies, así que solo
-- service_role (server-side) puede leer y escribir. Sin esto, el ALTER DEFAULT
-- PRIVILEGES de la 009 dejaría estas tablas abiertas vía PostgREST.
-- ------------------------------------------------------------
ALTER TABLE servicios                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE servicios_identificadores ENABLE ROW LEVEL SECURITY;
ALTER TABLE facturas                  ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- SEED de servicios
--
-- El vínculo con gastos_recurrentes se resuelve UNA VEZ acá por nombre (es un
-- bootstrap, no matching en runtime). Verificar después con la query del final:
-- si algún recurrente_id quedó NULL, ajustarlo a mano.
-- ------------------------------------------------------------
INSERT INTO servicios (slug, nombre, unidad_funcional, recurrente_id)
SELECT s.slug, s.nombre, s.uf, r.id
FROM (VALUES
  ('edenor',          'Edenor',          NULL),
  ('metrogas',        'Metrogas',        NULL),
  ('aysa',            'AySA',            NULL),
  ('personal',        'Personal',        NULL),
  ('consorcio_gallo', 'Consorcio Gallo', '255')
) AS s(slug, nombre, uf)
LEFT JOIN gastos_recurrentes r
  ON lower(trim(r.descripcion)) = lower(s.nombre) AND r.activo
ON CONFLICT (slug) DO NOTHING;

-- Identificadores, ya normalizados (sin espacios, puntos, guiones ni ceros a la
-- izquierda) para que coincidan con _norm_id() del parser.
INSERT INTO servicios_identificadores (servicio_id, tipo, valor)
SELECT sv.id, i.tipo, i.valor
FROM (VALUES
  ('edenor',          'cuenta',    '5255064586'),
  ('metrogas',        'cliente',   '40000507673'),
  ('aysa',            'cuenta',    '1929557'),
  ('personal',        'referente', '8100682932410002'),
  ('consorcio_gallo', 'cbu',       '70306020000004521499'),
  ('consorcio_gallo', 'cuit',      '30553713605')
) AS i(slug, tipo, valor)
JOIN servicios sv ON sv.slug = i.slug
ON CONFLICT (valor) DO NOTHING;

-- Verificación post-migración:
--   SELECT s.slug, s.nombre, s.recurrente_id, r.descripcion
--   FROM servicios s LEFT JOIN gastos_recurrentes r ON r.id = s.recurrente_id;
-- Todo recurrente_id en NULL hay que completarlo a mano.
