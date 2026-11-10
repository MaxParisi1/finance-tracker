-- Rollback de la 019. Solo hace falta si se quiere sacar todo rastro: con el
-- bot de vuelta en modo poller (RESUMENES_MODO=poll) los triggers no molestan.
DROP TRIGGER IF EXISTS avisar_resumen_nuevo        ON resumenes_tarjeta;
DROP TRIGGER IF EXISTS avisar_resumen_reprocesar   ON resumenes_tarjeta;
DROP TRIGGER IF EXISTS avisar_movimientos_a_cargar ON resumen_movimientos;
DROP FUNCTION IF EXISTS avisar_resumenes();
