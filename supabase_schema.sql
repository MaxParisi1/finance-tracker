-- ============================================================
-- finance-tracker: Schema completo de Supabase
-- Ejecutar en el SQL Editor de Supabase (en orden)
-- ============================================================

-- ------------------------------------------------------------
-- TABLA: categorias
-- ------------------------------------------------------------
CREATE TABLE categorias (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre VARCHAR(100) UNIQUE NOT NULL,
  descripcion TEXT,
  color VARCHAR(7),         -- hex para la UI, ej: '#FF5733'
  icono VARCHAR(50),
  activa BOOLEAN DEFAULT TRUE
);

-- ------------------------------------------------------------
-- TABLA: gastos
-- ------------------------------------------------------------
CREATE TABLE gastos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fecha DATE NOT NULL,
  descripcion TEXT NOT NULL,
  monto_original NUMERIC(12, 2) NOT NULL,
  moneda VARCHAR(3) NOT NULL,               -- 'ARS' o 'USD'
  monto_ars NUMERIC(12, 2),                 -- convertido al TC del momento
  tipo_cambio NUMERIC(10, 4),               -- TC usado en la conversión
  tipo_cambio_tipo VARCHAR(10),             -- 'oficial', 'blue', 'mep'
  categoria VARCHAR(100),                   -- asignada por LLM, ajustable
  subcategoria VARCHAR(100),
  medio_pago VARCHAR(50),
  -- valores: 'credito_ars', 'credito_usd', 'debito',
  --          'efectivo_ars', 'efectivo_usd', 'transferencia'
  cuotas INTEGER DEFAULT 1,
  cuota_actual INTEGER DEFAULT 1,
  es_recurrente BOOLEAN DEFAULT FALSE,
  comercio VARCHAR(200),
  notas TEXT,
  fuente VARCHAR(50),
  -- valores: 'telegram_texto', 'telegram_foto', 'telegram_audio',
  --          'pdf_bbva', 'web_manual'
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices útiles para las consultas más frecuentes
CREATE INDEX idx_gastos_fecha ON gastos (fecha);
CREATE INDEX idx_gastos_categoria ON gastos (categoria);
CREATE INDEX idx_gastos_medio_pago ON gastos (medio_pago);
CREATE INDEX idx_gastos_moneda ON gastos (moneda);

-- ------------------------------------------------------------
-- TABLA: gastos_recurrentes
-- ------------------------------------------------------------
CREATE TABLE gastos_recurrentes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  descripcion TEXT NOT NULL,
  monto_original NUMERIC(12, 2) NOT NULL,
  moneda VARCHAR(3) NOT NULL,
  categoria VARCHAR(100),
  medio_pago VARCHAR(50),
  frecuencia VARCHAR(20),   -- 'mensual', 'anual', 'semanal'
  dia_del_mes INTEGER,
  activo BOOLEAN DEFAULT TRUE,
  proximo_vencimiento DATE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- TABLA: tipos_cambio_historico
-- ------------------------------------------------------------
CREATE TABLE tipos_cambio_historico (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fecha DATE NOT NULL,
  tipo VARCHAR(10) NOT NULL,    -- 'oficial', 'blue', 'mep'
  valor NUMERIC(10, 4) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(fecha, tipo)
);

CREATE INDEX idx_tc_historico_fecha ON tipos_cambio_historico (fecha);

-- ------------------------------------------------------------
-- SEED: categorias iniciales
-- ------------------------------------------------------------
INSERT INTO categorias (nombre, descripcion, color, icono) VALUES
  ('Alimentación',         'Supermercado, almacén, verdulería',                '#4CAF50', 'shopping_cart'),
  ('Restaurantes y cafés', 'Comidas fuera de casa, delivery, cafeterías',      '#FF9800', 'restaurant'),
  ('Transporte',           'Nafta, peajes, Uber, SUBE, estacionamiento',       '#2196F3', 'directions_car'),
  ('Salud',                'Farmacia, médicos, obra social, gimnasio',         '#F44336', 'local_hospital'),
  ('Entretenimiento',      'Streaming, cine, bares, eventos',                  '#9C27B0', 'movie'),
  ('Ropa e indumentaria',  'Ropa, calzado, accesorios de vestimenta',          '#E91E63', 'checkroom'),
  ('Hogar',                'Expensas, servicios, mantenimiento, muebles',      '#795548', 'home'),
  ('Tecnología',           'Suscripciones digitales, equipos, accesorios',     '#607D8B', 'devices'),
  ('Educación',            'Cursos, libros, materiales educativos',            '#009688', 'school'),
  ('Viajes',               'Vuelos, hoteles, turismo',                         '#00BCD4', 'flight'),
  ('Otros',                'Gastos que no encajan en otra categoría',          '#9E9E9E', 'category');
