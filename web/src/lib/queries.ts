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
  pagado: boolean
  fecha_pago?: string
  con_comprobante: boolean
  dias_para_vencimiento: number
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

/** Ocurrencia anterior a `p` según la frecuencia (proximo_vencimiento − 1 período). */
function ocurrenciaAnterior(p: Date, frecuencia: string): Date {
  if (frecuencia === 'anual') return new Date(p.getFullYear() - 1, p.getMonth(), p.getDate())
  if (frecuencia === 'semanal') return new Date(p.getTime() - 7 * 86400000)
  return new Date(p.getFullYear(), p.getMonth() - 1, p.getDate())
}

/**
 * Estado de los fijos (recurrentes) en un mes: cuáles ya pagaste y cuáles faltan.
 *
 * Se razona por ocurrencia usando `proximo_vencimiento` (la verdad de "qué es lo
 * próximo que se debe"), no por la fecha del pago — así un fijo que vencía el 1
 * de julio pero se pagó adelantado el 29 de junio cuenta como pagado de julio.
 *
 *  - Pendiente: proximo_vencimiento cae este mes o antes (se debe / vencido).
 *  - Pagado:    proximo_vencimiento ya pasó a un mes futuro y la ocurrencia
 *               anterior (proximo − 1 período) caía en este mes.
 *  - Se excluye lo que no tiene ocurrencia este mes (ej: un anual de diciembre).
 */
export async function getFijosDelMes(mes: number, anio: number): Promise<FijosDelMes> {
  const supabase = getSupabaseServer()
  const { desde, hasta } = monthRange(mes, anio) // 'YYYY-MM-01' inclusivo / exclusivo

  const [recurrentes, tcInfo] = await Promise.all([getRecurrentes(), getTipoCambioActual('oficial')])
  const tc = tcInfo?.valor ?? 1
  const toARS = (m: number, mon: string) => (mon === 'USD' ? Math.round(m * tc) : m)

  // Pagos vinculados en una ventana amplia (incluye pagos adelantados del mes previo).
  const ids = recurrentes.map(r => r.id)
  const ventanaDesde = new Date(anio, mes - 1, 1)
  ventanaDesde.setDate(ventanaDesde.getDate() - 62)
  const ventanaDesdeStr = ventanaDesde.toISOString().split('T')[0]

  const pagosPorRec = new Map<string, { fecha: string; gasto_id: string; monto_ars: number }[]>()
  if (ids.length > 0) {
    const { data: pagos } = await supabase
      .from('gastos')
      .select('id, recurrente_id, fecha, monto_ars')
      .in('recurrente_id', ids)
      .gte('fecha', ventanaDesdeStr)
      .lt('fecha', hasta)
      .is('deleted_at', null)
      .order('fecha', { ascending: false })
    for (const g of pagos ?? []) {
      if (!g.recurrente_id) continue
      const arr = pagosPorRec.get(g.recurrente_id) ?? []
      arr.push({ fecha: g.fecha, gasto_id: g.id, monto_ars: g.monto_ars ?? 0 })
      pagosPorRec.set(g.recurrente_id, arr)
    }
  }

  const hoy = new Date()
  hoy.setHours(0, 0, 0, 0)

  const pagados: FijoDelMes[] = []
  const pendientes: FijoDelMes[] = []
  const settlingGastoIds: string[] = []
  // { fijo, gasto_id } para resolver comprobantes en un segundo paso
  const comprobantePend: { f: FijoDelMes; gasto_id: string }[] = []

  for (const r of recurrentes) {
    const venc = new Date(r.proximo_vencimiento + 'T00:00:00')
    const dias = Math.round((venc.getTime() - hoy.getTime()) / 86400000)
    const base = {
      id: r.id,
      descripcion: r.descripcion,
      categoria: r.categoria,
      medio_pago: r.medio_pago,
      moneda: r.moneda,
      monto_original: r.monto_original,
      frecuencia: r.frecuencia,
      proximo_vencimiento: r.proximo_vencimiento,
      dias_para_vencimiento: dias,
    }

    if (r.proximo_vencimiento < hasta) {
      // Pendiente: vence este mes o está vencido.
      pendientes.push({
        ...base,
        monto_ars: toARS(r.monto_original, r.moneda),
        pagado: false,
        con_comprobante: false,
      })
      continue
    }

    // proximo ya pasó a un mes futuro → ¿la ocurrencia anterior era de este mes?
    const ult = ocurrenciaAnterior(venc, r.frecuencia)
    if (ult.getFullYear() === anio && ult.getMonth() + 1 === mes) {
      // Pagado este mes. El pago que lo saldó es el más reciente anterior a proximo.
      const settling = (pagosPorRec.get(r.id) ?? []).find(g => g.fecha < r.proximo_vencimiento)
      const f: FijoDelMes = {
        ...base,
        monto_ars: settling?.monto_ars ?? toARS(r.monto_original, r.moneda),
        pagado: true,
        fecha_pago: settling?.fecha,
        con_comprobante: false,
      }
      pagados.push(f)
      if (settling) {
        settlingGastoIds.push(settling.gasto_id)
        comprobantePend.push({ f, gasto_id: settling.gasto_id })
      }
    }
    // else: la ocurrencia no cae este mes → no pertenece al mes, se excluye.
  }

  // Resolver comprobantes de los pagos que saldaron cada fijo
  const comprobantes = await contarArchivosPorGastos(settlingGastoIds)
  for (const { f, gasto_id } of comprobantePend) {
    f.con_comprobante = (comprobantes[gasto_id] ?? 0) > 0
  }

  pendientes.sort((a, b) => a.proximo_vencimiento.localeCompare(b.proximo_vencimiento))
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
