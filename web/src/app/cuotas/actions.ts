'use server'

import { revalidatePath } from 'next/cache'
import { getSupabaseServer } from '@/lib/supabase'
import { getTipoCambioActual } from '@/lib/queries'

// Local date formatting — avoids toISOString() UTC offset shifting the date
function formatDate(y: number, m: number, d: number): string {
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

// Next occurrence of diaDelMes on or after today (all local arithmetic)
function nextVencimiento(diaDelMes: number): string {
  const hoy = new Date()
  const y = hoy.getFullYear()
  const m = hoy.getMonth() + 1
  const d = hoy.getDate()

  const lastDayCurrent = new Date(y, m, 0).getDate()
  const dayThisMonth = Math.min(diaDelMes, lastDayCurrent)

  if (d <= dayThisMonth) {
    return formatDate(y, m, dayThisMonth)
  }
  const nextY = m === 12 ? y + 1 : y
  const nextM = m === 12 ? 1 : m + 1
  const lastDayNext = new Date(nextY, nextM, 0).getDate()
  return formatDate(nextY, nextM, Math.min(diaDelMes, lastDayNext))
}

// Add n months to a YYYY-MM-DD string, clamping day to last valid day of target month
function addMonths(dateStr: string, n = 1): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  const target = new Date(y, m - 1 + n, 1) // navigate to first of target month (no day overflow)
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate()
  return formatDate(target.getFullYear(), target.getMonth() + 1, Math.min(d, lastDay))
}

// Next vencimiento pinned to diaDelMes, one month after fechaBase
function nextVencimientoDesde(fechaBase: string, diaDelMes: number): string {
  const [y, m] = fechaBase.split('-').map(Number)
  const nextY = m === 12 ? y + 1 : y
  const nextM = m === 12 ? 1 : m + 1
  const lastDay = new Date(nextY, nextM, 0).getDate()
  return formatDate(nextY, nextM, Math.min(diaDelMes, lastDay))
}

// ── Crear plan ──────────────────────────────────────────────

export async function createPlanCuotaAction(fields: {
  descripcion: string
  comercio?: string
  categoria?: string
  medio_pago: string
  monto_cuota?: number | null
  moneda: string
  cuotas_total: number
  cuota_actual: number
  dia_del_mes: number
  tipo: 'fijo' | 'variable'
}) {
  const supabase = getSupabaseServer()
  const proximo_vencimiento = nextVencimiento(fields.dia_del_mes)

  const { error } = await supabase.from('planes_cuota').insert({
    ...fields,
    moneda: fields.moneda.toUpperCase(),
    monto_cuota: fields.tipo === 'fijo' ? (fields.monto_cuota ?? null) : null,
    proximo_vencimiento,
    activo: true,
  })

  if (error) throw new Error(error.message)
  revalidatePath('/cuotas')
  revalidatePath('/dashboard')
}

// ── Editar plan ─────────────────────────────────────────────

export async function updatePlanCuotaAction(
  id: string,
  fields: {
    descripcion: string
    comercio?: string
    categoria?: string
    medio_pago: string
    monto_cuota?: number | null
    moneda: string
    cuotas_total: number
    cuota_actual: number
    dia_del_mes: number
    tipo: 'fijo' | 'variable'
  },
) {
  const supabase = getSupabaseServer()
  const proximo_vencimiento = nextVencimiento(fields.dia_del_mes)

  const { error } = await supabase
    .from('planes_cuota')
    .update({
      ...fields,
      moneda: fields.moneda.toUpperCase(),
      monto_cuota: fields.tipo === 'fijo' ? (fields.monto_cuota ?? null) : null,
      proximo_vencimiento,
    })
    .eq('id', id)

  if (error) throw new Error(error.message)
  revalidatePath('/cuotas')
  revalidatePath('/dashboard')
}

// ── Activar / desactivar ────────────────────────────────────

export async function togglePlanCuotaAction(id: string, activo: boolean) {
  const supabase = getSupabaseServer()
  const { error } = await supabase
    .from('planes_cuota')
    .update({ activo })
    .eq('id', id)
  if (error) throw new Error(error.message)
  revalidatePath('/cuotas')
  revalidatePath('/dashboard')
}

// ── Registrar pago (planes variables) ──────────────────────

