import { getSupabaseServer } from './supabase'
import type { Gasto, GastoRecurrente, Categoria, MensualResumen, TendenciaMes, ArchivoDrive, PlanCuota } from './types'
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

export async function getAllComercios(): Promise<string[]> {
  const supabase = getSupabaseServer()
  const { data, error } = await supabase
    .from('gastos')
    .select('comercio')
    .is('deleted_at', null)
    .not('comercio', 'is', null)
    .order('comercio')
  if (error) throw error
  const unique = Array.from(new Set((data ?? []).map(r => r.comercio as string).filter(Boolean)))
  return unique.sort()
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
  ultimo_monto_original?: number
  ultimo_moneda?: string
}

export async function getRecurrentesConCosto(): Promise<{
  recurrentes: RecurrenteConCosto[]
  total_mensual_ars: number
  total_anual_ars: number
  tc_blue: number | null
  tc_fecha: string | null
  tc_es_hoy: boolean
}> {
  const supabase = getSupabaseServer()

  const [recurrentes, tcInfo] = await Promise.all([
    getRecurrentes(),
    getTipoCambioActual('oficial'),
  ])
  const tc_blue = tcInfo?.valor ?? null

  // Para recurrentes con no_materializar, traer el último gasto vinculado real
  const noMaterializarIds = recurrentes.filter(r => r.no_materializar).map(r => r.id)
  const ultimoMontoMap = new Map<string, { monto_original: number; moneda: string }>()

  if (noMaterializarIds.length > 0) {
    const { data: ultimosGastos } = await supabase
      .from('gastos')
      .select('recurrente_id, monto_original, moneda, fecha')
      .in('recurrente_id', noMaterializarIds)
      .is('deleted_at', null)
      .order('fecha', { ascending: false })

    for (const g of ultimosGastos ?? []) {
      if (g.recurrente_id && !ultimoMontoMap.has(g.recurrente_id)) {
        ultimoMontoMap.set(g.recurrente_id, {
          monto_original: g.monto_original,
          moneda: g.moneda,
        })
      }
    }
  }

  const hoy = new Date()

  const recurrentesConCosto: RecurrenteConCosto[] = recurrentes.map(r => {
    const ultimoGasto = r.no_materializar ? ultimoMontoMap.get(r.id) : undefined
    const monto = ultimoGasto?.monto_original ?? r.monto_original
    const moneda = ultimoGasto?.moneda ?? r.moneda
    const tc = tc_blue ?? 1
    const montoARS = moneda === 'USD' ? monto * tc : monto

    let mensual_ars: number
    if (r.frecuencia === 'anual') mensual_ars = Math.round(montoARS / 12)
    else if (r.frecuencia === 'semanal') mensual_ars = Math.round((montoARS * 52) / 12)
    else mensual_ars = Math.round(montoARS)

    const vencimiento = new Date(r.proximo_vencimiento + 'T00:00:00')
    const dias = Math.ceil((vencimiento.getTime() - hoy.getTime()) / (1000 * 60 * 60 * 24))

    return {
      ...r,
      mensual_ars,
      dias_para_vencimiento: dias,
      ...(ultimoGasto && {
        ultimo_monto_original: ultimoGasto.monto_original,
        ultimo_moneda: ultimoGasto.moneda,
      }),
    }
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
// Fijos del mes (estado de pagos: pagado vs pendiente)
// ──────────────────────────────────────────────

export interface FijoDelMes {
  id: string
  descripcion: string
  categoria: string
  medio_pago: string
  moneda: string
  monto_original: number
  monto_ars: number
  frecuencia: string
  proximo_vencimiento: string
  vencimiento: string // fecha de la ocurrencia en el mes (YYYY-MM-DD); '' si es sin día fija
  sin_dia: boolean    // mensual sin día fija (se paga en el mes, sin vencimiento en el calendario)
  pagado: boolean
  fecha_pago?: string
  con_comprobante: boolean
  dias_para_vencimiento: number
  siguiente_pagado: boolean // mensual: el mes siguiente ya tiene un pago mapeado (adelanto hecho)
  desde_factura: boolean    // monto y vencimiento vienen de la factura del mes, no de la estimación
}

export interface FijosDelMes {
  pendientes: FijoDelMes[]
  pagados: FijoDelMes[]
  count_total: number
  count_pagados: number
  total_pendiente_ars: number
  total_pagado_ars: number
  total_mes_ars: number
  proximo_dias: number | null
  pct_pagado: number
}

const pad2 = (n: number) => String(n).padStart(2, '0')
const DAY = 86400000
const monthKey = (anio: number, mes: number) => `${anio}-${pad2(mes)}`

/** Ancla día-D de un mes, clampeando al último día. */
function anclaDia(anio: number, mesIdx0: number, dia: number): Date {
  const last = new Date(anio, mesIdx0 + 1, 0).getDate()
  return new Date(anio, mesIdx0, Math.min(dia, last))
}

/**
 * A qué mes (YYYY-MM) corresponde un pago mensual. Regla: el mes CALENDARIO del
 * pago — porque `dia_del_mes` suele ser poco confiable (ej: Mapfre figura día 30
 * pero se cobra a principio de mes). Única excepción: un pago en los últimos días
 * del mes de un fijo de principio de mes es un adelanto del mes siguiente
 * (ej: AySA día 1 pagado el 29-jun cuenta para julio). Cada pago cuenta 1 sola vez.
 */
function mesDelPagoMensual(fecha: string, dia: number): string {
  const [fy, fm, fd] = fecha.split('-').map(Number)
  const ultimoDia = new Date(fy, fm, 0).getDate()
  if (dia <= 10 && fd >= ultimoDia - 3) {
    // Adelanto del mes siguiente
    const sig = new Date(fy, fm, 1) // primero del mes siguiente
    return monthKey(sig.getFullYear(), sig.getMonth() + 1)
  }
  return monthKey(fy, fm)
}

/**
 * Ocurrencia (fecha de vencimiento) de un fijo en el mes/año dado.
 * `belongs=false` cuando el fijo no tiene ocurrencia en ese mes (ej: un anual de otro mes).
 */
function ocurrenciaDelMes(r: GastoRecurrente, mes: number, anio: number): { belongs: boolean; occ: string } {
  const [, pm, pd] = r.proximo_vencimiento.split('-').map(Number)
  // Mensual sin día fija → pertenece a todos los meses, sin fecha de vencimiento.
  if (r.frecuencia === 'mensual' && r.dia_del_mes == null) return { belongs: true, occ: '' }
  // Anual sin día fija → pertenece solo a su mes aniversario (el de proximo_vencimiento).
  if (r.frecuencia === 'anual' && r.dia_del_mes == null) return { belongs: pm === mes, occ: '' }
  const dia = r.dia_del_mes || pd || 1
  if (r.frecuencia === 'anual') {
    const a = anclaDia(anio, mes - 1, dia)
    return { belongs: pm === mes, occ: `${a.getFullYear()}-${pad2(a.getMonth() + 1)}-${pad2(a.getDate())}` }
  }
  const a = anclaDia(anio, mes - 1, r.frecuencia === 'semanal' ? 28 : dia)
  return { belongs: true, occ: `${a.getFullYear()}-${pad2(a.getMonth() + 1)}-${pad2(a.getDate())}` }
}

/**
 * Estado de los fijos (recurrentes) en un mes: cuáles ya pagaste y cuáles faltan.
 *
 * Clasificación por PAGOS REALES vinculados, no por `proximo_vencimiento` (que
 * puede desalinearse). Cada pago se mapea a una única ocurrencia:
 *  - Mensual: el pago cuenta para el mes cuyo día-D está más cerca de la fecha
 *    del pago (así un pago adelantado del 29-jun cuenta para julio, y un único
 *    pago no se atribuye a dos meses).
 *  - Anual/semanal: pago dentro de ±30 días de la ocurrencia.
 * Pagado = hay un pago mapeado a este mes. Pendiente = pertenece al mes y no hay pago.
 */
export async function getFijosDelMes(mes: number, anio: number): Promise<FijosDelMes> {
  const supabase = getSupabaseServer()

  const [recurrentes, tcInfo] = await Promise.all([getRecurrentes(), getTipoCambioActual('oficial')])
  const tc = tcInfo?.valor ?? 1
  const toARS = (m: number, mon: string) => (mon === 'USD' ? Math.round(m * tc) : m)

  // Pagos vinculados en una ventana que rodea el mes (capta adelantados y atrasados).
  const ids = recurrentes.map(r => r.id)
  const wDesde = new Date(anio, mes - 1, 1); wDesde.setDate(wDesde.getDate() - 45)
  const wHasta = new Date(anio, mes, 1); wHasta.setDate(wHasta.getDate() + 45)
  const toStr = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`

  const pagosPorRec = new Map<string, { fecha: string; gasto_id: string; monto_ars: number }[]>()
  if (ids.length > 0) {
    const { data: pagos } = await supabase
      .from('gastos')
      .select('id, recurrente_id, fecha, monto_ars')
      .in('recurrente_id', ids)
      .gte('fecha', toStr(wDesde))
      .lt('fecha', toStr(wHasta))
      .is('deleted_at', null)
    for (const g of pagos ?? []) {
      if (!g.recurrente_id) continue
      const arr = pagosPorRec.get(g.recurrente_id) ?? []
      arr.push({ fecha: g.fecha, gasto_id: g.id, monto_ars: g.monto_ars ?? 0 })
      pagosPorRec.set(g.recurrente_id, arr)
    }
  }

  const keyMes = monthKey(anio, mes)
  const nextMes = mes === 12 ? 1 : mes + 1
  const nextAnio = mes === 12 ? anio + 1 : anio
  const keyMesSig = monthKey(nextAnio, nextMes)
  // ¿El mes siguiente ya tiene un pago mapeado? (adelanto ya hecho). Solo mensual.
  const siguientePagado = (r: GastoRecurrente) => {
    if (r.frecuencia !== 'mensual') return false
    const dia = r.dia_del_mes ?? 1
    return (pagosPorRec.get(r.id) ?? []).some(g => mesDelPagoMensual(g.fecha, dia) === keyMesSig)
  }
  // Facturas cuyo vencimiento cae en el mes. Son la autoridad sobre el monto: es
  // lo que el proveedor emitió, contra `monto_original`, que es lo que se pagó la
  // última vez y sólo se actualiza al vincular un pago. Sin esto, Fijos mostraba
  // el importe del mes anterior hasta que pagabas.
  const facturaPorRec = new Map<string, { monto: number; vencimiento: string }>()
  const { data: facturasMes } = await supabase
    .from('facturas')
    .select('monto, vencimiento, servicios!inner(recurrente_id)')
    .gte('vencimiento', `${anio}-${pad2(mes)}-01`)
    .lt('vencimiento', `${nextAnio}-${pad2(nextMes)}-01`)
  for (const f of facturasMes ?? []) {
    const recId = (f.servicios as unknown as { recurrente_id: string | null })?.recurrente_id
    if (!recId) continue
    // Si un servicio emitió más de una en el mes, gana la que vence primero.
    const previa = facturaPorRec.get(recId)
    if (previa && previa.vencimiento <= f.vencimiento) continue
    facturaPorRec.set(recId, { monto: Number(f.monto), vencimiento: f.vencimiento })
  }

  const hoy = new Date(); hoy.setHours(0, 0, 0, 0)
  const diasHasta = (fecha: string) => Math.round((new Date(fecha + 'T00:00:00').getTime() - hoy.getTime()) / DAY)

  // Pago que salda la ocurrencia de este mes (o undefined).
  const pagoDelMes = (r: GastoRecurrente, occ: string) => {
    const pagos = pagosPorRec.get(r.id) ?? []
    if (r.frecuencia === 'mensual') {
      // Sin día usa día-1 nominal → los últimos días del mes cuentan para el siguiente
      // (pago adelantado, ej: AySA pagado el 30-jun cuenta para julio).
      const dia = r.dia_del_mes ?? 1
      return pagos.find(g => mesDelPagoMensual(g.fecha, dia) === keyMes)
    }
    if (r.frecuencia === 'anual' && r.dia_del_mes == null) {
      // Anual sin día: mismo mes calendario y año.
      return pagos.find(g => g.fecha.slice(0, 7) === keyMes)
    }
    const occT = new Date(occ + 'T00:00:00').getTime()
    return pagos.find(g => Math.abs(new Date(g.fecha + 'T00:00:00').getTime() - occT) <= 30 * DAY)
  }

  const pagados: FijoDelMes[] = []
  const pendientes: FijoDelMes[] = []
  const comprobantePend: { f: FijoDelMes; gasto_id: string }[] = []

  for (const r of recurrentes) {
    const { belongs, occ } = ocurrenciaDelMes(r, mes, anio)
    if (!belongs) continue

    const base = {
      id: r.id,
      descripcion: r.descripcion,
      categoria: r.categoria,
      medio_pago: r.medio_pago,
      moneda: r.moneda,
      monto_original: r.monto_original,
      frecuencia: r.frecuencia,
      proximo_vencimiento: r.proximo_vencimiento,
    }

    const sinDiaNominal = r.dia_del_mes == null && (r.frecuencia === 'mensual' || r.frecuencia === 'anual')

    // Con factura del mes tenemos fecha exacta: deja de ser un fijo "sin día".
    const fact = facturaPorRec.get(r.id)
    const sinDia = fact ? false : sinDiaNominal
    const venc = fact ? fact.vencimiento : occ
    const dias = fact ? diasHasta(fact.vencimiento) : (sinDiaNominal ? 999 : diasHasta(occ))

    // El matching de pagos sigue usando `occ`: la ventana nominal es la que mapea
    // un pago a su mes, y cambiarla acá movería fijos ya saldados de lugar.
    const pago = pagoDelMes(r, occ)
    if (pago) {
      const f: FijoDelMes = {
        ...base,
        vencimiento: venc,
        sin_dia: sinDia,
        // Pagado: manda lo que efectivamente pagaste, no lo que decía la factura.
        monto_ars: pago.monto_ars || toARS(r.monto_original, r.moneda),
        pagado: true,
        fecha_pago: pago.fecha,
        con_comprobante: false,
        dias_para_vencimiento: dias,
        siguiente_pagado: siguientePagado(r),
        desde_factura: !!fact,
      }
      pagados.push(f)
      comprobantePend.push({ f, gasto_id: pago.gasto_id })
    } else {
      // Si el fijo se creó después de la ocurrencia, no lo debías ese mes.
      const creado = (r.created_at ?? '').split('T')[0]
      if (creado) {
        if (sinDiaNominal) { if (creado.slice(0, 7) > keyMes) continue }
        else if (occ < creado) continue
      }
      pendientes.push({
        ...base,
        vencimiento: venc,
        sin_dia: sinDia,
        monto_ars: fact ? fact.monto : toARS(r.monto_original, r.moneda),
        pagado: false,
        con_comprobante: false,
        desde_factura: !!fact,
        dias_para_vencimiento: dias,
        siguiente_pagado: false,
      })
    }
  }

  // Resolver comprobantes de los pagos que saldaron cada fijo
  const comprobantes = await contarArchivosPorGastos(comprobantePend.map(c => c.gasto_id))
  for (const { f, gasto_id } of comprobantePend) {
    f.con_comprobante = (comprobantes[gasto_id] ?? 0) > 0
  }

  pendientes.sort((a, b) => a.dias_para_vencimiento - b.dias_para_vencimiento)
  pagados.sort((a, b) => (b.fecha_pago ?? '').localeCompare(a.fecha_pago ?? ''))

  const total_pendiente_ars = pendientes.reduce((s, f) => s + f.monto_ars, 0)
  const total_pagado_ars = pagados.reduce((s, f) => s + f.monto_ars, 0)
  const count_total = pendientes.length + pagados.length

  return {
    pendientes,
    pagados,
    count_total,
    count_pagados: pagados.length,
    total_pendiente_ars,
    total_pagado_ars,
    total_mes_ars: total_pendiente_ars + total_pagado_ars,
    proximo_dias: pendientes.length ? pendientes[0].dias_para_vencimiento : null,
    pct_pagado: count_total ? Math.round((pagados.length / count_total) * 100) : 0,
  }
}

// ──────────────────────────────────────────────
// Agenda / "Lo que viene" (fijos + cuotas por fecha)
// ──────────────────────────────────────────────

export interface Obligacion {
  fecha: string        // para sin_fecha: último día del mes (solo para ordenar/agrupar, no se ubica en el calendario)
  sin_fecha: boolean
  titulo: string
  subtitulo: string
  monto_ars: number
  moneda: string
  monto_original: number
  tipo: 'fijo' | 'cuota'
  estado: 'pendiente' | 'pagado'
  recurrente_id?: string
}

/** Obligaciones de este mes y el próximo (fijos + cuotas), ordenadas por fecha. */
export async function getAgenda(): Promise<Obligacion[]> {
  const hoy = new Date()
  const mes = hoy.getMonth() + 1
  const anio = hoy.getFullYear()
  const nMes = mes === 12 ? 1 : mes + 1
  const nAnio = mes === 12 ? anio + 1 : anio

  const [f1, f2, cuotas, planes] = await Promise.all([
    getFijosDelMes(mes, anio),
    getFijosDelMes(nMes, nAnio),
    getCuotasActivas(),
    getPlanesCuotaActivos(),
  ])

  const obs: Obligacion[] = []
  const finDeMes = (m: number, a: number) => `${a}-${pad2(m)}-${pad2(new Date(a, m, 0).getDate())}`
  const pushFijos = (set: FijosDelMes, m: number, a: number) => {
    for (const f of [...set.pendientes, ...set.pagados]) {
      obs.push({
        fecha: f.sin_dia ? finDeMes(m, a) : f.vencimiento,
        sin_fecha: f.sin_dia,
        titulo: f.descripcion,
        subtitulo: f.categoria ?? 'Fijo',
        monto_ars: f.monto_ars,
        moneda: f.moneda,
        monto_original: f.monto_original,
        tipo: 'fijo',
        estado: f.pagado ? 'pagado' : 'pendiente',
        recurrente_id: f.id,
      })
    }
  }
  pushFijos(f1, mes, anio)
  pushFijos(f2, nMes, nAnio)

  for (const c of cuotas) {
    obs.push({
      fecha: c.proxima_fecha, sin_fecha: false,
      titulo: c.comercio || c.descripcion,
      subtitulo: `Cuota ${c.cuota_pendiente}/${c.cuotas}`,
      monto_ars: c.monto_ars, moneda: c.moneda, monto_original: c.monto_original,
      tipo: 'cuota', estado: 'pendiente',
    })
  }
  for (const p of planes) {
    obs.push({
      fecha: p.proximo_vencimiento, sin_fecha: false,
      titulo: p.descripcion,
      subtitulo: `Cuota ${p.cuota_actual}/${p.cuotas_total}`,
      monto_ars: p.monto_cuota ?? 0, moneda: p.moneda, monto_original: p.monto_cuota ?? 0,
      tipo: 'cuota', estado: 'pendiente',
    })
  }
  return obs.sort((a, b) => a.fecha.localeCompare(b.fecha))
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

  function applyFilters(q: any) {
    if (filtros?.comercio) q = q.ilike('comercio', `%${filtros.comercio}%`)
    if (filtros?.categoria) q = q.eq('categoria', filtros.categoria)
    if (filtros?.tipo) q = q.eq('tipo', filtros.tipo)
    return q
  }

  // Sin filtro de fecha: devolver todos con los filtros de metadata
  if (!filtros?.mes || !filtros?.anio) {
    const range = filtros?.anio
      ? { desde: `${filtros.anio}-01-01`, hasta: `${filtros.anio + 1}-01-01` }
      : null
    let q = supabase.from('archivos_drive').select('*')
    if (range) q = q.gte('fecha', range.desde).lt('fecha', range.hasta)
    q = applyFilters(q)
    const { data, error } = await q.order('fecha', { ascending: false })
    if (error) throw error
    return data ?? []
  }

  const { desde, hasta } = monthRange(filtros.mes, filtros.anio)

  // Query 1: archivos cuya propia fecha cae en el mes
  const q1 = applyFilters(
    supabase.from('archivos_drive').select('*').gte('fecha', desde).lt('fecha', hasta)
  )

  // Query 2: archivos vinculados a gastos cuya fecha cae en el mes
  // (cubre el caso donde el gasto fue editado a un mes diferente al de subida)
  const { data: gastosDelMes } = await supabase
    .from('gastos')
    .select('id')
    .gte('fecha', desde)
    .lt('fecha', hasta)
    .is('deleted_at', null)

  const gastoIds = (gastosDelMes ?? []).map((g: { id: string }) => g.id)

  const q2Promise = gastoIds.length > 0
    ? applyFilters(supabase.from('archivos_drive').select('*').in('gasto_id', gastoIds))
        .then((r: any) => r.data ?? [])
    : Promise.resolve([] as ArchivoDrive[])

  const [r1, r2] = await Promise.all([
    q1.then((r: any) => { if (r.error) throw r.error; return r.data ?? [] }),
    q2Promise,
  ])

  // Merge deduplicando por id, ordenar por fecha descendente
  const seen = new Set<string>()
  const merged: ArchivoDrive[] = []
  for (const a of [...r1, ...r2]) {
    if (!seen.has(a.id)) {
      seen.add(a.id)
      merged.push(a)
    }
  }
  return merged.sort((a, b) => b.fecha.localeCompare(a.fecha))
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

// ──────────────────────────────────────────────
// Planes de cuota
// ──────────────────────────────────────────────

export async function getPlanesCuota(): Promise<PlanCuota[]> {
  const supabase = getSupabaseServer()
  const { data, error } = await supabase
    .from('planes_cuota')
    .select('*')
    .order('proximo_vencimiento', { ascending: true })
  if (error) throw error
  return data ?? []
}

export async function getPlanesCuotaActivos(): Promise<PlanCuota[]> {
  const supabase = getSupabaseServer()
  const { data, error } = await supabase
    .from('planes_cuota')
    .select('*')
    .eq('activo', true)
    .order('proximo_vencimiento', { ascending: true })
  if (error) throw error
  return data ?? []
}

// ──────────────────────────────────────────────

// ──────────────────────────────────────────────
// Histórico multi-mes
// ──────────────────────────────────────────────

export interface HistoricoMes {
  mes: number
  anio: number
  label: string
  total_ars: number
  cantidad: number
}

export async function getGastosHistorico(filtros: {
  desde: string
  hasta: string
  busqueda?: string
  categoria?: string
  medio_pago?: string
}): Promise<{ meses: HistoricoMes[]; gastos: Gasto[] }> {
  const supabase = getSupabaseServer()

  let q = supabase
    .from('gastos')
    .select('*')
    .is('deleted_at', null)
    .gte('fecha', filtros.desde)
    .lt('fecha', filtros.hasta)
    .order('fecha', { ascending: false })

  if (filtros.busqueda) {
    q = q.or(`descripcion.ilike.%${filtros.busqueda}%,comercio.ilike.%${filtros.busqueda}%`)
  }
  if (filtros.categoria) q = q.eq('categoria', filtros.categoria)
  if (filtros.medio_pago) q = q.eq('medio_pago', filtros.medio_pago)

  const { data, error } = await q
  if (error) throw error
  const gastos: Gasto[] = data ?? []

  const mesMap = new Map<string, HistoricoMes>()
  for (const g of gastos) {
    const parts = g.fecha.split('-')
    const anio = parseInt(parts[0])
    const mes = parseInt(parts[1])
    const key = `${anio}-${mes}`
    if (!mesMap.has(key)) {
      mesMap.set(key, { mes, anio, label: monthLabel(mes, anio), total_ars: 0, cantidad: 0 })
    }
    const entry = mesMap.get(key)!
    entry.total_ars += g.monto_ars ?? 0
    entry.cantidad += 1
  }

  const meses = Array.from(mesMap.values())
    .map(m => ({ ...m, total_ars: Math.round(m.total_ars) }))
    .sort((a, b) => a.anio !== b.anio ? a.anio - b.anio : a.mes - b.mes)

  return { meses, gastos }
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

// ──────────────────────────────────────────────
// Registro de facturas (grilla de auditoría)
// ──────────────────────────────────────────────

export interface CeldaRegistro {
  factura_id: string
  borrador_consorcio: boolean
  monto: number
  vencimiento: string
  estado: 'pendiente' | 'pagada' | 'anulada'
  con_factura: boolean
  con_comprobante: boolean
  link_factura: string | null
  link_comprobante: string | null
}

export interface FilaRegistro {
  servicio_id: string
  slug: string
  nombre: string
  celdas: Record<string, CeldaRegistro>   // key: 'YYYY-MM' del vencimiento
  completas: number
  esperadas: number
}

export interface Registro {
  anio: number
  meses: string[]
  filas: FilaRegistro[]
  total_celdas: number
  celdas_completas: number
  pct_completo: number
}

/**
 * Grilla servicios × meses para verificar que el archivo esté completo.
 *
 * Una celda está completa cuando la factura está pagada Y tiene los dos PDFs
 * (factura y comprobante). Eso es lo que hace verificable el "registro total":
 * no alcanza con que la contabilidad cierre, tiene que estar el respaldo.
 */
export async function getRegistro(anio: number): Promise<Registro> {
  const supabase = getSupabaseServer()

  const [{ data: servicios }, { data: facturas }] = await Promise.all([
    supabase.from('servicios').select('id, slug, nombre').eq('activo', true).order('nombre'),
    supabase
      .from('facturas')
      .select('id, servicio_id, monto, vencimiento, estado, borrador_consorcio_at, archivos_drive(tipo, drive_web_view_link)')
      .neq('estado', 'anulada')
      .gte('vencimiento', `${anio}-01-01`)
      .lte('vencimiento', `${anio}-12-31`),
  ])

  const meses = Array.from({ length: 12 }, (_, i) => `${anio}-${pad2(i + 1)}`)
  const hoy = new Date()
  const mesActual = `${hoy.getFullYear()}-${pad2(hoy.getMonth() + 1)}`

  const filas: FilaRegistro[] = (servicios ?? []).map(s => {
    const celdas: Record<string, CeldaRegistro> = {}

    for (const f of facturas ?? []) {
      if (f.servicio_id !== s.id) continue
      const key = String(f.vencimiento).slice(0, 7)
      const archivos = (f.archivos_drive ?? []) as { tipo: string; drive_web_view_link: string | null }[]
      const factura = archivos.find(a => a.tipo === 'factura')
      const comprobante = archivos.find(a => a.tipo === 'comprobante')

      celdas[key] = {
        factura_id: f.id,
        borrador_consorcio: Boolean(f.borrador_consorcio_at),
        monto: Number(f.monto ?? 0),
        vencimiento: String(f.vencimiento),
        estado: f.estado,
        con_factura: Boolean(factura),
        con_comprobante: Boolean(comprobante),
        link_factura: factura?.drive_web_view_link ?? null,
        link_comprobante: comprobante?.drive_web_view_link ?? null,
      }
    }

    // Solo se cuentan como "esperadas" las celdas que ya existen: no sabemos de
    // antemano si un servicio factura todos los meses (AySA puede ser bimestral).
    const existentes = Object.values(celdas)
    const completas = existentes.filter(
      c => c.estado === 'pagada' && c.con_factura && c.con_comprobante,
    ).length

    return {
      servicio_id: s.id,
      slug: s.slug,
      nombre: s.nombre,
      celdas,
      completas,
      esperadas: existentes.length,
    }
  })

  const total_celdas = filas.reduce((n, f) => n + f.esperadas, 0)
  const celdas_completas = filas.reduce((n, f) => n + f.completas, 0)

  // Los meses futuros se ocultan para no mostrar columnas vacías, pero un mes con
  // factura ya emitida no es futuro para el registro: el aviso llegó y el PDF
  // puede estar archivado. Sin esto, una factura de septiembre cargada en agosto
  // quedaba invisible hasta que cambiara el mes.
  const conFacturas = new Set(filas.flatMap(f => Object.keys(f.celdas)))

  return {
    anio,
    meses: meses.filter(
      m => anio < hoy.getFullYear() || m <= mesActual || conFacturas.has(m),
    ),
    filas,
    total_celdas,
    celdas_completas,
    pct_completo: total_celdas ? Math.round((celdas_completas / total_celdas) * 100) : 0,
  }
}
