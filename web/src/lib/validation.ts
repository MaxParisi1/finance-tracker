import { z } from 'zod'

export const MEDIOS_PAGO = [
  'credito_ars',
  'credito_usd',
  'debito',
  'efectivo_ars',
  'efectivo_usd',
  'transferencia',
] as const

export const FRECUENCIAS = ['mensual', 'anual', 'semanal'] as const

export const updateGastoSchema = z.object({
  descripcion: z.string().min(1).max(300),
  monto: z.number().positive(),
  moneda: z.enum(['ARS', 'USD']),
  categoria: z.string().min(1),
  medio_pago: z.enum(MEDIOS_PAGO),
  fecha: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Fecha inválida (YYYY-MM-DD)'),
  notas: z.string().max(500).optional(),
})

export const upsertPresupuestoSchema = z.object({
  categoria: z.string().min(1),
  mes: z.number().int().min(1).max(12),
  anio: z.number().int().min(2020).max(2100),
  monto_limite: z.number().positive(),
})

export const recurrenteSchema = z.object({
  descripcion: z.string().min(1).max(300),
  monto_original: z.number().positive(),
  moneda: z.enum(['ARS', 'USD']),
  categoria: z.string().min(1),
  medio_pago: z.enum(MEDIOS_PAGO),
  frecuencia: z.enum(FRECUENCIAS),
  dia_del_mes: z.number().int().min(1).max(31),
  no_materializar: z.boolean().optional(),
})
