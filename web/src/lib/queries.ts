import { getSupabaseServer } from './supabase'
import type { Gasto, GastoRecurrente, Categoria, MensualResumen, TendenciaMes, ArchivoDrive } from './types'
import { monthLabel } from './utils'

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function monthRange(mes: number, anio: number): { desde: string; hasta: string } {
  const desde = `${anio}-${String(mes).padStart(2, '0')}-01`
  const hasta =
    mes === 12
      ? `${anio + 1}-01-01`
      : `${anio}-${String(mes + 1).padStart(2, '0')}-01`
  return { desde, hasta }
}

// ──────────────────────────────────────────────
// Gastos
// ──────────────────────────────────────────────

export async function getGastosMes(mes: number, anio: number): Promise<Gasto[]> {
  const supabase = getSupabaseServer()
  const { desde, hasta } = monthRange(mes, anio)

  const { data, error } = await supabase
    .from('gastos')
    .select('*')
    .is('deleted_at', null)
    .gte('fecha', desde)
    .lt('fecha', hasta)
    .order('fecha', { ascending: false })

  if (error) throw error
  return data ?? []
}

export async function getGastosRecientes(limit = 10): Promise<Gasto[]> {
  const supabase = getSupabaseServer()
  const { data, error } = await supabase
    .from('gastos')
    .select('*')
    .is('deleted_at', null)
    .order('fecha', { ascending: false })
    .limit(limit)

  if (error) throw error
  return data ?? []
}

export async function searchGastos(q: string): Promise<Gasto[]> {
  const supabase = getSupabaseServer()
  const term = q.trim()
  if (!term) return []

  const { data, error } = await supabase
    .from('gastos')
    .select('*')
    .is('deleted_at', null)
    .or(`descripcion.ilike.%${term}%,comercio.ilike.%${term}%`)
    .order('fecha', { ascending: false })
    .limit(200)

  if (error) throw error
  return data ?? []
}

export async function getCategorias(): Promise<Categoria[]> {
  const supabase = getSupabaseServer()
  const { data, error } = await supabase
    .from('categorias')
    .select('nombre, descripcion, color, icono')
    .eq('activa', true)
    .order('nombre')

  if (error) throw error
  return data ?? []
}

export async function getRecurrentes(): Promise<GastoRecurrente[]> {
  const supabase = getSupabaseServer()
  const { data, error } = await supabase
    .from('gastos_recurrentes')
    .select('*')
    .eq('activo', true)
    .order('proximo_vencimiento')

  if (error) throw error
  return data ?? []
}

// ──────────────────────────────────────────────
// Agregaciones
// ──────────────────────────────────────────────

export async function getResumenMes(
  mes: number,
  anio: number,
  categorias?: Categoria[],
): Promise<MensualResumen> {
  const gastos = await getGastosMes(mes, anio)
  const cats = categorias ?? (await getCategorias())
  const colorMap = Object.fromEntries(cats.map(c => [c.nombre, c.color]))

  const porCategoria = new Map<string, { total_ars: number; cantidad: number }>()
  let total_ars = 0

  for (const g of gastos) {
    const cat = g.categoria ?? 'Sin categoría'
    const monto = g.monto_ars ?? 0
    total_ars += monto
    const prev = porCategoria.get(cat) ?? { total_ars: 0, cantidad: 0 }
    porCategoria.set(cat, { total_ars: prev.total_ars + monto, cantidad: prev.cantidad + 1 })
  }

  const por_categoria = Array.from(porCategoria.entries())
    .map(([categoria, v]) => ({
      categoria,
      total_ars: Math.round(v.total_ars),
      cantidad: v.cantidad,
      color: colorMap[categoria] ?? '#9E9E9E',
    }))
    .sort((a, b) => b.total_ars - a.total_ars)

  return { mes, anio, total_ars: Math.round(total_ars), cantidad: gastos.length, por_categoria }
}

