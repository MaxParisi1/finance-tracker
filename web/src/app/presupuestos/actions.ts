'use server'

import { revalidatePath } from 'next/cache'
import { getSupabaseServer } from '@/lib/supabase'
import { upsertPresupuestoSchema } from '@/lib/validation'

export async function upsertPresupuestoAction(fields: {
  categoria: string
  mes: number
  anio: number
  monto_limite: number
}) {
  const parsed = upsertPresupuestoSchema.safeParse(fields)
  if (!parsed.success) throw new Error(parsed.error.errors[0].message)

  const supabase = getSupabaseServer()
  const { error } = await supabase
    .from('presupuestos')
    .upsert(fields, { onConflict: 'categoria,mes,anio' })

  if (error) throw new Error(error.message)
  revalidatePath('/presupuestos')
  revalidatePath('/dashboard')
}

export async function deletePresupuestoAction(id: string) {
  const supabase = getSupabaseServer()
  const { error } = await supabase.from('presupuestos').delete().eq('id', id)
  if (error) throw new Error(error.message)
  revalidatePath('/presupuestos')
  revalidatePath('/dashboard')
}
