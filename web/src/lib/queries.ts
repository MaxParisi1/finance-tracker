import { getSupabaseServer } from './supabase'
import type { Gasto, GastoRecurrente, Categoria, MensualResumen, TendenciaMes } from './types'
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
    .order('fecha', { ascending: false })
    .limit(limit)

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

  const por_categoria = [...porCategoria.entries()]
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

  return [...map.entries()]
    .map(([nombre, v]) => ({ nombre, total_ars: Math.round(v.total_ars), cantidad: v.cantidad }))
    .sort((a, b) => b.total_ars - a.total_ars)
    .slice(0, limite)
}

// ──────────────────────────────────────────────
// Tipo de cambio histórico
// ──────────────────────────────────────────────

export async function getLatestTipoCambio(tipo = 'blue'): Promise<number | null> {
  const supabase = getSupabaseServer()
  const { data } = await supabase
    .from('tipos_cambio_historico')
    .select('valor, fecha')
    .eq('tipo', tipo)
    .order('fecha', { ascending: false })
    .limit(1)

  return data?.[0]?.valor ?? null
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

  return [...map.entries()]
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

export interface RecurrenteConCosto extends GastoRecurrente {
  mensual_ars: number
  dias_para_vencimiento: number
}

export async function getRecurrentesConCosto(): Promise<{
  recurrentes: RecurrenteConCosto[]
  total_mensual_ars: number
  total_anual_ars: number
  tc_blue: number | null
}> {
  const [recurrentes, tc_blue] = await Promise.all([
    getRecurrentes(),
    getLatestTipoCambio('blue'),
  ])

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
  }
}
