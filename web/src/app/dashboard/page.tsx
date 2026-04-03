import Sidebar from '@/components/Sidebar'
import SummaryCard from '@/components/SummaryCard'
import AnimatedSummaryCard from '@/components/AnimatedSummaryCard'
import ExpenseTable from '@/components/ExpenseTable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BlurFade } from '@/components/magicui/blur-fade'
import { getResumenMes, getGastosRecientes, getCategorias, getRecurrentesConCosto, getCuotasActivas, getPlanesCuotaActivos } from '@/lib/queries'
import { formatARS, monthLabel } from '@/lib/utils'
import { cn } from '@/lib/utils'

export const dynamic = 'force-dynamic'

export default async function DashboardPage() {
  const hoy = new Date()
  const mes = hoy.getMonth() + 1
  const anio = hoy.getFullYear()
  const mesAnterior = mes === 1 ? 12 : mes - 1
  const anioAnterior = mes === 1 ? anio - 1 : anio

  const categorias = await getCategorias()
  const [resumenActual, resumenAnterior, recientes, recurrentes, cuotasActivas, planesCuota] = await Promise.all([
    getResumenMes(mes, anio, categorias),
    getResumenMes(mesAnterior, anioAnterior, categorias),
    getGastosRecientes(10),
    getRecurrentesConCosto(),
    getCuotasActivas(),
    getPlanesCuotaActivos(),
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

  const equivalenteUSD = tcBlue && resumenActual.total_ars > 0
    ? Math.round(resumenActual.total_ars / tcBlue)
    : null

  const proximosVencimientos = recurrentes.recurrentes.filter(
    r => r.dias_para_vencimiento >= 0 && r.dias_para_vencimiento <= 7,
  )

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
            <p className="text-muted-foreground text-sm mt-1">
              {monthLabel(mes, anio)} · día {diasTranscurridos} de {diasTotales}
            </p>
          </div>

          {/* Cards fila 1 */}
          <BlurFade delay={0} className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            <AnimatedSummaryCard
              title="Total del mes"
              value={formatARS(resumenActual.total_ars)}
              numericValue={resumenActual.total_ars}
              format="ars"
              trend={variacion}
              subtitle={`vs ${monthLabel(mesAnterior, anioAnterior)}`}
              icon="💸"
            />
            <AnimatedSummaryCard
              title="Proyección fin de mes"
              value={formatARS(proyeccion)}
              numericValue={proyeccion}
              format="ars"
              subtitle={`${formatARS(Math.round(promedioDiario))}/día promedio`}
              icon="📈"
            />
            <AnimatedSummaryCard
              title="Gastos registrados"
              value={String(resumenActual.cantidad)}
              numericValue={resumenActual.cantidad}
              format="count"
              subtitle={`${resumenAnterior.cantidad} el mes anterior`}
              icon="🧾"
            />
            {equivalenteUSD !== null ? (
              <AnimatedSummaryCard
                title="Equivalente USD (oficial)"
                value={`USD ${equivalenteUSD.toLocaleString('es-AR')}`}
                numericValue={equivalenteUSD}
                format="usd"
                subtitle={`TC $${tcBlue?.toLocaleString('es-AR')}${recurrentes.tc_es_hoy ? ' · hoy' : recurrentes.tc_fecha ? ` · ${recurrentes.tc_fecha}` : ''}`}
                icon="💵"
              />
            ) : (
              <AnimatedSummaryCard
                title="Recurrentes mensuales"
                value={formatARS(recurrentes.total_mensual_ars)}
                numericValue={recurrentes.total_mensual_ars}
                format="ars"
                subtitle={`${recurrentes.recurrentes.length} activos`}
                icon="🔁"
              />
            )}
          </BlurFade>

          {/* Cards fila 2 */}
          {equivalenteUSD !== null && (
            <BlurFade delay={0.05} className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <AnimatedSummaryCard
                title="Recurrentes mensuales"
                value={formatARS(recurrentes.total_mensual_ars)}
                numericValue={recurrentes.total_mensual_ars}
                format="ars"
                subtitle={`${recurrentes.recurrentes.length} activos`}
                icon="🔁"
              />
              <AnimatedSummaryCard
                title="Recurrentes anuales"
                value={formatARS(recurrentes.total_anual_ars)}
                numericValue={recurrentes.total_anual_ars}
                format="ars"
                subtitle="comprometido este año"
                icon="📋"
              />
            </BlurFade>
          )}

          <BlurFade delay={0.1} className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
            {/* Distribución por categoría */}
            {resumenActual.por_categoria.length > 0 && (
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle className="text-base">Por categoría</CardTitle>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="space-y-3">
                    {resumenActual.por_categoria.slice(0, 7).map(cat => {
                      const pct =
                        resumenActual.total_ars > 0
                          ? Math.round((cat.total_ars / resumenActual.total_ars) * 100)
                          : 0
                      return (
                        <div key={cat.categoria}>
                          <div className="flex justify-between text-sm mb-1">
                            <span className="text-foreground/80">{cat.categoria}</span>
                            <span className="font-medium text-foreground tabular">
                              {formatARS(cat.total_ars)}{' '}
                              <span className="text-muted-foreground font-normal">({pct}%)</span>
                            </span>
                          </div>
                          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full transition-all"
                              style={{ width: `${pct}%`, backgroundColor: cat.color ?? '#6366f1' }}
                            />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Próximos vencimientos */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Próximos vencimientos</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                {proximosVencimientos.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Sin vencimientos en los próximos 7 días.</p>
                ) : (
                  <div className="space-y-3">
                    {proximosVencimientos.map(r => (
                      <div key={r.id} className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-sm font-medium text-foreground leading-tight">{r.descripcion}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {r.dias_para_vencimiento === 0
                              ? '¡Hoy!'
                              : r.dias_para_vencimiento === 1
                              ? 'Mañana'
                              : `En ${r.dias_para_vencimiento} días`}
                          </p>
                        </div>
                        <span className="text-sm font-semibold text-foreground whitespace-nowrap tabular">
                          {r.moneda === 'USD' ? `USD ${r.monto_original}` : formatARS(r.monto_original)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                <a href="/recurrentes" className="text-xs text-primary hover:text-primary/80 transition-colors mt-4 block">
                  Ver todos los recurrentes →
                </a>
              </CardContent>
            </Card>
          </BlurFade>

          {/* Cuotas activas */}
          {(cuotasActivas.length > 0 || planesCuota.length > 0) && (
          <BlurFade delay={0.15}>
          <Card className="mb-6">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Cuotas activas</CardTitle>
                <a href="/cuotas" className="text-sm text-primary hover:text-primary/80 transition-colors">
                  Ver planes →
                </a>
              </div>
            </CardHeader>
            <div className="divide-y divide-border/60">
              {/* Planes de cuota (nueva tabla) */}
              {planesCuota.map(p => {
                const pct = Math.round(((p.cuota_actual - 1) / p.cuotas_total) * 100)
                const fechaFin = (() => {
                  const mesesRestantes = p.cuotas_total - p.cuota_actual + 1
                  const [fy, fm] = p.proximo_vencimiento.split('-').map(Number)
                  const totalM = (fm - 1) + (mesesRestantes - 1)
                  const finY = fy + Math.floor(totalM / 12)
                  const finM = (totalM % 12) + 1
                  return new Date(finY, finM - 1, 1).toLocaleDateString('es-AR', { month: 'short', year: 'numeric' })
                })()
                const proximoPago = new Date(p.proximo_vencimiento + 'T00:00:00')
                  .toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })
                return (
                  <div key={p.id} className="px-5 py-4">
                    <div className="flex items-start justify-between gap-4 mb-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{p.descripcion}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Cuota {p.cuota_actual} de {p.cuotas_total}
                          {' · '}próx. {proximoPago} · termina {fechaFin}
                          {' · '}
                          <span className={p.tipo === 'fijo' ? 'text-success' : 'text-warning'}>
                            {p.tipo === 'fijo' ? 'sin interés' : 'con interés'}
                          </span>
                        </p>
                      </div>
                      <span className="text-sm font-semibold text-foreground whitespace-nowrap tabular">
                        {p.tipo === 'fijo' && p.monto_cuota != null
                          ? (p.moneda === 'USD' ? `USD ${p.monto_cuota}` : formatARS(p.monto_cuota)) + '/mes'
                          : <span className="text-muted-foreground font-normal text-xs">variable</span>
                        }
                      </span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div className="h-full gradient-primary rounded-full transition-all" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
              {/* Cuotas de gastos (tabla original) */}
              {cuotasActivas.map((c, i) => {
                const pct = Math.round(((c.cuota_pendiente - 1) / c.cuotas) * 100)
                const fechaFin = new Date(c.fecha_fin + 'T00:00:00').toLocaleDateString('es-AR', { month: 'short', year: 'numeric' })
                const proximoPago = new Date(c.proxima_fecha + 'T00:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })
                return (
                  <div key={i} className="px-5 py-4">
                    <div className="flex items-start justify-between gap-4 mb-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">
                          {c.comercio || c.descripcion}
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Cuota {c.cuota_pendiente} de {c.cuotas} · próx. {proximoPago} · termina {fechaFin}
                        </p>
                      </div>
                      <span className="text-sm font-semibold text-foreground whitespace-nowrap tabular">
                        {c.moneda === 'USD' ? `USD ${c.monto_original}` : formatARS(c.monto_ars)}/mes
                      </span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div className="h-full gradient-primary rounded-full transition-all" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </Card>
          </BlurFade>
          )}

          {/* Últimos gastos */}
          <BlurFade delay={0.2}>
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Últimos gastos</CardTitle>
                <a href="/gastos" className="text-sm text-primary hover:text-primary/80 transition-colors">
                  Ver todos →
                </a>
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
