-- ============================================================
-- RESET DE GASTOS — limpiar datos de prueba
-- Ejecutar en el SQL Editor de Supabase
-- ============================================================
-- IMPORTANTE: esto borra datos permanentemente.
-- Hacé un backup desde Supabase → Table Editor → Export si querés
-- guardar algo antes.
-- ============================================================

-- ── Opción A: borrar SOLO los gastos (mantiene todo lo demás) ──
-- Limpia gastos, presupuestos del mes y sesión del bot.
-- Mantiene: categorias, tipos_cambio_historico, gastos_recurrentes.

TRUNCATE TABLE gastos RESTART IDENTITY CASCADE;
TRUNCATE TABLE presupuestos RESTART IDENTITY CASCADE;
TRUNCATE TABLE bot_sessions RESTART IDENTITY CASCADE;


-- ── Opción B: borrar solo gastos de cierto período ──
-- (comentar Opción A y descomentar esto si preferís ser más selectivo)

-- DELETE FROM gastos
-- WHERE fecha BETWEEN '2025-01-01' AND '2025-12-31';


-- ── Opción C: borrar TODO (factory reset completo) ──
-- Borra absolutamente todo, incluidas categorías y tipo de cambio.

-- TRUNCATE TABLE gastos RESTART IDENTITY CASCADE;
-- TRUNCATE TABLE gastos_recurrentes RESTART IDENTITY CASCADE;
-- TRUNCATE TABLE presupuestos RESTART IDENTITY CASCADE;
-- TRUNCATE TABLE bot_sessions RESTART IDENTITY CASCADE;
-- TRUNCATE TABLE tipos_cambio_historico RESTART IDENTITY CASCADE;
-- TRUNCATE TABLE categorias RESTART IDENTITY CASCADE;


-- ── Verificación (ejecutar después para confirmar) ──
SELECT
  (SELECT COUNT(*) FROM gastos)               AS gastos,
  (SELECT COUNT(*) FROM gastos_recurrentes)   AS recurrentes,
  (SELECT COUNT(*) FROM presupuestos)         AS presupuestos,
  (SELECT COUNT(*) FROM bot_sessions)         AS bot_sessions,
  (SELECT COUNT(*) FROM categorias)           AS categorias;
