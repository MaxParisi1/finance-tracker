import Sidebar from '@/components/Sidebar'
import ExpenseTable from '@/components/ExpenseTable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BlurFade } from '@/components/magicui/blur-fade'
import {
  getResumenMes, getGastosRecientes, getCategorias, getRecurrentesConCosto,
  getFijosDelMes, getAgenda, getTendencia,
} from '@/lib/queries'
import { formatARS, monthLabel, cn } from '@/lib/utils'

export const dynamic = 'force-dynamic'

const MONTH_SHORT = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

function agendaLabel(fecha: string, sinFecha: boolean, hoy: string): string {
  if (sinFecha) return MONTH_SHORT[Number(fecha.split('-')[1]) - 1]
  const [y, m, d] = fecha.split('-').map(Number)
  const [hy, hm, hd] = hoy.split('-').map(Number)
  const diff = Math.round((new Date(y, m - 1, d).getTime() - new Date(hy, hm - 1, hd).getTime()) / 86400000)
  if (diff <= 0) return 'hoy'
  if (diff === 1) return 'mañana'
  if (diff <= 7) return `en ${diff}d`
  return `${d} ${MONTH_SHORT[m - 1]}`
}

export default async function DashboardPage() {
  const hoy = new Date()
  const hoyStr = hoy.toLocaleDateString('sv-SE', { timeZone: 'America/Argentina/Buenos_Aires' })
  const mes = hoy.getMonth() + 1
  const anio = hoy.getFullYear()
  const mesAnterior = mes === 1 ? 12 : mes - 1
  const anioAnterior = mes === 1 ? anio - 1 : anio

  const categorias = await getCategorias()
  const [resumenActual, resumenAnterior, recientes, recurrentes, fijos, agenda, tendencia] =
    await Promise.all([
      getResumenMes(mes, anio, categorias),
      getResumenMes(mesAnterior, anioAnterior, categorias),
      getGastosRecientes(8),
      getRecurrentesConCosto(),
      getFijosDelMes(mes, anio),
      getAgenda(),
      getTendencia(4),
    ])
  const tcBlue = recurrentes.tc_blue

  const variacion = resumenAnterior.total_ars > 0
    ? Math.round(((resumenActual.total_ars - resumenAnterior.total_ars) / resumenAnterior.total_ars) * 1000) / 10
    : null

  const diasTranscurridos = hoy.getDate()
  const diasTotales = new Date(anio, mes, 0).getDate()
  const promedioDiario = diasTranscurridos > 0 ? resumenActual.total_ars / diasTranscurridos : 0
  const proyeccion = Math.round(promedioDiario * diasTotales)
  const equivalenteUSD = tcBlue && resumenActual.total_ars > 0 ? Math.round(resumenActual.total_ars / tcBlue) : null

  // Promedio de los 3 meses previos (excluye el actual)
  const previos = tendencia.slice(0, -1).filter(t => t.total_ars > 0)
  const avg3m = previos.length ? Math.round(previos.reduce((s, t) => s + t.total_ars, 0) / previos.length) : 0
  const proyVsAvg = avg3m > 0 ? Math.round(((proyeccion - avg3m) / avg3m) * 100) : null

  // Categorías con bucket "Otras"
  const TOP_N = 6
  const catTop = resumenActual.por_categoria.slice(0, TOP_N)
  const catResto = resumenActual.por_categoria.slice(TOP_N)
  const categoriasVista = catResto.length > 0
    ? [...catTop, { categoria: 'Otras categorías', total_ars: catResto.reduce((s, c) => s + c.total_ars, 0), cantidad: 0, color: '#9E9E9E' }]
    : catTop
  const topCat = resumenActual.por_categoria[0]
  const topCatPct = topCat && resumenActual.total_ars > 0 ? Math.round((topCat.total_ars / resumenActual.total_ars) * 100) : 0

  // Insights ("radar del mes")
  const insights: { txt: string; tone: 'up' | 'down' | 'neutral' }[] = []
  if (variacion != null) insights.push({ txt: variacion > 0 ? `Vas ${variacion}% arriba de ${monthLabel(mesAnterior, anioAnterior).split(' ')[0]}` : `Vas ${Math.abs(variacion)}% abajo de ${monthLabel(mesAnterior, anioAnterior).split(' ')[0]}`, tone: variacion > 0 ? 'up' : 'down' })
  if (proyVsAvg != null) insights.push({ txt: proyVsAvg > 0 ? `Proyectás terminar ${proyVsAvg}% sobre tu promedio de 3 meses` : `Proyectás terminar ${Math.abs(proyVsAvg)}% bajo tu promedio`, tone: proyVsAvg > 0 ? 'up' : 'down' })
  if (topCat) insights.push({ txt: `${topCat.categoria} es tu mayor gasto (${topCatPct}%)`, tone: 'neutral' })

  // Strip "Lo que viene": pendientes próximas
  const upcoming = agenda
    .filter(o => o.estado === 'pendiente' && (o.sin_fecha || o.fecha >= hoyStr))
    .sort((a, b) => a.fecha.localeCompare(b.fecha))
    .slice(0, 4)

  return (
    <div className="flex min-h-screen">
      <Sidebar pendientes={fijos.pendientes.length} />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          <div className="mb-6">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">Panel</h1>
            <p className="text-muted-foreground text-sm mt-1">{monthLabel(mes, anio)} · día {diasTranscurridos} de {diasTotales}</p>
          </div>

          {/* Estado de pagos + categorías */}
          <BlurFade delay={0} className="grid grid-cols-1 lg:grid-cols-5 gap-5 mb-5">
            <Card className="lg:col-span-3">
              <CardContent className="p-6">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Fijos de {MONTH_SHORT[mes - 1]} · lo que estás gestionando</p>
                <div className="flex items-center gap-6 mt-4 flex-wrap">
                  <Ring pct={fijos.pct_pagado} pagados={fijos.count_pagados} total={fijos.count_total} />
                  <div className="min-w-0">
                    {fijos.pendientes.length > 0 ? (
                      <>
                        <div className="font-display text-[2.4rem] leading-none tracking-tight text-foreground tabular">{formatARS(fijos.total_pendiente_ars)}</div>
                        <p className="text-sm text-muted-foreground mt-2 max-w-[34ch]">te faltan pagar <b className="text-foreground font-semibold">{fijos.pendientes.length} fijo{fijos.pendientes.length > 1 ? 's' : ''}</b> este mes</p>
                      </>
                    ) : (
                      <>
                        <div className="font-display text-[2.4rem] leading-none tracking-tight text-success">Al día ✓</div>
                        <p className="text-sm text-muted-foreground mt-2 max-w-[34ch]">pagaste los {fijos.count_total} fijos de este mes</p>
                      </>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-x-8 gap-y-3 mt-6 pt-5 border-t border-border">
                  <Stat k="Gastado en el mes" v={formatARS(resumenActual.total_ars)} extra={variacion != null ? <Delta v={variacion} /> : null} />
                  <Stat k="Proyección fin de mes" v={formatARS(proyeccion)} />
                  {equivalenteUSD !== null && <Stat k="Equivalente USD oficial" v={`US$ ${equivalenteUSD.toLocaleString('es-AR')}`} />}
                </div>
              </CardContent>
            </Card>

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
                            <span className="flex items-center gap-2 text-foreground/80"><span className="w-2 h-2 rounded-sm" style={{ backgroundColor: cat.color ?? '#9E9E9E' }} />{cat.categoria}</span>
                            <span className="font-medium text-foreground tabular">{formatARS(cat.total_ars)} <span className="text-muted-foreground font-normal">{pct}%</span></span>
                          </div>
                          <div className="h-1.5 bg-muted rounded-full overflow-hidden"><div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: cat.color ?? '#9E9E9E' }} /></div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </BlurFade>

          {/* Ritmo del mes + Lo que viene */}
          <BlurFade delay={0.06} className="grid grid-cols-1 lg:grid-cols-5 gap-5 mb-5">
            {/* Ritmo */}
            <Card className="lg:col-span-3">
              <CardHeader><CardTitle className="text-base">Ritmo del mes</CardTitle></CardHeader>
              <CardContent className="pt-0">
                {avg3m > 0 ? (
                  <>
                    <div className="space-y-3">
                      <RitmoBar label="Proyección fin de mes" value={proyeccion} max={Math.max(proyeccion, avg3m)} tone={proyVsAvg != null && proyVsAvg > 0 ? 'up' : 'ok'} />
                      <RitmoBar label="Promedio 3 meses" value={avg3m} max={Math.max(proyeccion, avg3m)} tone="muted" />
                    </div>
                    <ul className="mt-4 pt-4 border-t border-border space-y-2">
                      {insights.map((ins, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm">
                          <span className={cn('mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0', ins.tone === 'up' ? 'bg-destructive' : ins.tone === 'down' ? 'bg-success' : 'bg-primary')} />
                          <span className="text-foreground/80">{ins.txt}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground py-4">Necesito un par de meses de historial para comparar tu ritmo.</p>
                )}
              </CardContent>
            </Card>

            {/* Lo que viene */}
            <Card className="lg:col-span-2">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Lo que viene</CardTitle>
                  <a href="/agenda" className="text-xs text-primary hover:opacity-80 font-medium">Ver agenda →</a>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                {upcoming.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4">Nada pendiente. Estás al día 🎉</p>
                ) : (
                  <div className="space-y-3">
                    {upcoming.map((o, i) => (
                      <div key={i} className="flex items-center gap-3">
                        <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', o.tipo === 'fijo' ? 'bg-primary' : 'bg-primary/40')} />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-foreground truncate leading-tight">{o.titulo}</p>
                          <p className="text-[11px] text-muted-foreground">{agendaLabel(o.fecha, o.sin_fecha, hoyStr)}</p>
                        </div>
                        <span className="text-sm font-medium text-foreground tabular whitespace-nowrap">{o.moneda === 'USD' ? `US$ ${o.monto_original}` : formatARS(o.monto_ars)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </BlurFade>

          {/* Últimos gastos */}
          <BlurFade delay={0.12}>
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

function Ring({ pct, pagados, total }: { pct: number; pagados: number; total: number }) {
  return (
    <div className="relative w-[108px] h-[108px] flex-shrink-0 rounded-full grid place-items-center" style={{ background: `conic-gradient(hsl(var(--success)) ${pct * 3.6}deg, hsl(var(--muted)) 0)` }}>
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
  return <span className={cn('text-xs font-semibold', v > 0 ? 'text-destructive' : 'text-success')}>{v > 0 ? '▲' : '▼'} {Math.abs(v)}%</span>
}

function RitmoBar({ label, value, max, tone }: { label: string; value: number; max: number; tone: 'up' | 'ok' | 'muted' }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0
  const color = tone === 'up' ? 'bg-warning' : tone === 'muted' ? 'bg-muted-foreground/40' : 'bg-primary'
  return (
    <div>
      <div className="flex justify-between text-[13px] mb-1.5">
        <span className="text-foreground/80">{label}</span>
        <span className="font-medium text-foreground tabular">{formatARS(value)}</span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden"><div className={cn('h-full rounded-full', color)} style={{ width: `${pct}%` }} /></div>
    </div>
  )
}
