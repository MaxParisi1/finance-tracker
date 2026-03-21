-- Tabla para almacenar metadata de archivos subidos a Google Drive
-- Cada archivo puede estar vinculado a un gasto (o no)
-- Un gasto puede tener múltiples archivos (facturas + comprobantes de pago)

CREATE TABLE archivos_drive (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  gasto_id UUID REFERENCES gastos(id) ON DELETE SET NULL,
  tipo VARCHAR(50) NOT NULL,                    -- 'factura', 'comprobante', 'ticket', 'recibo', 'resumen'
  comercio VARCHAR(200),                        -- Nombre del emisor normalizado
  fecha DATE NOT NULL,                          -- Fecha extraída del documento
  categoria VARCHAR(100),                       -- Para facilitar búsqueda
  monto NUMERIC(12, 2),                         -- Si se puede extraer
  moneda VARCHAR(3),                            -- 'ARS', 'USD', null
  drive_file_id VARCHAR(200) NOT NULL UNIQUE,   -- ID del archivo en Drive
  drive_file_name VARCHAR(500) NOT NULL,        -- Nombre del archivo con extensión
  drive_web_view_link TEXT,                     -- URL para abrir en navegador
  drive_folder_path TEXT,                       -- Ruta lógica: Comercio/Año/Mes
  mime_type VARCHAR(100),                       -- application/pdf, image/jpeg, etc.
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_archivos_comercio ON archivos_drive(comercio);
CREATE INDEX idx_archivos_fecha ON archivos_drive(fecha);
CREATE INDEX idx_archivos_categoria ON archivos_drive(categoria);
CREATE INDEX idx_archivos_gasto ON archivos_drive(gasto_id);
