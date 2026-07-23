import Sidebar from '@/components/Sidebar'
import ExpenseTable from '@/components/ExpenseTable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BlurFade } from '@/components/magicui/blur-fade'
import {
  getResumenMes, getGastosRecientes, getCategorias, getRecurrentesConCosto,
  getCuotasActivas, getPlanesCuotaActivos, getFijosDelMes, type FijoDelMes,
} from '@/lib/queries'
import { formatARS, monthLabel, cn } from '@/lib/utils'

export const dynamic = 'force-dynamic'

/** Texto + tono del chip de vencimiento de un fijo pendiente. */
function vencInfo(dias: number): { label: string; tone: 'crit' | 'warn' | 'muted' } {
  if (dias < 0) return { label: `vencido hace ${Math.abs(dias)}d`, tone: 'crit' }
  if (dias === 0) return { label: '¡vence hoy!', tone: 'crit' }
  if (dias === 1) return { label: 'vence mañana', tone: 'warn' }
  if (dias <= 5) return { label: `en ${dias} días`, tone: 'warn' }
  return { label: `en ${dias} días`, tone: 'muted' }
}

const chipTone: Record<string, string> = {
  crit: 'bg-destructive/12 text-destructive',
  warn: 'bg-warning/15 text-warning',
  muted: 'bg-muted text-muted-foreground',
}
const stripeTone: Record<string, string> = {
  crit: 'bg-destructive',
  warn: 'bg-warning',
  muted: 'bg-muted-foreground/40',
}

function montoFijo(f: FijoDelMes): string {
  return f.moneda === 'USD' ? `US$ ${f.monto_original.toLocaleString('es-AR')}` : formatARS(f.monto_original)
}

