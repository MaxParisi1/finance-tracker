-- ============================================================
-- 019 — Aviso al bot cuando hay trabajo de resúmenes (LISTEN/NOTIFY)
--
-- Hasta acá el bot preguntaba cada 10 segundos si había un resumen pendiente o
-- movimientos para cargar: ~17.000 consultas por día para algo que pasa una vez
-- por mes, y en la instancia Free eso se notó en el saldo de Disk IO.
--
-- Ahora la base avisa por el canal `resumenes` cuando aparece trabajo, y el bot
-- (que escucha con LISTEN) procesa en el momento. El aviso es solo un
-- despertador: no lleva datos y el bot vuelve a leer las tablas como siempre.
-- Si el bot no está escuchando (reinicio, conexión caída), el aviso se pierde
-- y lo levanta el barrido periódico del bot.
--
-- pg_notify es transaccional: llega recién cuando la escritura se confirma, y
-- varios avisos iguales en la misma transacción se juntan en uno.
--
-- Triggers por sentencia con tabla de transición: un UPDATE de muchas filas
-- avisa una vez, y solo si alguna fila quedó en el estado que le interesa al
-- bot. Así las escrituras del propio bot ('procesado', 'cargado') no lo
-- vuelven a despertar.
--
-- Rollback: ver 019_aviso_resumenes.down.sql. Sin listener, estos triggers no
-- cuestan nada; se pueden dejar aunque se vuelva al poller.
-- ============================================================

CREATE OR REPLACE FUNCTION avisar_resumenes() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME = 'resumenes_tarjeta' THEN
    IF EXISTS (SELECT 1 FROM nuevas WHERE estado = 'pendiente') THEN
      PERFORM pg_notify('resumenes', 'resumen');
    END IF;
  ELSE
    IF EXISTS (SELECT 1 FROM nuevas WHERE estado = 'a_cargar') THEN
      PERFORM pg_notify('resumenes', 'movimientos');
    END IF;
  END IF;
  RETURN NULL;
END;
$$;

-- La web sube un resumen nuevo.
DROP TRIGGER IF EXISTS avisar_resumen_nuevo ON resumenes_tarjeta;
CREATE TRIGGER avisar_resumen_nuevo
  AFTER INSERT ON resumenes_tarjeta
  REFERENCING NEW TABLE AS nuevas
  FOR EACH STATEMENT EXECUTE FUNCTION avisar_resumenes();

-- La web manda a reprocesar uno que falló (vuelve a 'pendiente').
DROP TRIGGER IF EXISTS avisar_resumen_reprocesar ON resumenes_tarjeta;
CREATE TRIGGER avisar_resumen_reprocesar
  AFTER UPDATE ON resumenes_tarjeta
  REFERENCING NEW TABLE AS nuevas
  FOR EACH STATEMENT EXECUTE FUNCTION avisar_resumenes();

-- La web marca movimientos para cargar.
DROP TRIGGER IF EXISTS avisar_movimientos_a_cargar ON resumen_movimientos;
CREATE TRIGGER avisar_movimientos_a_cargar
  AFTER UPDATE ON resumen_movimientos
  REFERENCING NEW TABLE AS nuevas
  FOR EACH STATEMENT EXECUTE FUNCTION avisar_resumenes();
