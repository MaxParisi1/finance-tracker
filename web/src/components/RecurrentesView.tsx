'use client'

import { useState, useTransition } from 'react'
import type { GastoRecurrente } from '@/lib/types'
import type { RecurrenteConCosto } from '@/lib/queries'
import RecurrenteModal from './RecurrenteModal'
import { formatARS } from '@/lib/utils'
import { materializarRecurrentesAction } from '@/app/recurrentes/actions'

const FRECUENCIA_LABEL: Record<string, string> = {
  mensual: 'Mensual',
  anual: 'Anual',
  semanal: 'Semanal',
}

interface Props {
  recurrentes: RecurrenteConCosto[]
  total_mensual_ars: number
  total_anual_ars: number
  tc_blue: number | null
  categorias: string[]
}

export default function RecurrentesView({
  recurrentes,
  total_mensual_ars,
  total_anual_ars,
  tc_blue,
  categorias,
}: Props) {
  const [editing, setEditing] = useState<GastoRecurrente | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [isPending, startTransition] = useTransition()
  const [materializeResult, setMaterializeResult] = useState<{
    insertados: number
    omitidos: number
    errores: string[]
  } | null>(null)

  const recurrentesSorted = [...recurrentes].sort(
    (a, b) => a.dias_para_vencimiento - b.dias_para_vencimiento,
  )

  const porCategoria = new Map<string, number>()
  for (const r of recurrentes) {
    const cat = r.categoria ?? 'Sin categoría'
    porCategoria.set(cat, (porCategoria.get(cat) ?? 0) + r.mensual_ars)
  }
  const categoriasSorted = Array.from(porCategoria.entries())
    .map(([cat, total]) => ({ cat, total }))
    .sort((a, b) => b.total - a.total)

  function handleMaterialize() {
    setMaterializeResult(null)
    startTransition(async () => {
      const result = await materializarRecurrentesAction()
      setMaterializeResult(result)
    })
  }

  const pendingCount = recurrentes.filter(r => r.dias_para_vencimiento <= 0 && !r.no_materializar).length

  return (
    <>
      {/* Resumen total */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
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

      {/* Barra de acciones */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          {pendingCount > 0 && (
            <button
              onClick={handleMaterialize}
              disabled={isPending}
              className="text-sm bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              {isPending ? 'Materializando...' : `Registrar vencidos (${pendingCount})`}
            </button>
          )}
          {materializeResult && (
            <p className="text-sm text-gray-600">
              ✓ {materializeResult.insertados} registrados
              {materializeResult.omitidos > 0 && `, ${materializeResult.omitidos} ya existían`}
              {materializeResult.errores.length > 0 && (
                <span className="text-red-500"> · {materializeResult.errores.length} errores</span>
              )}
            </p>
          )}
        </div>
        <button
          onClick={() => setShowNew(true)}
          className="text-sm border border-gray-300 rounded-lg px-4 py-2 bg-white hover:bg-gray-50 text-gray-700 transition-colors"
        >
          + Nuevo recurrente
        </button>
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
                const vencido = r.dias_para_vencimiento < 0

                return (
                  <button
                    key={r.id}
                    onClick={() => setEditing(r)}
                    className="w-full flex items-center justify-between px-6 py-4 hover:bg-gray-50 transition-colors text-left"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {r.descripcion}
                        </p>
                        {r.no_materializar && (
                          <span className="text-xs bg-blue-100 text-blue-600 px-1.5 py-0.5 rounded font-medium whitespace-nowrap">
                            auto
                          </span>
                        )}
                        {!r.no_materializar && vencido && (
                          <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded font-medium whitespace-nowrap">
                            Vencido
                          </span>
                        )}
                        {!r.no_materializar && urgente && !vencido && (
                          <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded font-medium whitespace-nowrap">
                            {r.dias_para_vencimiento === 0 ? '¡Hoy!' : `${r.dias_para_vencimiento}d`}
                          </span>
                        )}
                        {!r.no_materializar && proximo && (
                          <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium whitespace-nowrap">
                            {r.dias_para_vencimiento}d
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-0.5">
                        <span className="text-xs text-gray-400">{r.categoria ?? 'Sin categoría'}</span>
                        <span className="text-xs text-gray-300">·</span>
                        <span className="text-xs text-gray-400">{FRECUENCIA_LABEL[r.frecuencia] ?? r.frecuencia}</span>
                        <span className="text-xs text-gray-300">·</span>
                        <span className="text-xs text-gray-400">Día {r.dia_del_mes}</span>
                      </div>
                    </div>

                    <div className="text-right ml-4">
                      <p className="text-sm font-semibold text-gray-900">
                        {r.moneda === 'USD'
                          ? `USD ${r.monto_original.toLocaleString('es-AR', { minimumFractionDigits: 2 })}`
                          : formatARS(r.monto_original)}
                      </p>
                      {r.frecuencia !== 'mensual' && (
                        <p className="text-xs text-gray-400 mt-0.5">≈ {formatARS(r.mensual_ars)}/mes</p>
                      )}
                      {r.moneda === 'USD' && tc_blue && (
                        <p className="text-xs text-gray-400 mt-0.5">≈ {formatARS(r.mensual_ars)}/mes</p>
                      )}
                    </div>
                  </button>
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
                      <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
              <p className="text-xs text-gray-400 mt-4 pt-3 border-t border-gray-100">
                Los montos en USD se convierten al TC blue más reciente.
              </p>
            </div>
          )}
        </div>
      </div>

      {editing && (
        <RecurrenteModal
          recurrente={editing}
          categorias={categorias}
          onClose={() => setEditing(null)}
        />
      )}
      {showNew && (
        <RecurrenteModal
          categorias={categorias}
          onClose={() => setShowNew(false)}
        />
      )}
    </>
  )
}