export default async function DashboardPage() {
  const hoy = new Date()
  const mes = hoy.getMonth() + 1
  const anio = hoy.getFullYear()
  const mesAnterior = mes === 1 ? 12 : mes - 1
  const anioAnterior = mes === 1 ? anio - 1 : anio

  const categorias = await getCategorias()
  const [resumenActual, resumenAnterior, recientes, recurrentes, cuotasActivas, planesCuota, fijos] =
    await Promise.all([
      getResumenMes(mes, anio, categorias),
      getResumenMes(mesAnterior, anioAnterior, categorias),
      getGastosRecientes(10),
      getRecurrentesConCosto(),
      getCuotasActivas(),
      getPlanesCuotaActivos(),
      getFijosDelMes(mes, anio),
    ])
  const tcBlue = recurrentes.tc_blue

  const variacion =
    resumenAnterior.total_ars > 0
      ? Math.round(((resumenActual.total_ars - resumenAnterior.total_ars) / resumenAnterior.total_ars) * 1000) / 10
      : null

  const diasTranscurridos = hoy.getDate()
  const diasTotales = new Date(anio, mes, 0).getDate()
  const promedioDiario = diasTranscurridos > 0 ? resumenActual.total_ars / diasTranscurridos : 0
  const proyeccion = Math.round(promedioDiario * diasTotales)
  const equivalenteUSD = tcBlue && resumenActual.total_ars > 0 ? Math.round(resumenActual.total_ars / tcBlue) : null

  // Distribución por categoría con bucket "Otras"
  const TOP_N = 6
  const catTop = resumenActual.por_categoria.slice(0, TOP_N)
  const catResto = resumenActual.por_categoria.slice(TOP_N)
  const categoriasVista = catResto.length > 0
    ? [...catTop, {
        categoria: 'Otras categorías',
        total_ars: catResto.reduce((s, c) => s + c.total_ars, 0),
        cantidad: catResto.reduce((s, c) => s + c.cantidad, 0),
        color: '#9E9E9E',
      }]
    : catTop

  const proxTexto =
    fijos.proximo_dias == null ? null
    : fijos.proximo_dias < 0 ? `hay ${fijos.pendientes.filter(p => p.dias_para_vencimiento < 0).length} vencido(s)`
    : fijos.proximo_dias === 0 ? 'el más próximo vence hoy'
    : fijos.proximo_dias === 1 ? 'el más próximo vence mañana'
    : `el más próximo vence en ${fijos.proximo_dias} días`

  return (
    <div className="flex min-h-screen">
      <Sidebar pendientes={fijos.pendientes.length} />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          <div className="mb-6">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">Panel</h1>
            <p className="text-muted-foreground text-sm mt-1">{monthLabel(mes, anio)} · día {diasTranscurridos} de {diasTotales}</p>
          </div>

          {/* HERO: estado de pagos + categorías */}
          <BlurFade delay={0} className="grid grid-cols-1 lg:grid-cols-5 gap-5 mb-5">
            {/* Estado de pagos del mes */}
            <Card className="lg:col-span-3">
              <CardContent className="p-6">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Fijos de {MONTH_SHORT[mes - 1]} · lo que estás gestionando
                </p>
                <div className="flex items-center gap-6 mt-4 flex-wrap">
                  <Ring pct={fijos.pct_pagado} pagados={fijos.count_pagados} total={fijos.count_total} />
                  <div className="min-w-0">
                    {fijos.pendientes.length > 0 ? (
                      <>
                        <div className="font-display text-[2.4rem] leading-none tracking-tight text-foreground tabular">
                          {formatARS(fijos.total_pendiente_ars)}
                        </div>
                        <p className="text-sm text-muted-foreground mt-2 max-w-[34ch]">
                          te faltan pagar <b className="text-foreground font-semibold">{fijos.pendientes.length} fijo{fijos.pendientes.length > 1 ? 's' : ''}</b>
                          {proxTexto ? ` · ${proxTexto}` : ''}
                        </p>
                      </>
                    ) : (
                      <>
                        <div className="font-display text-[2.4rem] leading-none tracking-tight text-success">Al día ✓</div>
                        <p className="text-sm text-muted-foreground mt-2 max-w-[34ch]">
                          pagaste los {fijos.count_total} fijos de este mes
                        </p>
                      </>
                    )}
                  </div>
                </div>

                {/* Supporting stats */}
                <div className="flex flex-wrap gap-x-8 gap-y-3 mt-6 pt-5 border-t border-border">
                  <Stat k="Gastado en el mes" v={formatARS(resumenActual.total_ars)}
                    extra={variacion != null ? <Delta v={variacion} /> : null} />
                  <Stat k="Proyección fin de mes" v={formatARS(proyeccion)} />
                  {equivalenteUSD !== null && <Stat k="Equivalente USD oficial" v={`US$ ${equivalenteUSD.toLocaleString('es-AR')}`} />}
                </div>
              </CardContent>
            </Card>

            {/* En qué se te va */}
            <Card className="lg:col-span-2">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">En qué se te va</CardTitle>
                  <a href="/analytics" className="text-xs text-primary hover:opacity-80 font-medium">Ver análisis →</a>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                {categoriasVista.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4">Sin gastos este mes.</p>
                ) : (
                  <div className="space-y-3">
                    {categoriasVista.map(cat => {
                      const pct = resumenActual.total_ars > 0 ? Math.round((cat.total_ars / resumenActual.total_ars) * 100) : 0
                      return (
                        <div key={cat.categoria}>
                          <div className="flex justify-between text-[13px] mb-1.5">
                            <span className="flex items-center gap-2 text-foreground/80">
                              <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: cat.color ?? '#9E9E9E' }} />
                              {cat.categoria}
                            </span>
                            <span className="font-medium text-foreground tabular">
                              {formatARS(cat.total_ars)} <span className="text-muted-foreground font-normal">{pct}%</span>
                            </span>
                          </div>
                          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: cat.color ?? '#9E9E9E' }} />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </BlurFade>

          {/* FALTA PAGAR */}
          {(fijos.pendientes.length > 0 || fijos.pagados.length > 0) && (
            <BlurFade delay={0.06}>
              <Card className="mb-5">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">Falta pagar este mes</CardTitle>
                    <a href="/recurrentes" className="text-sm text-primary hover:opacity-80 font-medium">Gestionar fijos →</a>
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  {fijos.pendientes.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-2">
                      No te queda nada por pagar este mes. 🎉
                    </p>
                  ) : (
                    <div className="divide-y divide-border/70">
                      {fijos.pendientes.map(f => {
                        const info = vencInfo(f.dias_para_vencimiento)
                        return (
                          <div key={f.id} className="flex items-center gap-3 py-3">
                            <span className={cn('w-[3px] self-stretch rounded-full', stripeTone[info.tone])} />
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium text-foreground leading-tight truncate">{f.descripcion}</p>
                              <p className="text-xs text-muted-foreground mt-0.5">
                                {f.categoria} · {f.medio_pago.replace('_', ' ')}
                              </p>
                            </div>
                            <span className={cn('text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap', chipTone[info.tone])}>
                              {info.label}
                            </span>
                            <span className="text-sm font-semibold text-foreground tabular whitespace-nowrap w-24 text-right">
                              {montoFijo(f)}
                            </span>
                            <a href="/recurrentes" className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:opacity-90 whitespace-nowrap">
                              Pagar
                            </a>
                          </div>
                        )
                      })}
                    </div>
                  )}
                  {fijos.pagados.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-border text-xs text-muted-foreground">
                      <span className="text-success font-semibold">✓ {fijos.count_pagados} pagado{fijos.count_pagados > 1 ? 's' : ''}</span>
                      {' · '}{formatARS(fijos.total_pagado_ars)}
                      {' · '}
                      <span className="text-foreground/70">
                        {fijos.pagados.slice(0, 6).map(f => `${f.descripcion}${f.con_comprobante ? ' 📎' : ''}`).join(' · ')}
                        {fijos.pagados.length > 6 ? ` +${fijos.pagados.length - 6}` : ''}
                      </span>
                    </div>
                  )}
                </CardContent>
              </Card>
            </BlurFade>
          )}

          {/* Cuotas activas */}
          {(cuotasActivas.length > 0 || planesCuota.length > 0) && (
            <BlurFade delay={0.12}>
              <Card className="mb-5">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">Cuotas activas</CardTitle>
                    <a href="/cuotas" className="text-sm text-primary hover:opacity-80 font-medium">Ver planes →</a>
                  </div>
                </CardHeader>
                <div className="divide-y divide-border/70">
                  {planesCuota.map(p => {
                    const pct = Math.round(((p.cuota_actual - 1) / p.cuotas_total) * 100)
                    const proximoPago = new Date(p.proximo_vencimiento + 'T00:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })
                    return (
                      <div key={p.id} className="px-5 py-4">
                        <div className="flex items-start justify-between gap-4 mb-2">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-foreground truncate">{p.descripcion}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">
                              Cuota {p.cuota_actual} de {p.cuotas_total} · próx. {proximoPago} ·{' '}
                              <span className={p.tipo === 'fijo' ? 'text-success' : 'text-warning'}>
                                {p.tipo === 'fijo' ? 'sin interés' : 'con interés'}
                              </span>
                            </p>
                          </div>
                          <span className="text-sm font-semibold text-foreground whitespace-nowrap tabular">
                            {p.tipo === 'fijo' && p.monto_cuota != null
                              ? (p.moneda === 'USD' ? `US$ ${p.monto_cuota}` : formatARS(p.monto_cuota)) + '/mes'
                              : <span className="text-muted-foreground font-normal text-xs">variable</span>}
                          </span>
                        </div>
                        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                          <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    )
                  })}
                  {cuotasActivas.map((c, i) => {
                    const pct = Math.round(((c.cuota_pendiente - 1) / c.cuotas) * 100)
                    const proximoPago = new Date(c.proxima_fecha + 'T00:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })
                    const fechaFin = new Date(c.fecha_fin + 'T00:00:00').toLocaleDateString('es-AR', { month: 'short', year: 'numeric' })
                    return (
                      <div key={i} className="px-5 py-4">
                        <div className="flex items-start justify-between gap-4 mb-2">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-foreground truncate">{c.comercio || c.descripcion}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">
                              Cuota {c.cuota_pendiente} de {c.cuotas} · próx. {proximoPago} · termina {fechaFin}
                            </p>
                          </div>
                          <span className="text-sm font-semibold text-foreground whitespace-nowrap tabular">
                            {c.moneda === 'USD' ? `US$ ${c.monto_original}` : formatARS(c.monto_ars)}/mes
                          </span>
                        </div>
                        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                          <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </Card>
            </BlurFade>
          )}

          {/* Últimos gastos */}
          <BlurFade delay={0.18}>
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Últimos gastos</CardTitle>
                  <a href="/gastos" className="text-sm text-primary hover:opacity-80 font-medium">Ver todos →</a>
                </div>
              </CardHeader>
              <CardContent className="pt-0 px-0 pb-0">
                <ExpenseTable gastos={recientes} compact />
              </CardContent>
            </Card>
          </BlurFade>
        </div>
      </main>
    </div>
  )
}

const MONTH_SHORT = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

function Ring({ pct, pagados, total }: { pct: number; pagados: number; total: number }) {
  return (
    <div
      className="relative w-[108px] h-[108px] flex-shrink-0 rounded-full grid place-items-center"
      style={{ background: `conic-gradient(hsl(var(--success)) ${pct * 3.6}deg, hsl(var(--muted)) 0)` }}
    >
      <div className="absolute inset-[11px] rounded-full bg-card" />
      <div className="relative text-center">
        <div className="text-[22px] font-bold text-foreground leading-none tabular">{pagados}/{total}</div>
        <div className="text-[10px] text-muted-foreground mt-1 tracking-wide uppercase">pagados</div>
      </div>
    </div>
  )
}

function Stat({ k, v, extra }: { k: string; v: string; extra?: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11.5px] text-muted-foreground font-medium">{k}</div>
      <div className="text-base font-semibold text-foreground mt-0.5 tabular flex items-center gap-1.5">{v}{extra}</div>
    </div>
  )
}

function Delta({ v }: { v: number }) {
  return (
    <span className={cn('text-xs font-semibold', v > 0 ? 'text-destructive' : 'text-success')}>
      {v > 0 ? '▲' : '▼'} {Math.abs(v)}%
    </span>
  )
}