export async function getTendencia(meses = 6): Promise<TendenciaMes[]> {
  const hoy = new Date()
  const periodos: { mes: number; anio: number }[] = []

  for (let i = meses - 1; i >= 0; i--) {
    let mes = hoy.getMonth() + 1 - i
    let anio = hoy.getFullYear()
    while (mes <= 0) { mes += 12; anio-- }
    periodos.push({ mes, anio })
  }

  const resúmenes = await Promise.all(periodos.map(p => getResumenMes(p.mes, p.anio)))

  return resúmenes.map((r, i) => {
    const prev = i > 0 ? resúmenes[i - 1].total_ars : null
    const variacion_pct =
      prev !== null && prev > 0 ? Math.round(((r.total_ars - prev) / prev) * 1000) / 10 : null

    return {
      mes: r.mes,
      anio: r.anio,
      label: monthLabel(r.mes, r.anio),
      total_ars: r.total_ars,
      cantidad: r.cantidad,
      variacion_pct,
    }
  })
}

export async function getTopComercios(
  mes: number,
  anio: number,
  limite = 10,
): Promise<{ nombre: string; total_ars: number; cantidad: number }[]> {
  const gastos = await getGastosMes(mes, anio)
  const map = new Map<string, { total_ars: number; cantidad: number }>()

  for (const g of gastos) {
    const nombre = g.comercio || g.descripcion || 'Sin descripción'
    const prev = map.get(nombre) ?? { total_ars: 0, cantidad: 0 }
    map.set(nombre, {
      total_ars: prev.total_ars + (g.monto_ars ?? 0),
      cantidad: prev.cantidad + 1,
    })
  }

  return Array.from(map.entries())
    .map(([nombre, v]) => ({ nombre, total_ars: Math.round(v.total_ars), cantidad: v.cantidad }))
    .sort((a, b) => b.total_ars - a.total_ars)
    .slice(0, limite)
}

// ──────────────────────────────────────────────
// Tipo de cambio histórico
// ──────────────────────────────────────────────

const BLUELYTICS_URL = 'https://api.bluelytics.com.ar/v2/latest'

export async function getLatestTipoCambio(tipo = 'oficial'): Promise<number | null> {
  const supabase = getSupabaseServer()
  const { data } = await supabase
    .from('tipos_cambio_historico')
    .select('valor, fecha')
    .eq('tipo', tipo)
    .order('fecha', { ascending: false })
    .limit(1)

  return data?.[0]?.valor ?? null
}

export interface TipoCambioInfo {
  valor: number
  fecha: string
  esHoy: boolean
}

export async function getTipoCambioActual(tipo = 'oficial'): Promise<TipoCambioInfo | null> {
  const supabase = getSupabaseServer()
  const hoy = new Date().toISOString().split('T')[0]

  // Always fetch from Bluelytics; Next.js Data Cache revalida cada hora
  try {
    const res = await fetch(BLUELYTICS_URL, { next: { revalidate: 3600 } })
    if (!res.ok) throw new Error(`Bluelytics ${res.status}`)
    const json = await res.json()

    const keyMap: Record<string, string> = { oficial: 'oficial', blue: 'blue', mep: 'blue_euro' }
    const cotizacion = json[keyMap[tipo] ?? 'oficial'] ?? json.oficial
    const compra = parseFloat(cotizacion.value_buy)
    const venta = parseFloat(cotizacion.value_sell)
    const promedio = Math.round(((compra + venta) / 2) * 10000) / 10000

    // Upsert en DB para historial (el bot también lo hace, esto lo complementa)
    await supabase
      .from('tipos_cambio_historico')
      .upsert({ fecha: hoy, tipo, valor: promedio }, { onConflict: 'fecha,tipo' })

    return { valor: promedio, fecha: hoy, esHoy: true }
  } catch {
    // Bluelytics no disponible → usar el registro más reciente de la DB
    const { data: fallback } = await supabase
      .from('tipos_cambio_historico')
      .select('valor, fecha')
      .eq('tipo', tipo)
      .order('fecha', { ascending: false })
      .limit(1)

    if (fallback?.[0]) {
      return { valor: fallback[0].valor, fecha: fallback[0].fecha, esHoy: fallback[0].fecha === hoy }
    }
    return null
  }
}

// ──────────────────────────────────────────────
// Gasto diario del mes (acumulado + por día)
// ──────────────────────────────────────────────