export async function registrarPagoCuotaAction(
  planId: string,
  fields: {
    monto: number
    moneda: string
    fecha: string
    notas?: string
    cuotaActual: number
    cuotasTotal: number
    descripcion: string
    comercio?: string
    categoria?: string
    medio_pago: string
    diaDelMes: number
  },
) {
  const supabase = getSupabaseServer()
  const moneda = fields.moneda.toUpperCase()

  const tc = moneda === 'USD' ? ((await getTipoCambioActual('oficial'))?.valor ?? 1) : 1
  const monto_ars = moneda === 'USD' ? Math.round(fields.monto * tc) : fields.monto

  const { error: errGasto } = await supabase.from('gastos').insert({
    descripcion: fields.descripcion,
    monto_original: fields.monto,
    moneda,
    monto_ars,
    tipo_cambio: tc,
    tipo_cambio_tipo: moneda === 'USD' ? 'oficial' : 'n/a',
    categoria: fields.categoria ?? null,
    medio_pago: fields.medio_pago,
    comercio: fields.comercio?.trim() || null,
    fecha: fields.fecha,
    notas: fields.notas ?? null,
    fuente: 'plan_cuota_manual',
    cuotas: 1,
    cuota_actual: 1,
  })
  if (errGasto) throw new Error(errGasto.message)

  // Avanzar el plan — pin next vencimiento to dia_del_mes, not to fields.fecha
  const nuevaCuota = fields.cuotaActual + 1
  const terminado = nuevaCuota > fields.cuotasTotal

  const { error: errPlan } = await supabase
    .from('planes_cuota')
    .update({
      cuota_actual: terminado ? fields.cuotasTotal : nuevaCuota,
      proximo_vencimiento: terminado
        ? fields.fecha
        : nextVencimientoDesde(fields.fecha, fields.diaDelMes),
      activo: !terminado,
    })
    .eq('id', planId)

  if (errPlan) throw new Error(errPlan.message)

  revalidatePath('/cuotas')
  revalidatePath('/gastos')
  revalidatePath('/dashboard')
}

// ── Materializar planes fijos vencidos ──────────────────────

export async function materializarPlanesFijosAction(): Promise<{
  insertados: number
  omitidos: number
  errores: string[]
}> {
  const supabase = getSupabaseServer()
  const hoy = new Date()
  const todayStr = formatDate(hoy.getFullYear(), hoy.getMonth() + 1, hoy.getDate())

  const { data: planes, error } = await supabase
    .from('planes_cuota')
    .select('*')
    .eq('activo', true)
    .eq('tipo', 'fijo')
    .lte('proximo_vencimiento', todayStr)

  if (error) throw new Error(error.message)
  if (!planes || planes.length === 0) return { insertados: 0, omitidos: 0, errores: [] }

  const tc = (await getTipoCambioActual('oficial'))?.valor ?? 1
  let insertados = 0, omitidos = 0
  const errores: string[] = []

  for (const p of planes) {
    try {
      // Verificar duplicado
      const { count } = await supabase
        .from('gastos')
        .select('id', { count: 'exact', head: true })
        .eq('descripcion', p.descripcion)
        .eq('fecha', p.proximo_vencimiento)
        .eq('fuente', 'plan_cuota_auto')
        .is('deleted_at', null)

      if ((count ?? 0) > 0) {
        omitidos++
      } else {
        const moneda = p.moneda?.toUpperCase() ?? 'ARS'
        const monto_ars = moneda === 'USD'
          ? Math.round((p.monto_cuota ?? 0) * tc)
          : (p.monto_cuota ?? 0)

        await supabase.from('gastos').insert({
          descripcion: p.descripcion,
          monto_original: p.monto_cuota,
          moneda,
          monto_ars,
          tipo_cambio: moneda === 'USD' ? tc : 1,
          tipo_cambio_tipo: moneda === 'USD' ? 'oficial' : 'n/a',
          categoria: p.categoria ?? null,
          medio_pago: p.medio_pago,
          comercio: p.comercio ?? null,
          fecha: p.proximo_vencimiento,
          fuente: 'plan_cuota_auto',
          cuotas: 1,
          cuota_actual: 1,
        })
        insertados++

        // Avanzar el plan only after successful insert (not on duplicate skip)
        const nuevaCuota = p.cuota_actual + 1
        const terminado = nuevaCuota > p.cuotas_total

        await supabase
          .from('planes_cuota')
          .update({
            cuota_actual: terminado ? p.cuotas_total : nuevaCuota,
            proximo_vencimiento: terminado
              ? p.proximo_vencimiento
              : addMonths(p.proximo_vencimiento, 1),
            activo: !terminado,
          })
          .eq('id', p.id)
      }
    } catch (e: any) {
      errores.push(`${p.descripcion}: ${e.message}`)
    }
  }

  revalidatePath('/cuotas')
  revalidatePath('/dashboard')
  revalidatePath('/gastos')
  return { insertados, omitidos, errores }
}
