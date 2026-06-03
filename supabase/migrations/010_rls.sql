-- ============================================================
-- 010 — Habilitar Row Level Security en todas las tablas
-- Con RLS activo y sin policies: acceso denegado para anon/authenticated.
-- service_role bypasea RLS, así que la app no se ve afectada.
-- Esto silencia los errores del Security Advisor de Supabase y
-- cierra el acceso directo via PostgREST con la anon key.
-- ============================================================

ALTER TABLE categorias              ENABLE ROW LEVEL SECURITY;
ALTER TABLE gastos                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE gastos_recurrentes      ENABLE ROW LEVEL SECURITY;
ALTER TABLE tipos_cambio_historico  ENABLE ROW LEVEL SECURITY;
ALTER TABLE bot_sessions            ENABLE ROW LEVEL SECURITY;
ALTER TABLE presupuestos            ENABLE ROW LEVEL SECURITY;
ALTER TABLE archivos_drive          ENABLE ROW LEVEL SECURITY;
ALTER TABLE planes_cuota            ENABLE ROW LEVEL SECURITY;
ALTER TABLE tarjetas                ENABLE ROW LEVEL SECURITY;
ALTER TABLE recurrentes_aliases     ENABLE ROW LEVEL SECURITY;

-- Política permisiva para categorías (datos de referencia, no sensibles)
CREATE POLICY "categorias_public_read"
  ON categorias FOR SELECT
  TO anon, authenticated
  USING (true);
