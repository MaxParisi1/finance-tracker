import Sidebar from '@/components/Sidebar'
import { getRecurrentesConCosto } from '@/lib/queries'
import { formatARS } from '@/lib/utils'

export const dynamic = 'force-dynamic'

const FRECUENCIA_LABEL: Record<string, string> = {
  mensual: 'Mensual',
  anual: 'Anual',
  semanal: 'Semanal',
}

export default async function RecurrentesPage() {
  const { recurrentes, total_mensual_ars, total_anual_ars, tc_blue } = await getRecurrentesConCosto()

  // Agrupar por categoría para el resumen
  const porCategoria = new Map<string, number>()
  for (const r of recurrentes) {
    const cat = r.categoria ?? 'Sin categoría'
    porCategoria.set(cat, (porCategoria.get(cat) ?? 0) + r.mensual_ars)
  }
  const categoriasSorted = [...porCategoria.entries()]
    .map(([cat, total]) => ({ cat, total }))
    .sort((a, b) => b.total - a.total)

  // Ordenar: primero los que vencen antes
  const recurrentesSorted = [...recurrentes].sort(
    (a, b) => a.dias_para_vencimiento - b.dias_para_vencimiento,
  )

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      <main className="flex-1 px-8 py-8 overflow-auto">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-gray-900">Gastos recurrentes</h1>
            <p className="text-gray-500 text-sm mt-1">
              Suscripciones, servicios y pagos periódicos activos
            </p>
          </div>

          {/* Resumen total */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5">
              <p className="text-xs font-medium text-emerald-700">Compromiso mensual</p>
              <p className="text-2xl font-bold text-emerald-900 mt-1">{formatARS(total_mensual_ars)}</p>
              <p className="text-xs text-emerald-600 mt-0.5">{recurrentes.length} activos</p>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-5">
              <p className="text-xs font-medium text-gray-500">Compromiso anual</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{formatARS(total_anual_ars)}</p>
              <p className="text-xs text-gray-400 mt-0.5">proyectado 12 meses</p>
            </div>
            {tc_blue && (
              <div className="bg-white border border-gray-200 rounded-xl p-5">
                <p className="text-xs font-medium text-gray-500">Equiv. mensual USD</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  USD {Math.round(total_mensual_ars / tc_blue).toLocaleString('es-AR')}
                </p>
                <p className="text-xs text-gray-400 mt-0.5">TC blue ${tc_blue.toLocaleString('es-AR')}</p>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Lista de recurrentes */}
            <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200">
              <div className="px-6 py-4 border-b border-gray-200">
                <h2 className="text-base font-semibold text-gray-900">Detalle</h2>
              </div>

              {recurrentesSorted.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-12">
                  No hay gastos recurrentes activos.
                </p>
              ) : (
                <div className="divide-y divide-gray-100">
                  {recurrentesSorted.map(r => {
                    const urgente = r.dias_para_vencimiento >= 0 && r.dias_para_vencimiento <= 3
                    const proximo = r.dias_para_vencimiento > 3 && r.dias_para_vencimiento <= 7

                    return (
                      <div key={r.id} className="flex items-center justify-between px-6 py-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium text-gray-900 truncate">
                              {r.descripcion}
                            </p>
                            {urgente && (
                              <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded font-medium whitespace-nowrap">
                                {r.dias_para_vencimiento === 0 ? '¡Hoy!' : `${r.dias_para_vencimiento}d`}
                              </span>
                            )}
                            {proximo && (
                              <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium whitespace-nowrap">
                                {r.dias_para_vencimiento}d
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-3 mt-0.5">
                            <span className="text-xs text-gray-400">
                              {r.categoria ?? 'Sin categoría'}
                            </span>
                            <span className="text-xs text-gray-300">·</span>
                            <span className="text-xs text-gray-400">
                              {FRECUENCIA_LABEL[r.frecuencia] ?? r.frecuencia}
                            </span>
                            <span className="text-xs text-gray-300">·</span>
                            <span className="text-xs text-gray-400">
                              Vence el {r.dia_del_mes} de cada mes
                            </span>
                          </div>
                        </div>

                        <div className="text-right ml-4">
                          <p className="text-sm font-semibold text-gray-900">
                            {r.moneda === 'USD'
                              ? `USD ${r.monto_original.toLocaleString('es-AR', { minimumFractionDigits: 2 })}`
                              : formatARS(r.monto_original)}
                          </p>
                          {r.frecuencia !== 'mensual' && (
                            <p className="text-xs text-gray-400 mt-0.5">
                              ≈ {formatARS(r.mensual_ars)}/mes
                            </p>
                          )}
                          {r.moneda === 'USD' && tc_blue && (
                            <p className="text-xs text-gray-400 mt-0.5">
                              ≈ {formatARS(r.mensual_ars)}/mes ARS
                            </p>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Desglose por categoría */}
            <div className="bg-white rounded-xl border border-gray-200 p-6 h-fit">
              <h2 className="text-base font-semibold text-gray-900 mb-4">Por categoría</h2>
              {categoriasSorted.length === 0 ? (
                <p className="text-sm text-gray-400">Sin datos.</p>
              ) : (
                <div className="space-y-3">
                  {categoriasSorted.map(({ cat, total }) => {
                    const pct = total_mensual_ars > 0 ? Math.round((total / total_mensual_ars) * 100) : 0
                    return (
                      <div key={cat}>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-700 text-xs">{cat}</span>
                          <span className="text-xs font-medium text-gray-900">{formatARS(total)}</span>
                        </div>
                        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-emerald-500 rounded-full"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                  <p className="text-xs text-gray-400 mt-4 pt-3 border-t border-gray-100">
                    Los montos en USD se convierten al TC blue más reciente disponible en la DB.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
