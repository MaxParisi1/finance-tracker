import Sidebar from '@/components/Sidebar'
import SpendingTrendChart from '@/components/charts/SpendingTrendChart'
import CategoryChart from '@/components/charts/CategoryChart'
import TopMerchantsChart from '@/components/charts/TopMerchantsChart'
import DailySpendingChart from '@/components/charts/DailySpendingChart'
import PaymentMethodChart from '@/components/charts/PaymentMethodChart'
import {
  getTendencia,
  getResumenMes,
  getTopComercios,
  getCategorias,
  getDailySpending,
  getPaymentMethodBreakdown,
  getLatestTipoCambio,
} from '@/lib/queries'
import { formatARS, monthLabel, MEDIO_PAGO_LABELS } from '@/lib/utils'

export const dynamic = 'force-dynamic'

export default async function AnalyticsPage() {
  const hoy = new Date()
  const mes = hoy.getMonth() + 1
  const anio = hoy.getFullYear()
  const mesAnioAnterior = anio - 1

  const categorias = await getCategorias()
  const [tendencia, resumen, resumenYoY, topComercios, dailySpending, paymentMethods, tcBlue] =
    await Promise.all([
      getTendencia(6),
      getResumenMes(mes, anio, categorias),
      getResumenMes(mes, mesAnioAnterior, categorias),
      getTopComercios(mes, anio, 10),
      getDailySpending(mes, anio),
      getPaymentMethodBreakdown(mes, anio),
      getLatestTipoCambio('blue'),
    ])

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

      <main className="flex-1 px-4 md:px-8 pt-safe-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-gray-900">Analíticas</h1>
            <p className="text-gray-500 text-sm mt-1">Últimos 6 meses · actualizado en tiempo real</p>
          </div>

          {/* KPIs rápidos */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 font-medium">Promedio 6 meses</p>
              <p className="text-lg font-bold text-gray-900 mt-1">{formatARS(promedioMensual6m)}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 font-medium">{monthLabel(mes, anio)}</p>
              <p className="text-lg font-bold text-gray-900 mt-1">{formatARS(resumen.total_ars)}</p>
            </div>
            {equivalenteUSD !== null && (
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <p className="text-xs text-gray-500 font-medium">Equiv. USD blue</p>
                <p className="text-lg font-bold text-gray-900 mt-1">
                  USD {equivalenteUSD.toLocaleString('es-AR')}
                </p>
                <p className="text-xs text-gray-400">TC ${tcBlue?.toLocaleString('es-AR')}</p>
              </div>
            )}
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 font-medium">vs {monthLabel(mes, mesAnioAnterior)}</p>
              <p className="text-lg font-bold text-gray-900 mt-1">{formatARS(resumenYoY.total_ars)}</p>
              {yoyVariacion !== null && (
                <span className={`text-xs font-medium ${yoyVariacion > 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                  {yoyVariacion > 0 ? '+' : ''}{yoyVariacion}% interanual
                </span>
              )}
            </div>
          </div>

          {/* Tendencia 6 meses */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-gray-900">Tendencia de gasto</h2>
                <p className="text-xs text-gray-500 mt-0.5">Últimos 6 meses en ARS</p>
              </div>
              {tendencia.at(-1)?.variacion_pct != null && (
                <span className={`text-sm font-medium px-3 py-1 rounded-full ${
                  (tendencia.at(-1)!.variacion_pct! > 0)
                    ? 'bg-red-50 text-red-600'
                    : 'bg-emerald-50 text-emerald-700'
                }`}>
                  {tendencia.at(-1)!.variacion_pct! > 0 ? '+' : ''}{tendencia.at(-1)!.variacion_pct}% vs mes anterior
                </span>
              )}
            </div>
            <SpendingTrendChart data={tendencia} />
          </div>

          {/* Gasto diario */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
            <h2 className="text-base font-semibold text-gray-900 mb-1">
              Gasto diario — {monthLabel(mes, anio)}
            </h2>
            <p className="text-xs text-gray-500 mb-4">
              Barras: gasto del día · Línea verde: acumulado del mes
            </p>
            {dailySpending.length > 0 ? (
              <DailySpendingChart data={dailySpending} />
            ) : (
              <p className="text-sm text-gray-400 text-center py-8">Sin datos este mes.</p>
            )}
          </div>

          {/* Categorías + Medios de pago */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-base font-semibold text-gray-900 mb-1">Por categoría</h2>
              <p className="text-xs text-gray-500 mb-4">{monthLabel(mes, anio)}</p>
              {resumen.por_categoria.length > 0 ? (
                <CategoryChart data={resumen.por_categoria} />
              ) : (
                <p className="text-sm text-gray-400 text-center py-8">Sin datos.</p>
              )}
            </div>

            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-base font-semibold text-gray-900 mb-1">Por medio de pago</h2>
              <p className="text-xs text-gray-500 mb-4">{monthLabel(mes, anio)}</p>
              {paymentMethods.length > 0 ? (
                <>
                  <PaymentMethodChart data={paymentMethods} />
                  <div className="mt-2 space-y-1.5 pt-2 border-t border-gray-100">
                    {paymentMethods.map(pm => (
                      <div key={pm.medio_pago} className="flex justify-between text-xs text-gray-600">
                        <span>{MEDIO_PAGO_LABELS[pm.medio_pago] ?? pm.medio_pago}</span>
                        <span className="font-medium">{formatARS(pm.total_ars)}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-sm text-gray-400 text-center py-8">Sin datos.</p>
              )}
            </div>
          </div>

          {/* Top comercios */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
            <h2 className="text-base font-semibold text-gray-900 mb-1">Top comercios</h2>
            <p className="text-xs text-gray-500 mb-4">{monthLabel(mes, anio)}</p>
            {topComercios.length > 0 ? (
              <TopMerchantsChart data={topComercios} />
            ) : (
              <p className="text-sm text-gray-400 text-center py-8">Sin datos.</p>
            )}
          </div>

          {/* Tabla histórica */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-4">Resumen por mes</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Mes</th>
                  <th className="text-right pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Total ARS</th>
                  {tcBlue && <th className="text-right pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide">USD equiv.</th>}
                  <th className="text-right pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Gastos</th>
                  <th className="text-right pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Prom./día</th>
                  <th className="text-right pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide">vs anterior</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {[...tendencia].reverse().map(t => {
                  const diasMes = new Date(t.anio, t.mes, 0).getDate()
                  const promDia = t.total_ars > 0 ? Math.round(t.total_ars / diasMes) : 0
                  const usdEquiv = tcBlue && t.total_ars > 0 ? Math.round(t.total_ars / tcBlue) : null
                  return (
                    <tr key={`${t.mes}-${t.anio}`}>
                      <td className="py-3 font-medium text-gray-900">{t.label}</td>
                      <td className="py-3 text-right text-gray-900">{formatARS(t.total_ars)}</td>
                      {tcBlue && (
                        <td className="py-3 text-right text-blue-600 text-xs">
                          {usdEquiv ? `USD ${usdEquiv.toLocaleString('es-AR')}` : '—'}
                        </td>
                      )}
                      <td className="py-3 text-right text-gray-500">{t.cantidad}</td>
                      <td className="py-3 text-right text-gray-500">{formatARS(promDia)}</td>
                      <td className="py-3 text-right">
                        {t.variacion_pct != null ? (
                          <span className={`text-xs font-medium ${
                            t.variacion_pct > 0 ? 'text-red-600' : t.variacion_pct < 0 ? 'text-emerald-600' : 'text-gray-400'
                          }`}>
                            {t.variacion_pct > 0 ? '+' : ''}{t.variacion_pct}%
                          </span>
                        ) : <span className="text-gray-300">—</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  )
}