export async function getDailySpending(
  mes: number,
  anio: number,
): Promise<{ dia: number; total_ars: number; acumulado: number }[]> {
  const gastos = await getGastosMes(mes, anio)
  const hoy = new Date()
  const diasHastaHoy =
    hoy.getFullYear() === anio && hoy.getMonth() + 1 === mes
      ? hoy.getDate()
      : new Date(anio, mes, 0).getDate()

  const byDay = new Map<number, number>()
  for (const g of gastos) {
    const dia = parseInt(g.fecha.split('-')[2])
    byDay.set(dia, (byDay.get(dia) ?? 0) + (g.monto_ars ?? 0))
  }

  const result = []
  let acumulado = 0
  for (let d = 1; d <= diasHastaHoy; d++) {
    const total = Math.round(byDay.get(d) ?? 0)
    acumulado += total
    result.push({ dia: d, total_ars: total, acumulado })
  }

  return result
}

// ──────────────────────────────────────────────
// Desglose por medio de pago
// ──────────────────────────────────────────────

export async function getPaymentMethodBreakdown(
  mes: number,
  anio: number,
): Promise<{ medio_pago: string; total_ars: number; cantidad: number }[]> {
  const gastos = await getGastosMes(mes, anio)
  const map = new Map<string, { total_ars: number; cantidad: number }>()

  for (const g of gastos) {
    const mp = g.medio_pago ?? 'Sin especificar'
    const prev = map.get(mp) ?? { total_ars: 0, cantidad: 0 }
    map.set(mp, { total_ars: prev.total_ars + (g.monto_ars ?? 0), cantidad: prev.cantidad + 1 })
  }

  return Array.from(map.entries())
    .map(([medio_pago, v]) => ({
      medio_pago,
      total_ars: Math.round(v.total_ars),
      cantidad: v.cantidad,
    }))
    .sort((a, b) => b.total_ars - a.total_ars)
}

// ──────────────────────────────────────────────
// Recurrentes con costo mensual calculado
// ──────────────────────────────────────────────

// ──────────────────────────────────────────────
// Presupuestos
// ──────────────────────────────────────────────

export async function getPresupuestos(mes: number, anio: number) {
  const supabase = getSupabaseServer()
  const { data, error } = await supabase
    .from('presupuestos')
    .select('*')
    .eq('mes', mes)
    .eq('anio', anio)

  if (error) throw error
  return (data ?? []) as { id: string; categoria: string; mes: number; anio: number; monto_limite: number }[]
}

export async function getPresupuestosConGasto(mes: number, anio: number) {
  const [presupuestos, resumen] = await Promise.all([
    getPresupuestos(mes, anio),
    getResumenMes(mes, anio),
  ])

  const gastoMap = Object.fromEntries(
    resumen.por_categoria.map(c => [c.categoria, c.total_ars]),
  )

  return presupuestos.map(p => ({
    ...p,
    gastado: gastoMap[p.categoria] ?? 0,
    pct: p.monto_limite > 0 ? Math.round(((gastoMap[p.categoria] ?? 0) / p.monto_limite) * 100) : 0,
  }))
}

// ──────────────────────────────────────────────
// Cuotas activas
// ──────────────────────────────────────────────

export interface CuotaActiva {
  descripcion: string
  comercio: string | null
  categoria: string
  cuotas: number
  cuota_pendiente: number
  monto_original: number
  moneda: string
  monto_ars: number
  proxima_fecha: string
  fecha_fin: string
}

