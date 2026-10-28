'use server'

import { revalidatePath } from 'next/cache'
import { getSupabaseServer } from '@/lib/supabase'
import { getAllComercios, getCategorias, getTipoCambioActual } from '@/lib/queries'
import { createGastoSchema, updateGastoSchema } from '@/lib/validation'
import { hoyISO } from '@/lib/fechas'
import { exigirSesion } from '@/lib/auth'

/** Lo que necesita el formulario de alta: se pide recién al abrirlo. */
export async function getOpcionesGastoAction(): Promise<{
  categorias: string[]
  comercios: string[]
  hoy: string
}> {
  exigirSesion()
  const [categorias, comercios] = await Promise.all([getCategorias(), getAllComercios()])
  return { categorias: categorias.map(c => c.nombre), comercios, hoy: hoyISO() }
}

/**
 * Alta manual de un gasto: lo que no llega por mail (efectivo, transferencias,
 * la tarjeta que no avisa).
 */
export async function createGastoAction(fields: {
  descripcion: string
  monto: number
  moneda: string
  categoria: string
  medio_pago: string
  fecha: string
  notas?: string
  comercio?: string
}): Promise<{ id: string }> {
  exigirSesion()
  const parsed = createGastoSchema.safeParse(fields)
  if (!parsed.success) throw new Error(parsed.error.errors[0].message)
  const datos = parsed.data

  let monto_ars = datos.monto
  let tipo_cambio = 1.0
  let tipo_cambio_tipo = 'n/a'

  if (datos.moneda === 'USD') {
    const tc = (await getTipoCambioActual('oficial'))?.valor ?? null
    // Sin cotización no se guarda: un gasto en dólares con el monto en pesos
    // inventado queda mal en todos los totales y no avisa.
    if (!tc) throw new Error('No pude obtener el tipo de cambio. Probá de nuevo en un rato.')
    monto_ars = Math.round(datos.monto * tc * 100) / 100
    tipo_cambio = tc
    tipo_cambio_tipo = 'oficial'
  }

  const supabase = getSupabaseServer()
  const { data, error } = await supabase
    .from('gastos')
    .insert({
      descripcion: datos.descripcion.trim(),
      monto_original: datos.monto,
      moneda: datos.moneda,
      monto_ars,
      tipo_cambio,
      tipo_cambio_tipo,
      categoria: datos.categoria,
      medio_pago: datos.medio_pago,
      fecha: datos.fecha,
      notas: datos.notas?.trim() || null,
      comercio: datos.comercio?.trim() || null,
      cuotas: 1,
      cuota_actual: 1,
      fuente: 'web_manual',
    })
    .select('id')
    .single()

  if (error) throw new Error(error.message)

  revalidatePath('/gastos')
  revalidatePath('/dashboard')
  revalidatePath('/analytics')
  return { id: data.id }
}

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
    comercio?: string
  },
) {
  exigirSesion()
  const parsed = updateGastoSchema.safeParse(fields)
  if (!parsed.success) throw new Error(parsed.error.errors[0].message)

  const supabase = getSupabaseServer()
  const monedaUpper = fields.moneda.toUpperCase()

  let monto_ars = fields.monto
  let tipo_cambio = 1.0
  let tipo_cambio_tipo = 'n/a'

  if (monedaUpper === 'USD') {
    const tcInfo = await getTipoCambioActual('oficial')
    const tc = tcInfo?.valor ?? null
    if (tc) {
      monto_ars = fields.monto * tc
      tipo_cambio = tc
      tipo_cambio_tipo = 'oficial'
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
      comercio: fields.comercio?.trim() || null,
    })
    .eq('id', id)

  if (error) throw new Error(error.message)

  // Sincronizar fecha de comprobantes vinculados (best-effort)
  await supabase
    .from('archivos_drive')
    .update({ fecha: fields.fecha })
    .eq('gasto_id', id)

  revalidatePath('/gastos')
  revalidatePath('/dashboard')
  revalidatePath('/comprobantes')
}

/**
 * Avanza una fecha (YYYY-MM-DD) un período según la frecuencia, con clamp de
 * fin de mes. Trabaja en UTC para evitar corrimientos por zona horaria.
 */
