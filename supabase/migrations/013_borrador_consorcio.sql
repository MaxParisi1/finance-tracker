-- ============================================================
-- 013 — Registro del borrador enviado al consorcio
--
-- Las expensas requieren un paso extra que ningún otro servicio tiene: mandarle
-- el comprobante a la administración. Sin dejar constancia, no hay forma de
-- saber de qué meses ya se hizo, y "registro total" quedaría incompleto.
--
-- Se guarda cuándo se GENERÓ el borrador, no cuándo se envió: el envío lo hace
-- el usuario desde su cliente de correo y el sistema no puede verificarlo.
-- ============================================================

ALTER TABLE facturas
  ADD COLUMN IF NOT EXISTS borrador_consorcio_at TIMESTAMPTZ;
