-- ============================================================
-- 014 — RLS en las tablas de la migración 012
--
-- La 012 creó servicios, servicios_identificadores y facturas sin habilitar
-- RLS. Como la 009 dejó ALTER DEFAULT PRIVILEGES con GRANT ALL para
-- `authenticated`, las tres quedaron legibles y escribibles vía PostgREST por
-- cualquier JWT autenticado — incluida servicios_identificadores, que guarda
-- CBU, CUIT y números de cuenta.
--
-- Mismo criterio que la 010: RLS activo y sin policies = acceso denegado para
-- anon/authenticated. service_role bypasea RLS, así que ni el bot ni la web se
-- ven afectados (ambos usan la service role key del lado del servidor).
-- ============================================================

ALTER TABLE servicios                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE servicios_identificadores ENABLE ROW LEVEL SECURITY;
ALTER TABLE facturas                  ENABLE ROW LEVEL SECURITY;

-- Verificación: las tres deben quedar en true.
--   SELECT tablename, rowsecurity FROM pg_tables
--   WHERE schemaname = 'public'
--     AND tablename IN ('servicios', 'servicios_identificadores', 'facturas');