function siguienteVencimiento(fecha: string, frecuencia: string): string {
  const [y, m, d] = fecha.split('-').map(Number)
  let ny = y
  let nm = m
  if (frecuencia === 'anual') {
    ny = y + 1
  } else if (frecuencia === 'semestral') {
    nm = m + 6
    if (nm > 12) {
      nm -= 12
      ny = y + 1
    }
  } else if (frecuencia === 'semanal') {
    const dt = new Date(Date.UTC(y, m - 1, d))
    dt.setUTCDate(dt.getUTCDate() + 7)
    return dt.toISOString().split('T')[0]
  } else {
    nm = m + 1
    if (nm > 12) {
      nm = 1
      ny = y + 1
    }
  }
  const ultimoDia = new Date(Date.UTC(ny, nm, 0)).getUTCDate() // día 0 del mes siguiente = último del mes
  const dt = new Date(Date.UTC(ny, nm - 1, Math.min(d, ultimoDia)))
  return dt.toISOString().split('T')[0]
}

export async function vincularRecurrenteAction(
  gastoId: string,
  recurrenteId: string | null,
  comercio?: string,
) {
  exigirSesion()
  const supabase = getSupabaseServer()

  await supabase
    .from('gastos')
    .update({ recurrente_id: recurrenteId })
    .eq('id', gastoId)

  if (recurrenteId === null) {
    revalidatePath('/gastos')
    return
  }

  // Guardar alias para auto-matching futuro
  if (comercio?.trim()) {
    const norm = comercio.trim().toLowerCase()
      .replace(/\.(com|net|org|ar|io)\b/g, '')
      .replace(/[*.\-_/\\]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
    if (norm) {
      await supabase
        .from('recurrentes_aliases')
        .upsert(
          { recurrente_id: recurrenteId, comercio_normalizado: norm, confirmado_por_usuario: true },
          { onConflict: 'comercio_normalizado' },
        )
    }
  }

  // Datos del gasto vinculado: sirven para actualizar el monto esperado y
  // anclar el avance de la fecha al pago real.
  const { data: gasto } = await supabase
    .from('gastos')
    .select('monto_original, fecha')
    .eq('id', gastoId)
    .single()

  const { data: rec } = await supabase
    .from('gastos_recurrentes')
    .select('frecuencia, proximo_vencimiento')
    .eq('id', recurrenteId)
    .single()

  const updates: { monto_original?: number; proximo_vencimiento?: string } = {}

  // Actualizar el monto esperado al último observado (igual que el bot)
  if (gasto?.monto_original != null) {
    updates.monto_original = gasto.monto_original
  }

  // Avanzar proximo_vencimiento; si el pago llegó tarde, seguir avanzando
  // hasta superar la fecha del pago para no desalinear la ventana futura.
  if (rec?.proximo_vencimiento) {
    const frecuencia = rec.frecuencia ?? 'mensual'
    const ancla = gasto?.fecha ?? hoyISO()
    let nueva = siguienteVencimiento(rec.proximo_vencimiento, frecuencia)
    let guard = 0
    while (nueva <= ancla && guard < 120) {
      nueva = siguienteVencimiento(nueva, frecuencia)
      guard++
    }
    updates.proximo_vencimiento = nueva
  }

  if (Object.keys(updates).length > 0) {
    await supabase
      .from('gastos_recurrentes')
      .update(updates)
      .eq('id', recurrenteId)
  }

  revalidatePath('/gastos')
  revalidatePath('/recurrentes')
}

export async function deleteGastoAction(id: string) {
  exigirSesion()
  const supabase = getSupabaseServer()
  const { error } = await supabase
    .from('gastos')
    .update({ deleted_at: new Date().toISOString() })
    .eq('id', id)
  if (error) throw new Error(error.message)
  revalidatePath('/gastos')
  revalidatePath('/dashboard')
}

export async function bulkRecategorizarAction(ids: string[], categoria: string) {
  exigirSesion()
  if (!ids.length || !categoria) return
  const supabase = getSupabaseServer()
  const { error } = await supabase.from('gastos').update({ categoria }).in('id', ids)
  if (error) throw new Error(error.message)
  revalidatePath('/gastos')
  revalidatePath('/dashboard')
}

export async function bulkDeleteGastosAction(ids: string[]) {
  exigirSesion()
  if (!ids.length) return
  const supabase = getSupabaseServer()
  const { error } = await supabase
    .from('gastos')
    .update({ deleted_at: new Date().toISOString() })
    .in('id', ids)
  if (error) throw new Error(error.message)
  revalidatePath('/gastos')
  revalidatePath('/dashboard')
}
