import { NextRequest, NextResponse } from 'next/server'
import { getArchivosPorGasto } from '@/lib/queries'

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
