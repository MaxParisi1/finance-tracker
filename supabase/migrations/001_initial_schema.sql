-- ============================================================
-- 001 — Schema inicial
-- ============================================================

CREATE TABLE IF NOT EXISTS categorias (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre VARCHAR(100) UNIQUE NOT NULL,
  descripcion TEXT,
  color VARCHAR(7),
  icono VARCHAR(50),
  activa BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS gastos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fecha DATE NOT NULL,
  descripcion TEXT NOT NULL,
  monto_original NUMERIC(12, 2) NOT NULL,
  moneda VARCHAR(3) NOT NULL,
  monto_ars NUMERIC(12, 2),
  tipo_cambio NUMERIC(10, 4),
  tipo_cambio_tipo VARCHAR(10),
  categoria VARCHAR(100),
  subcategoria VARCHAR(100),
  medio_pago VARCHAR(50),
  cuotas INTEGER DEFAULT 1,
  cuota_actual INTEGER DEFAULT 1,
  es_recurrente BOOLEAN DEFAULT FALSE,
  comercio VARCHAR(200),
  notas TEXT,
  fuente VARCHAR(50),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos (fecha);
CREATE INDEX IF NOT EXISTS idx_gastos_categoria ON gastos (categoria);
CREATE INDEX IF NOT EXISTS idx_gastos_medio_pago ON gastos (medio_pago);
CREATE INDEX IF NOT EXISTS idx_gastos_moneda ON gastos (moneda);

CREATE TABLE IF NOT EXISTS gastos_recurrentes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  descripcion TEXT NOT NULL,
  monto_original NUMERIC(12, 2) NOT NULL,
  moneda VARCHAR(3) NOT NULL,
  categoria VARCHAR(100),
  medio_pago VARCHAR(50),
  frecuencia VARCHAR(20),
  dia_del_mes INTEGER,
  activo BOOLEAN DEFAULT TRUE,
  proximo_vencimiento DATE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tipos_cambio_historico (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fecha DATE NOT NULL,
  tipo VARCHAR(10) NOT NULL,
  valor NUMERIC(10, 4) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(fecha, tipo)
);

CREATE INDEX IF NOT EXISTS idx_tc_historico_fecha ON tipos_cambio_historico (fecha);

-- Seed de categorías iniciales
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
  ('Otros',                'Gastos que no encajan en otra categoría',          '#9E9E9E', 'category')
ON CONFLICT (nombre) DO NOTHING;
