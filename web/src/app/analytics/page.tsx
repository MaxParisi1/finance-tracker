import Sidebar from '@/components/Sidebar'
import SpendingTrendChart from '@/components/charts/SpendingTrendChart'
import CategoryChart from '@/components/charts/CategoryChart'
import TopMerchantsChart from '@/components/charts/TopMerchantsChart'
import DailySpendingChart from '@/components/charts/DailySpendingChart'
import PaymentMethodChart from '@/components/charts/PaymentMethodChart'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  getTendencia, getResumenMes, getTopComercios, getCategorias,
  getDailySpending, getPaymentMethodBreakdown, getTipoCambioActual,
} from '@/lib/queries'
import { formatARS, monthLabel, MEDIO_PAGO_LABELS } from '@/lib/utils'
import { cn } from '@/lib/utils'

export const dynamic = 'force-dynamic'

export default async function AnalyticsPage() {
  const hoy = new Date()
  const mes = hoy.getMonth() + 1
  const anio = hoy.getFullYear()
  const mesAnioAnterior = anio - 1

  const categorias = await getCategorias()
  const [tendencia, resumen, resumenYoY, topComercios, dailySpending, paymentMethods, tcInfo] =
    await Promise.all([
      getTendencia(6),
      getResumenMes(mes, anio, categorias),
      getResumenMes(mes, mesAnioAnterior, categorias),
      getTopComercios(mes, anio, 10),
      getDailySpending(mes, anio),
      getPaymentMethodBreakdown(mes, anio),
      getTipoCambioActual('oficial'),
    ])
  const tcBlue = tcInfo?.valor ?? null

  const yoyVariacion =
    resumenYoY.total_ars > 0
      ? Math.round(((resumen.total_ars - resumenYoY.total_ars) / resumenYoY.total_ars) * 1000) / 10
      : null

  const promedioMensual6m =
    tendencia.length > 0
      ? Math.round(tendencia.reduce((sum, t) => sum + t.total_ars, 0) / tendencia.length)
      : 0

  const equivalenteUSD = tcBlue && resumen.total_ars > 0
    ? Math.round(resumen.total_ars / tcBlue)
    : null

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-foreground">Analíticas</h1>
            <p className="text-muted-foreground text-sm mt-1">Últimos 6 meses · actualizado en tiempo real</p>
          </div>

          {/* KPIs */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <Card>
              <CardContent className="py-4">
                <p className="text-xs text-muted-foreground font-medium">Promedio 6 meses</p>
                <p className="text-lg font-bold text-foreground mt-1 tabular">{formatARS(promedioMensual6m)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="py-4">
                <p className="text-xs text-muted-foreground font-medium">{monthLabel(mes, anio)}</p>
                <p className="text-lg font-bold text-foreground mt-1 tabular">{formatARS(resumen.total_ars)}</p>
              </CardContent>
            </Card>
            {equivalenteUSD !== null && (
              <Card>
                <CardContent className="py-4">
                  <p className="text-xs text-muted-foreground font-medium">Equiv. USD blue</p>
                  <p className="text-lg font-bold text-foreground mt-1 tabular">
                    USD {equivalenteUSD.toLocaleString('es-AR')}
                  </p>
                  <p className="text-xs text-muted-foreground">TC ${tcBlue?.toLocaleString('es-AR')}</p>
                </CardContent>
              </Card>
            )}
            <Card>
              <CardContent className="py-4">
                <p className="text-xs text-muted-foreground font-medium">vs {monthLabel(mes, mesAnioAnterior)}</p>
                <p className="text-lg font-bold text-foreground mt-1 tabular">{formatARS(resumenYoY.total_ars)}</p>
                {yoyVariacion !== null && (
                  <span className={cn('text-xs font-medium', yoyVariacion > 0 ? 'text-destructive' : 'text-success')}>
                    {yoyVariacion > 0 ? '+' : ''}{yoyVariacion}% interanual
                  </span>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Tendencia 6 meses */}
          <Card className="mb-6">
            <CardHeader>
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-base">Tendencia de gasto</CardTitle>
                  <CardDescription>Últimos 6 meses en ARS</CardDescription>
                </div>
                {tendencia.at(-1)?.variacion_pct != null && (
                  <span className={cn(
                    'text-sm font-medium px-3 py-1 rounded-full',
                    tendencia.at(-1)!.variacion_pct! > 0
                      ? 'bg-destructive/10 text-destructive'
                      : 'bg-success/10 text-success'
                  )}>
                    {tendencia.at(-1)!.variacion_pct! > 0 ? '+' : ''}{tendencia.at(-1)!.variacion_pct}% vs mes anterior
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <SpendingTrendChart data={tendencia} />
            </CardContent>
          </Card>

          {/* Gasto diario */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-base">Gasto diario — {monthLabel(mes, anio)}</CardTitle>
              <CardDescription>Barras: gasto del día · Línea: acumulado del mes</CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              {dailySpending.length > 0 ? (
                <DailySpendingChart data={dailySpending} />
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">Sin datos este mes.</p>
              )}
            </CardContent>
          </Card>

          {/* Categorías + Medios de pago */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Por categoría</CardTitle>
                <CardDescription>{monthLabel(mes, anio)}</CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                {resumen.por_categoria.length > 0 ? (
                  <CategoryChart data={resumen.por_categoria} />
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-8">Sin datos.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Por medio de pago</CardTitle>
                <CardDescription>{monthLabel(mes, anio)}</CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                {paymentMethods.length > 0 ? (
                  <>
                    <PaymentMethodChart data={paymentMethods} />
                    <div className="mt-3 space-y-1.5 pt-3 border-t border-border">
                      {paymentMethods.map(pm => (
                        <div key={pm.medio_pago} className="flex justify-between text-xs text-muted-foreground">
                          <span>{MEDIO_PAGO_LABELS[pm.medio_pago] ?? pm.medio_pago}</span>
                          <span className="font-medium text-foreground tabular">{formatARS(pm.total_ars)}</span>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-8">Sin datos.</p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Top comercios */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-base">Top comercios</CardTitle>
              <CardDescription>{monthLabel(mes, anio)}</CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              {topComercios.length > 0 ? (
                <TopMerchantsChart data={topComercios} />
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">Sin datos.</p>
              )}
            </CardContent>
          </Card>

          {/* Tabla histórica */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Resumen por mes</CardTitle>
            </CardHeader>
            <CardContent className="pt-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {['Mes', 'Total ARS', tcBlue ? 'USD equiv.' : null, 'Gastos', 'Prom./día', 'vs anterior']
                      .filter(Boolean).map((h, i) => (
                      <th key={h} className={cn(
                        'pb-3 text-xs font-medium text-muted-foreground uppercase tracking-wide',
                        i === 0 ? 'text-left' : 'text-right'
                      )}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {[...tendencia].reverse().map(t => {
                    const diasMes = new Date(t.anio, t.mes, 0).getDate()
                    const promDia = t.total_ars > 0 ? Math.round(t.total_ars / diasMes) : 0
                    const usdEquiv = tcBlue && t.total_ars > 0 ? Math.round(t.total_ars / tcBlue) : null
                    return (
                      <tr key={`${t.mes}-${t.anio}`}>
                        <td className="py-3 font-medium text-foreground">{t.label}</td>
                        <td className="py-3 text-right text-foreground tabular">{formatARS(t.total_ars)}</td>
                        {tcBlue && (
                          <td className="py-3 text-right text-blue-500 text-xs tabular">
                            {usdEquiv ? `USD ${usdEquiv.toLocaleString('es-AR')}` : '—'}
                          </td>
                        )}
                        <td className="py-3 text-right text-muted-foreground">{t.cantidad}</td>
                        <td className="py-3 text-right text-muted-foreground tabular">{formatARS(promDia)}</td>
                        <td className="py-3 text-right">
                          {t.variacion_pct != null ? (
                            <span className={cn('text-xs font-medium',
                              t.variacion_pct > 0 ? 'text-destructive' :
                              t.variacion_pct < 0 ? 'text-success' : 'text-muted-foreground'
                            )}>
                              {t.variacion_pct > 0 ? '+' : ''}{t.variacion_pct}%
                            </span>
                          ) : <span className="text-muted-foreground">—</span>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  )
}
