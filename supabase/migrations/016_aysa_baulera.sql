-- ============================================================
-- 016 — Varias facturas por mail, y la baulera de AySA
--
-- El aviso de AySA del 20/10/2026 trajo dos facturas en la misma tabla: el
-- depto (cuenta 1929557, mensual) y la baulera (cuenta 1932903, U.C. 074), que
-- AySA factura aparte y por SEMESTRE adelantado ("Frecuencia: SEMESTRAL",
-- período 26/10/2026 al 26/04/2027). El bot leía solo la primera fila.
--
-- 1. La idempotencia del poller pasa de "un mail, una factura" a "un mail,
--    una factura por servicio".
-- 2. La baulera se da de alta como servicio propio, con su cuenta como
--    identificador y un recurrente semestral. Va aparte y no como segunda
--    cuenta de 'aysa' porque (servicio, vencimiento) es único, la guarda de
--    monto compararía contra el depto y en Registro tiene que ser su fila.
--
-- Idempotente: se puede correr dos veces sin duplicar nada.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Idempotencia por (mail, servicio)
-- ------------------------------------------------------------
DROP INDEX IF EXISTS idx_facturas_email_message_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_facturas_email_servicio
  ON facturas (email_message_id, servicio_id)
  WHERE email_message_id IS NOT NULL;

-- ------------------------------------------------------------
-- 2. Alta de la baulera
--
-- El recurrente copia categoría, medio de pago y materialización del de AySA:
-- se paga igual. Sin día fijo (como AySA): el vencimiento exacto lo trae cada
-- factura. proximo_vencimiento = fin del mes de la primera factura, el ancla
-- nominal que usa la web para los recurrentes sin día.
-- ------------------------------------------------------------
INSERT INTO gastos_recurrentes (
  descripcion, monto_original, moneda, categoria, medio_pago, frecuencia,
  dia_del_mes, activo, proximo_vencimiento, no_materializar
)
SELECT 'AySA Baulera', 19120.69, 'ARS', r.categoria, r.medio_pago, 'semestral',
       NULL, TRUE, DATE '2026-11-30', r.no_materializar
FROM gastos_recurrentes r
WHERE r.id = (SELECT recurrente_id FROM servicios WHERE slug = 'aysa')
  AND NOT EXISTS (
    SELECT 1 FROM gastos_recurrentes WHERE descripcion = 'AySA Baulera'
  );

INSERT INTO servicios (slug, nombre, recurrente_id)
SELECT 'aysa_baulera', 'AySA Baulera', r.id
FROM gastos_recurrentes r
WHERE r.descripcion = 'AySA Baulera'
ON CONFLICT (slug) DO NOTHING;

-- Ya normalizado, como lo deja _norm_id(): sin los ceros a la izquierda del mail.
INSERT INTO servicios_identificadores (servicio_id, tipo, valor)
SELECT id, 'cuenta', '1932903' FROM servicios WHERE slug = 'aysa_baulera'
ON CONFLICT (valor) DO NOTHING;

-- Verificación post-migración (tiene que dar una fila con las tres columnas):
--   SELECT s.slug, i.valor, r.descripcion, r.frecuencia, r.proximo_vencimiento
--   FROM servicios s
--   JOIN servicios_identificadores i ON i.servicio_id = s.id
--   JOIN gastos_recurrentes r ON r.id = s.recurrente_id
--   WHERE s.slug = 'aysa_baulera';
