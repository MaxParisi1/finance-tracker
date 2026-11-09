-- ============================================================
-- 018 — Categoría "Impuestos y comisiones"
--
-- La conciliación del resumen de tarjeta carga los impuestos y cargos de cada
-- resumen (sellos, IVA sobre servicios del exterior, IIBB) en un solo gasto.
-- Con categoría propia se ve cuánto se va en eso por mes sin mezclarlo con
-- "Otros". La percepción RG 5617 no entra: se reintegra.
-- ============================================================

INSERT INTO categorias (nombre, descripcion, color, icono, activa)
SELECT 'Impuestos y comisiones',
       'Impuestos y cargos del resumen de tarjeta: sellos, IVA, IIBB, comisiones',
       '#78716C', 'receipt_long', TRUE
WHERE NOT EXISTS (SELECT 1 FROM categorias WHERE nombre = 'Impuestos y comisiones');