export async function getCuotasActivas(): Promise<CuotaActiva[]> {
  const supabase = getSupabaseServer()
  const hoy = new Date().toISOString().split('T')[0]

  const { data, error } = await supabase
    .from('gastos')
    .select('descripcion, comercio, cuotas, cuota_actual, monto_original, moneda, monto_ars, fecha, categoria')
    .gt('cuotas', 1)
    .is('deleted_at', null)
    .order('fecha', { ascending: true })

  if (error || !data) return []

  const groups = new Map<string, typeof data>()
  for (const g of data) {
    const key = `${g.descripcion}||${g.cuotas}||${g.monto_original}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(g)
  }

  const result: CuotaActiva[] = []
  for (const items of groups.values()) {
    const pending = items.filter(i => i.fecha >= hoy)
    if (pending.length === 0) continue

    const allSorted = [...items].sort((a, b) => a.cuota_actual - b.cuota_actual)
    const pendingSorted = [...pending].sort((a, b) => a.cuota_actual - b.cuota_actual)

    result.push({
      descripcion: items[0].descripcion,
      comercio: items[0].comercio,
      categoria: items[0].categoria,
      cuotas: items[0].cuotas,
      cuota_pendiente: pendingSorted[0].cuota_actual,
      monto_original: items[0].monto_original,
      moneda: items[0].moneda,
      monto_ars: pendingSorted[0].monto_ars,
      proxima_fecha: pendingSorted[0].fecha,
      fecha_fin: allSorted[allSorted.length - 1].fecha,
    })
  }

  return result.sort((a, b) => a.proxima_fecha.localeCompare(b.proxima_fecha))
}

export interface RecurrenteConCosto extends GastoRecurrente {
  mensual_ars: number
  dias_para_vencimiento: number
}

export async function getRecurrentesConCosto(): Promise<{
  recurrentes: RecurrenteConCosto[]
  total_mensual_ars: number
  total_anual_ars: number
  tc_blue: number | null
  tc_fecha: string | null
  tc_es_hoy: boolean
}> {
  const [recurrentes, tcInfo] = await Promise.all([
    getRecurrentes(),
    getTipoCambioActual('oficial'),
  ])
  const tc_blue = tcInfo?.valor ?? null

  const hoy = new Date()

  const recurrentesConCosto: RecurrenteConCosto[] = recurrentes.map(r => {
    const monto = r.monto_original
    const tc = tc_blue ?? 1
    const montoARS = r.moneda === 'USD' ? monto * tc : monto

    let mensual_ars: number
    if (r.frecuencia === 'anual') mensual_ars = Math.round(montoARS / 12)
    else if (r.frecuencia === 'semanal') mensual_ars = Math.round((montoARS * 52) / 12)
    else mensual_ars = Math.round(montoARS)

    const vencimiento = new Date(r.proximo_vencimiento + 'T00:00:00')
    const dias = Math.ceil((vencimiento.getTime() - hoy.getTime()) / (1000 * 60 * 60 * 24))

    return { ...r, mensual_ars, dias_para_vencimiento: dias }
  })

  const total_mensual_ars = recurrentesConCosto.reduce((sum, r) => sum + r.mensual_ars, 0)

  return {
    recurrentes: recurrentesConCosto,
    total_mensual_ars,
    total_anual_ars: total_mensual_ars * 12,
    tc_blue,
    tc_fecha: tcInfo?.fecha ?? null,
    tc_es_hoy: tcInfo?.esHoy ?? false,
  }
}

// ──────────────────────────────────────────────
// Archivos Drive (comprobantes/facturas)
// ──────────────────────────────────────────────

export async function getArchivosDrive(filtros?: {
  mes?: number
  anio?: number
  comercio?: string
  categoria?: string
  tipo?: string
}): Promise<ArchivoDrive[]> {
  const supabase = getSupabaseServer()
  let q = supabase.from('archivos_drive').select('*')

  if (filtros?.mes && filtros?.anio) {
    const { desde, hasta } = monthRange(filtros.mes, filtros.anio)
    q = q.gte('fecha', desde).lt('fecha', hasta)
  } else if (filtros?.anio) {
    q = q.gte('fecha', `${filtros.anio}-01-01`).lt('fecha', `${filtros.anio + 1}-01-01`)
  }

  if (filtros?.comercio) {
    q = q.ilike('comercio', `%${filtros.comercio}%`)
  }
  if (filtros?.categoria) {
    q = q.eq('categoria', filtros.categoria)
  }
  if (filtros?.tipo) {
    q = q.eq('tipo', filtros.tipo)
  }

  const { data, error } = await q.order('fecha', { ascending: false })
  if (error) throw error
  return data ?? []
}

export async function getArchivosPorGasto(gastoId: string): Promise<ArchivoDrive[]> {
  const supabase = getSupabaseServer()
  const { data, error } = await supabase
    .from('archivos_drive')
    .select('*')
    .eq('gasto_id', gastoId)
    .order('created_at', { ascending: false })

  if (error) throw error
  return data ?? []
}

export async function contarArchivosPorGastos(gastoIds: string[]): Promise<Record<string, number>> {
  if (gastoIds.length === 0) return {}
  const supabase = getSupabaseServer()
  const { data, error } = await supabase
    .from('archivos_drive')
    .select('gasto_id')
    .in('gasto_id', gastoIds)

  if (error) throw error
  const counts: Record<string, number> = {}
  for (const row of data ?? []) {
    if (row.gasto_id) {
      counts[row.gasto_id] = (counts[row.gasto_id] ?? 0) + 1
    }
  }
  return counts
}
