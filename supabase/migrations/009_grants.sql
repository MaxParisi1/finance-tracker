-- ============================================================
-- 009 — Grants explícitos en schema public
-- Requerido por el cambio de Supabase (Oct 2026):
-- nuevas tablas no se exponen al Data API sin GRANT explícito.
-- service_role siempre tiene acceso completo (bypasea todo).
-- ============================================================

GRANT USAGE ON SCHEMA public TO authenticated, anon;

GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO authenticated;

-- anon solo lectura en tablas no sensibles (categorías)
GRANT SELECT ON categorias TO anon;

-- Asegurar que futuros objetos también hereden los permisos
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON TABLES TO authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON SEQUENCES TO authenticated;
