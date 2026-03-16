import Sidebar from '@/components/Sidebar'
import SummaryCard from '@/components/SummaryCard'
import ExpenseTable from '@/components/ExpenseTable'
import { getResumenMes, getGastosRecientes, getCategorias, getRecurrentesConCosto, getCuotasActivas } from '@/lib/queries'
import { formatARS, monthLabel } from '@/lib/utils'

export const dynamic = 'force-dynamic'

export default async function DashboardPage() {
  const hoy = new Date()
  const mes = hoy.getMonth() + 1
  const anio = hoy.getFullYear()
  const mesAnterior = mes === 1 ? 12 : mes - 1
  const anioAnterior = mes === 1 ? anio - 1 : anio

  const categorias = await getCategorias()
  const [resumenActual, resumenAnterior, recientes, recurrentes, cuotasActivas] = await Promise.all([
    getResumenMes(mes, anio, categorias),
    getResumenMes(mesAnterior, anioAnterior, categorias),
    getGastosRecientes(10),
    getRecurrentesConCosto(),
    getCuotasActivas(),
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
            <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
            <p className="text-gray-500 text-sm mt-1">
              {monthLabel(mes, anio)} · día {diasTranscurridos} de {diasTotales}
            </p>
          </div>

          {/* Cards fila 1 */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            <SummaryCard
              title="Total del mes"
              value={formatARS(resumenActual.total_ars)}
              trend={variacion}
              subtitle={`vs ${monthLabel(mesAnterior, anioAnterior)}`}
              icon="💸"
            />
            <SummaryCard
              title="Proyección fin de mes"
              value={formatARS(proyeccion)}
              subtitle={`${formatARS(Math.round(promedioDiario))}/día promedio`}
              icon="📈"
            />
            <SummaryCard
              title="Gastos registrados"
              value={String(resumenActual.cantidad)}
              subtitle={`${resumenAnterior.cantidad} el mes anterior`}
              icon="🧾"
            />
            {equivalenteUSD !== null ? (
              <SummaryCard
                title="Equivalente USD (oficial)"
                value={`USD ${equivalenteUSD.toLocaleString('es-AR')}`}
                subtitle={`TC $${tcBlue?.toLocaleString('es-AR')}${recurrentes.tc_es_hoy ? ' · hoy' : recurrentes.tc_fecha ? ` · ${recurrentes.tc_fecha}` : ''}`}
                icon="💵"
              />
            ) : (
              <SummaryCard
                title="Recurrentes mensuales"
                value={formatARS(recurrentes.total_mensual_ars)}
                subtitle={`${recurrentes.recurrentes.length} activos`}
                icon="🔁"
              />
            )}
          </div>

          {/* Cards fila 2 — recurrentes + equivalente USD si no cabe arriba */}
          {equivalenteUSD !== null && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <SummaryCard
                title="Recurrentes mensuales"
                value={formatARS(recurrentes.total_mensual_ars)}
                subtitle={`${recurrentes.recurrentes.length} activos`}
                icon="🔁"
              />
              <SummaryCard
                title="Recurrentes anuales"
                value={formatARS(recurrentes.total_anual_ars)}
                subtitle="comprometido este año"
                icon="📋"
              />
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
            {/* Distribución por categoría */}
            {resumenActual.por_categoria.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-200 p-6 lg:col-span-2">
                <h2 className="text-base font-semibold text-gray-900 mb-4">Por categoría</h2>
                <div className="space-y-3">
                  {resumenActual.por_categoria.slice(0, 7).map(cat => {
                    const pct =
                      resumenActual.total_ars > 0
                        ? Math.round((cat.total_ars / resumenActual.total_ars) * 100)
                        : 0
                    return (
                      <div key={cat.categoria}>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-700">{cat.categoria}</span>
                          <span className="font-medium text-gray-900">
                            {formatARS(cat.total_ars)}{' '}
                            <span className="text-gray-400 font-normal">({pct}%)</span>
                          </span>
                        </div>
                        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{ width: `${pct}%`, backgroundColor: cat.color ?? '#10b981' }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Próximos vencimientos */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-base font-semibold text-gray-900 mb-4">Próximos vencimientos</h2>
              {proximosVencimientos.length === 0 ? (
                <p className="text-sm text-gray-400">Sin vencimientos en los próximos 7 días.</p>
              ) : (
                <div className="space-y-3">
                  {proximosVencimientos.map(r => (
                    <div key={r.id} className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium text-gray-900 leading-tight">{r.descripcion}</p>
                        <p className="text-xs text-gray-400 mt-0.5">
                          {r.dias_para_vencimiento === 0
                            ? '¡Hoy!'
                            : r.dias_para_vencimiento === 1
                            ? 'Mañana'
                            : `En ${r.dias_para_vencimiento} días`}
                        </p>
                      </div>
                      <span className="text-sm font-semibold text-gray-900 whitespace-nowrap">
                        {r.moneda === 'USD'
                          ? `USD ${r.monto_original}`
                          : formatARS(r.monto_original)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <a href="/recurrentes" className="text-xs text-emerald-600 hover:underline mt-4 block">
                Ver todos los recurrentes →
              </a>
            </div>
          </div>

          {/* Cuotas activas */}
          <div className="bg-white rounded-xl border border-gray-200 mb-6">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-base font-semibold text-gray-900">Cuotas activas</h2>
            </div>
            {cuotasActivas.length === 0 ? (
              <p className="px-6 py-4 text-sm text-gray-400">Sin cuotas activas.</p>
            ) : (
              <div className="divide-y divide-gray-100">
                {cuotasActivas.map((c, i) => {
                  const pct = Math.round((c.cuota_pendiente / c.cuotas) * 100)
                  const fechaFin = new Date(c.fecha_fin + 'T00:00:00').toLocaleDateString('es-AR', { month: 'short', year: 'numeric' })
                  const proximoPago = new Date(c.proxima_fecha + 'T00:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })
                  return (
                    <div key={i} className="px-6 py-4">
                      <div className="flex items-start justify-between gap-4 mb-2">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">
                            {c.comercio || c.descripcion}
                          </p>
                          <p className="text-xs text-gray-400 mt-0.5">
                            Cuota {c.cuota_pendiente} de {c.cuotas} · próx. {proximoPago} · termina {fechaFin}
                          </p>
                        </div>
                        <span className="text-sm font-semibold text-gray-900 whitespace-nowrap">
                          {c.moneda === 'USD' ? `USD ${c.monto_original}` : formatARS(c.monto_ars)}/mes
                        </span>
                      </div>
                      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-400 rounded-full transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Últimos gastos */}
          <div className="bg-white rounded-xl border border-gray-200">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h2 className="text-base font-semibold text-gray-900">Últimos gastos</h2>
              <a href="/gastos" className="text-sm text-emerald-600 hover:underline">
                Ver todos →
              </a>
            </div>
            <ExpenseTable gastos={recientes} compact />
          </div>
        </div>
      </main>
    </div>
  )
}
