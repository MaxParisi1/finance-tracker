'use server'

import { revalidatePath } from 'next/cache'
import { getSupabaseServer } from '@/lib/supabase'
import { getLatestTipoCambio } from '@/lib/queries'
import { updateGastoSchema } from '@/lib/validation'

export async function updateGastoAction(
  id: string,
  fields: {
    descripcion: string
    monto: number
    moneda: string
    categoria: string
    medio_pago: string
    fecha: string
    notas?: string
  },
) {
  const parsed = updateGastoSchema.safeParse(fields)
  if (!parsed.success) throw new Error(parsed.error.errors[0].message)

  const supabase = getSupabaseServer()
  const monedaUpper = fields.moneda.toUpperCase()

  let monto_ars = fields.monto
  let tipo_cambio = 1.0
  let tipo_cambio_tipo = 'n/a'

  if (monedaUpper === 'USD') {
    const tc = await getLatestTipoCambio('blue')
    if (tc) {
      monto_ars = fields.monto * tc
      tipo_cambio = tc
      tipo_cambio_tipo = 'blue'
    }
  }

  const { error } = await supabase
    .from('gastos')
    .update({
      descripcion: fields.descripcion,
      monto_original: fields.monto,
      moneda: monedaUpper,
      monto_ars: Math.round(monto_ars),
      tipo_cambio,
      tipo_cambio_tipo,
      categoria: fields.categoria,
      medio_pago: fields.medio_pago,
      fecha: fields.fecha,
      notas: fields.notas ?? null,
    })
    .eq('id', id)

  if (error) throw new Error(error.message)
  revalidatePath('/gastos')
  revalidatePath('/dashboard')
}

export async function deleteGastoAction(id: string) {
  const supabase = getSupabaseServer()
  const { error } = await supabase
    .from('gastos')
    .update({ deleted_at: new Date().toISOString() })
    .eq('id', id)
  if (error) throw new Error(error.message)
  revalidatePath('/gastos')
  revalidatePath('/dashboard')
}
