import { NextRequest, NextResponse } from 'next/server'
import { getArchivosPorGasto } from '@/lib/queries'
import { getSupabaseServer } from '@/lib/supabase'

export async function GET(req: NextRequest) {
  const gastoId = req.nextUrl.searchParams.get('gastoId')
  if (!gastoId) return NextResponse.json([], { status: 200 })

  try {
    const archivos = await getArchivosPorGasto(gastoId)
    return NextResponse.json(archivos)
  } catch {
    return NextResponse.json([], { status: 200 })
  }
}

export async function DELETE(req: NextRequest) {
  const id = req.nextUrl.searchParams.get('id')
  if (!id) return NextResponse.json({ error: 'Falta el id' }, { status: 400 })

  try {
    const supabase = getSupabaseServer()
    const { error } = await supabase.from('archivos_drive').delete().eq('id', id)
    if (error) throw error
    return NextResponse.json({ eliminado: true, id })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function PATCH(req: NextRequest) {
  const id = req.nextUrl.searchParams.get('id')
  if (!id) return NextResponse.json({ error: 'Falta el id' }, { status: 400 })

  try {
    const supabase = getSupabaseServer()
    const { error } = await supabase
      .from('archivos_drive')
      .update({ gasto_id: null })
      .eq('id', id)
    if (error) throw error
    return NextResponse.json({ desvinculado: true, id })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
