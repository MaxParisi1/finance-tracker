'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import type { Gasto, Categoria } from '@/lib/types'
import type { HistoricoMes } from '@/lib/queries'
import HistoricoChart from '@/components/charts/HistoricoChart'
import { formatARS, formatDate, MEDIO_PAGO_LABELS, cn } from '@/lib/utils'
import { Search, X } from 'lucide-react'

interface Filtros {
  rango: string
  busqueda: string
  categoria: string
  medio_pago: string
}

interface Props {
  meses: HistoricoMes[]
  gastos: Gasto[]
  categorias: Categoria[]
  filtros: Filtros
}

const RANGOS = [
  { value: '3m', label: '3 meses' },
  { value: '6m', label: '6 meses' },
  { value: '12m', label: '12 meses' },
]

const selectClass = cn(
  'h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  'transition-colors text-foreground cursor-pointer',
)

export default function HistoricoView({ meses, gastos, categorias, filtros }: Props) {
  const router = useRouter()
  const [searchInput, setSearchInput] = useState(filtros.busqueda)

  // Debounce: push URL change 400ms after user stops typing
  useEffect(() => {
    const t = setTimeout(() => {
      if (searchInput !== filtros.busqueda) pushFilters({ busqueda: searchInput })
    }, 400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput])

  // Reset local input when server-side value changes (e.g. cleared by button)
  useEffect(() => { setSearchInput(filtros.busqueda) }, [filtros.busqueda])

  const pushFilters = useCallback(
    (overrides: Partial<Filtros>) => {
      const merged = { ...filtros, ...overrides }
      const params = new URLSearchParams()
      if (merged.rango && merged.rango !== '6m') params.set('rango', merged.rango)
      if (merged.busqueda) params.set('busqueda', merged.busqueda)
      if (merged.categoria) params.set('categoria', merged.categoria)
      if (merged.medio_pago) params.set('medio_pago', merged.medio_pago)
      router.push(`/historico${params.toString() ? `?${params}` : ''}`)
    },
    [filtros, router],
  )

  const hoy = new Date()
  const mesActual = { mes: hoy.getMonth() + 1, anio: hoy.getFullYear() }

  const totalARS = gastos.reduce((sum, g) => sum + (g.monto_ars ?? 0), 0)
  const promedioMensual = meses.length > 0 ? Math.round(totalARS / meses.length) : 0
  const hayFiltros = filtros.busqueda || filtros.categoria || filtros.medio_pago

  return (
    <div className="space-y-5">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Range presets */}
        <div className="flex gap-1 rounded-lg border border-input p-1 bg-background">
          {RANGOS.map(r => (
            <button
              key={r.value}
              onClick={() => pushFilters({ rango: r.value })}
              className={cn(
                'px-3 py-1.5 text-xs font-medium rounded-md transition-colors',
                filtros.rango === r.value
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted',
              )}
            >
              {r.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative flex-1 min-w-[160px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Buscar comercio…"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            className={cn(
              selectClass,
              'pl-8 w-full',
              searchInput && 'pr-8',
            )}
          />
          {searchInput && (
            <button
              onClick={() => { setSearchInput(''); pushFilters({ busqueda: '' }) }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Category */}
        <select
          value={filtros.categoria}
          onChange={e => pushFilters({ categoria: e.target.value })}
          className={selectClass}
        >
          <option value="">Todas las categorías</option>
          {categorias.map(c => (
            <option key={c.nombre} value={c.nombre}>{c.nombre}</option>
          ))}
        </select>

        {/* Medio de pago */}
        <select
          value={filtros.medio_pago}
          onChange={e => pushFilters({ medio_pago: e.target.value })}
          className={selectClass}
        >
          <option value="">Todos los medios</option>
          {Object.entries(MEDIO_PAGO_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Total en el período', value: formatARS(Math.round(totalARS)) },
          { label: `${gastos.length} transacciones`, value: `${meses.length} mes${meses.length !== 1 ? 'es' : ''}` },
          { label: 'Promedio mensual', value: formatARS(promedioMensual) },
        ].map(stat => (
          <div key={stat.label} className="rounded-xl border border-border bg-card px-4 py-3">
            <p className="text-xs text-muted-foreground">{stat.label}</p>
            <p className="text-base font-semibold text-foreground mt-0.5">{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Chart */}
      {meses.length > 0 ? (
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="text-sm font-medium text-foreground mb-3">Gastos por mes</p>
          <HistoricoChart data={meses} mesActual={mesActual} />
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card px-4 py-10 text-center text-muted-foreground text-sm">
          {hayFiltros ? 'Sin resultados para los filtros aplicados.' : 'No hay gastos en este período.'}
        </div>
      )}

      {/* Transactions table */}
      {gastos.length > 0 && (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">Fecha</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">Descripción</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground hidden sm:table-cell">Categoría</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground hidden md:table-cell">Medio</th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-muted-foreground">Monto</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {gastos.map(g => (
                  <tr key={g.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                      {formatDate(g.fecha)}
                    </td>
                    <td className="px-4 py-2.5 max-w-[200px]">
                      <p className="font-medium text-foreground truncate">{g.comercio || g.descripcion}</p>
                      {g.comercio && g.descripcion && (
                        <p className="text-xs text-muted-foreground truncate">{g.descripcion}</p>
                      )}
                    </td>
                    <td className="px-4 py-2.5 hidden sm:table-cell">
                      <span className="text-xs text-muted-foreground">{g.categoria ?? '—'}</span>
                    </td>
                    <td className="px-4 py-2.5 hidden md:table-cell">
                      <span className="text-xs text-muted-foreground">
                        {MEDIO_PAGO_LABELS[g.medio_pago] ?? g.medio_pago ?? '—'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right whitespace-nowrap">
                      <span className="font-semibold text-foreground">{formatARS(g.monto_ars ?? 0)}</span>
                      {g.moneda === 'USD' && (
                        <span className="text-xs text-muted-foreground ml-1">
                          (u$s {g.monto_original.toLocaleString('es-AR')})
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
