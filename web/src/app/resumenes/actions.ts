'use server'

import { createHash } from 'crypto'
import { revalidatePath } from 'next/cache'
import { getSupabaseServer } from '@/lib/supabase'
import { exigirSesion } from '@/lib/auth'

const MAX_BYTES = 10 * 1024 * 1024

/**
 * Sube el PDF del resumen y deja la fila 'pendiente' para que la procese el bot.
 *
 * La web no lee el PDF: el parser vive en el bot (Python), junto a los demás
 * parsers de documentos. Subir dos veces el mismo archivo devuelve el resumen
 * que ya existía.
 */
export async function subirResumenAction(formData: FormData): Promise<{ id: string } | { error: string }> {
  exigirSesion()
  const file = formData.get('file') as File | null
  if (!file || file.size === 0) return { error: 'Elegí el PDF del resumen.' }
  if (file.type !== 'application/pdf') return { error: 'El resumen tiene que ser un PDF.' }
  if (file.size > MAX_BYTES) return { error: 'El PDF pesa más de 10 MB.' }

  const bytes = Buffer.from(await file.arrayBuffer())
  if (bytes.subarray(0, 5).toString() !== '%PDF-') return { error: 'El archivo no es un PDF válido.' }
  const sha256 = createHash('sha256').update(bytes).digest('hex')

  const supabase = getSupabaseServer()
  const existente = await supabase.from('resumenes_tarjeta').select('id').eq('sha256', sha256).maybeSingle()
  if (existente.data) return { id: existente.data.id }

  const storage_path = `${new Date().getUTCFullYear()}/${sha256}.pdf`
  const subida = await supabase.storage
    .from('resumenes')
    .upload(storage_path, bytes, { contentType: 'application/pdf', upsert: true })
  if (subida.error) return { error: `No pude subir el PDF: ${subida.error.message}` }

  const { data, error } = await supabase
    .from('resumenes_tarjeta')
    .insert({ sha256, storage_path, nombre_archivo: file.name })
    .select('id')
    .single()
  if (error) return { error: error.message }

  revalidatePath('/resumenes')
  return { id: data.id }
}

/**
 * Marca los movimientos elegidos para que el bot cree los gastos.
 *
 * Solo pasan movimientos de este resumen que están en un estado cargable: un
 * POST armado a mano no puede convertir en gasto algo que ya coincidió con
 * otro, ni un pago del resumen anterior.
 */
export async function cargarMovimientosAction(
  resumenId: string,
  items: { id: string; categoria: string; recurrente_id: string | null }[],
): Promise<{ ok: true } | { error: string }> {
  exigirSesion()
  if (items.length === 0) return { error: 'No elegiste ningún movimiento.' }

  const supabase = getSupabaseServer()
  // Una bonificación no lleva categoría: se resta del gasto de su consumo.
  const { data: filas, error: errFilas } = await supabase
    .from('resumen_movimientos')
    .select('id, estado')
    .eq('resumen_id', resumenId)
    .in('id', items.map(i => i.id))
  if (errFilas) return { error: errFilas.message }
  const estado = new Map((filas ?? []).map(f => [f.id, f.estado as string]))
  if (items.some(i => !i.categoria && estado.get(i.id) !== 'bonificacion')) {
    return { error: 'Todos los movimientos a cargar necesitan categoría.' }
  }

  for (const item of items) {
    const { error } = await supabase
      .from('resumen_movimientos')
      .update({
        estado: 'a_cargar',
        categoria_sugerida: item.categoria || null,
        recurrente_id: item.recurrente_id,
      })
      .eq('id', item.id)
      .eq('resumen_id', resumenId)
      .in('estado', ['falta', 'impuesto', 'percepcion', 'bonificacion', 'descartado'])
    if (error) return { error: error.message }
  }
  revalidatePath(`/resumenes/${resumenId}`)
  return { ok: true }
}

/** Deja asentado que un faltante no se carga (queda a la vista, se puede revertir). */
export async function descartarMovimientosAction(
  resumenId: string,
  ids: string[],
): Promise<{ ok: true } | { error: string }> {
  exigirSesion()
  const supabase = getSupabaseServer()
  const { error } = await supabase
    .from('resumen_movimientos')
    .update({ estado: 'descartado' })
    .in('id', ids)
    .eq('resumen_id', resumenId)
    .in('estado', ['falta', 'impuesto', 'percepcion', 'bonificacion'])
  if (error) return { error: error.message }
  revalidatePath(`/resumenes/${resumenId}`)
  return { ok: true }
}

/** Vuelve a mandar al bot un resumen que falló (por ejemplo, tras arreglar el parser). */
export async function reprocesarResumenAction(resumenId: string): Promise<{ ok: true } | { error: string }> {
  exigirSesion()
  const supabase = getSupabaseServer()
  const { error } = await supabase
    .from('resumenes_tarjeta')
    .update({ estado: 'pendiente', error: null })
    .eq('id', resumenId)
    .eq('estado', 'error')
  if (error) return { error: error.message }
  revalidatePath(`/resumenes/${resumenId}`)
  return { ok: true }
}
