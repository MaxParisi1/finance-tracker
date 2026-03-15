'use server'

import { revalidatePath } from 'next/cache'
import { getSupabaseServer } from '@/lib/supabase'
import { getLatestTipoCambio } from '@/lib/queries'
import { recurrenteSchema } from '@/lib/validation'

function nextDueDate(diaDelMes: number, frecuencia: string): string {
  const hoy = new Date()
  let d = new Date(hoy.getFullYear(), hoy.getMonth(), diaDelMes)
  if (d < hoy) {
    if (frecuencia === 'anual') {
      d = new Date(hoy.getFullYear() + 1, hoy.getMonth(), diaDelMes)
    } else {
      d = new Date(hoy.getFullYear(), hoy.getMonth() + 1, diaDelMes)
    }
  }
  return d.toISOString().split('T')[0]
}

function addMonths(dateStr: string, months: number): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  return new Date(y, m - 1 + months, d).toISOString().split('T')[0]
}

export async function materializarRecurrentesAction(): Promise<{
  insertados: number
  omitidos: number
  errores: string[]
}> {
  const supabase = getSupabaseServer()
  const hoy = new Date().toISOString().split('T')[0]

  // Traer recurrentes cuyo próximo vencimiento ya llegó
  const { data: recurrentes, error: errFetch } = await supabase
    .from('gastos_recurrentes')
    .select('*')
    .eq('activo', true)
    .eq('no_materializar', false)
    .lte('proximo_vencimiento', hoy)

  if (errFetch) throw new Error(errFetch.message)
  if (!recurrentes || recurrentes.length === 0) return { insertados: 0, omitidos: 0, errores: [] }

  const tc_blue = await getLatestTipoCambio('blue')

  let insertados = 0
  let omitidos = 0
  const errores: string[] = []

  for (const r of recurrentes) {
    try {
      const moneda = r.moneda?.toUpperCase() ?? 'ARS'
      const monto_ars = moneda === 'USD' && tc_blue
        ? Math.round(r.monto_original * tc_blue)
        : r.monto_original

      // Verificar si ya se materializó este vencimiento (evitar duplicados)
      const { count } = await supabase
        .from('gastos')
        .select('id', { count: 'exact', head: true })
        .eq('descripcion', r.descripcion)
        .eq('fecha', r.proximo_vencimiento)
        .eq('fuente', 'recurrente_auto')
        .is('deleted_at', null)

      if ((count ?? 0) > 0) {
        omitidos++
      } else {
        await supabase.from('gastos').insert({
          descripcion: r.descripcion,
          monto_original: r.monto_original,
          moneda,
          monto_ars,
          tipo_cambio: moneda === 'USD' ? (tc_blue ?? 1) : 1,
          tipo_cambio_tipo: moneda === 'USD' ? 'blue' : 'n/a',
          categoria: r.categoria,
          medio_pago: r.medio_pago,
          fecha: r.proximo_vencimiento,
          fuente: 'recurrente_auto',
          cuotas: 1,
          cuota_actual: 1,
        })
        insertados++
      }

      // Avanzar próximo vencimiento
      let nuevaFecha: string
      if (r.frecuencia === 'anual') {
        nuevaFecha = addMonths(r.proximo_vencimiento, 12)
      } else if (r.frecuencia === 'semanal') {
        const d = new Date(r.proximo_vencimiento + 'T00:00:00')
        d.setDate(d.getDate() + 7)
        nuevaFecha = d.toISOString().split('T')[0]
      } else {
        nuevaFecha = addMonths(r.proximo_vencimiento, 1)
      }

      await supabase
        .from('gastos_recurrentes')
        .update({ proximo_vencimiento: nuevaFecha })
        .eq('id', r.id)
    } catch (e: any) {
      errores.push(`${r.descripcion}: ${e.message}`)
    }
  }

  revalidatePath('/recurrentes')
  revalidatePath('/dashboard')
  revalidatePath('/gastos')
  return { insertados, omitidos, errores }
}

export async function createRecurrenteAction(fields: {
  descripcion: string
  monto_original: number
  moneda: string
  categoria: string
  medio_pago: string
  frecuencia: string
  dia_del_mes: number
  no_materializar?: boolean
}) {
  const parsed = recurrenteSchema.safeParse(fields)
  if (!parsed.success) throw new Error(parsed.error.errors[0].message)

  const supabase = getSupabaseServer()
  const proximo_vencimiento = nextDueDate(fields.dia_del_mes, fields.frecuencia)

  const { error } = await supabase.from('gastos_recurrentes').insert({
    ...fields,
    moneda: fields.moneda.toUpperCase(),
    activo: true,
    proximo_vencimiento,
  })

  if (error) throw new Error(error.message)
  revalidatePath('/recurrentes')
}

export async function updateRecurrenteAction(
  id: string,
  fields: {
    descripcion: string
    monto_original: number
    moneda: string
    categoria: string
    medio_pago: string
    frecuencia: string
    dia_del_mes: number
    no_materializar?: boolean
  },
) {
  const parsed = recurrenteSchema.safeParse(fields)
  if (!parsed.success) throw new Error(parsed.error.errors[0].message)

  const supabase = getSupabaseServer()
  const proximo_vencimiento = nextDueDate(fields.dia_del_mes, fields.frecuencia)

  const { error } = await supabase
    .from('gastos_recurrentes')
    .update({ ...fields, moneda: fields.moneda.toUpperCase(), proximo_vencimiento })
    .eq('id', id)

  if (error) throw new Error(error.message)
  revalidatePath('/recurrentes')
}

export async function toggleRecurrenteAction(id: string, activo: boolean) {
  const supabase = getSupabaseServer()
  const { error } = await supabase
    .from('gastos_recurrentes')
    .update({ activo })
    .eq('id', id)

  if (error) throw new Error(error.message)
  revalidatePath('/recurrentes')
}
