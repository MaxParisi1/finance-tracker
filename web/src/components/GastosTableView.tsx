'use client'

import { useState, useMemo } from 'react'
import type { Gasto } from '@/lib/types'
import ExpenseTable from './ExpenseTable'
import EditGastoModal from './EditGastoModal'
import { formatARS } from '@/lib/utils'

interface Props {
  gastos: Gasto[]
  categorias: string[]
}

export default function GastosTableView({ gastos, categorias }: Props) {
  const [search, setSearch] = useState('')
  const [categoria, setCategoria] = useState('')
  const [moneda, setMoneda] = useState('')
  const [mediopago, setMediopago] = useState('')
  const [editing, setEditing] = useState<Gasto | null>(null)

  const mediosPago = useMemo(
    () => Array.from(new Set(gastos.map(g => g.medio_pago).filter(Boolean))).sort(),
    [gastos],
  )

  const filtered = useMemo(() => {
    return gastos.filter(g => {
      if (categoria && g.categoria !== categoria) return false
      if (moneda && g.moneda !== moneda) return false
      if (mediopago && g.medio_pago !== mediopago) return false
      if (search) {
        const q = search.toLowerCase()
        const desc = (g.descripcion ?? '').toLowerCase()
        const com = (g.comercio ?? '').toLowerCase()
        if (!desc.includes(q) && !com.includes(q)) return false
      }
      return true
    })
  }, [gastos, search, categoria, moneda, mediopago])

  const totalARS = filtered.reduce((sum, g) => sum + (g.monto_ars ?? 0), 0)
  const totalUSD = filtered.filter(g => g.moneda === 'USD').reduce((sum, g) => sum + g.monto_original, 0)

  function exportCSV() {
    const headers = ['Fecha', 'Descripcion', 'Comercio', 'Categoria', 'Medio de Pago', 'Moneda', 'Monto Original', 'Monto ARS', 'Cuotas']
    const rows = filtered.map(g => [
      g.fecha,
      `"${(g.descripcion ?? '').replace(/"/g, '""')}"`,
      `"${(g.comercio ?? '').replace(/"/g, '""')}"`,
      g.categoria ?? '',
      g.medio_pago ?? '',
      g.moneda,
      g.monto_original,
      g.monto_ars,
      g.cuotas > 1 ? `${g.cuota_actual}/${g.cuotas}` : '1',
    ])
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `gastos.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const hasFilters = search || categoria || moneda || mediopago

  return (
    <div>
      {/* Filtros */}
      <div className="flex flex-wrap gap-3 mb-5">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="🔍 Buscar descripción o comercio..."
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500 w-64"
        />

        <select
          value={categoria}
          onChange={e => setCategoria(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <option value="">Todas las categorías</option>
          {categorias.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        <select
          value={mediopago}
          onChange={e => setMediopago(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <option value="">Todos los medios de pago</option>
          {mediosPago.map(mp => <option key={mp} value={mp}>{mp}</option>)}
        </select>

        <select
          value={moneda}
          onChange={e => setMoneda(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <option value="">ARS + USD</option>
          <option value="ARS">Solo ARS</option>
          <option value="USD">Solo USD</option>
        </select>

        {hasFilters && (
          <button
            onClick={() => { setSearch(''); setCategoria(''); setMoneda(''); setMediopago('') }}
            className="text-sm text-gray-400 hover:text-gray-600 px-2"
          >
            ✕ Limpiar
          </button>
        )}

        <button
          onClick={exportCSV}
          className="ml-auto text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white hover:bg-gray-50 text-gray-600 transition-colors"
        >
          ↓ Exportar CSV
        </button>
      </div>

      {/* Resumen de resultados */}
      <div className="flex items-center gap-4 mb-4 text-sm text-gray-500">
        <span>
          <span className="font-semibold text-gray-900">{filtered.length}</span> gastos ·{' '}
          <span className="font-semibold text-gray-900">{formatARS(totalARS)}</span>
          {hasFilters && gastos.length !== filtered.length && (
            <span className="text-gray-400"> (de {gastos.length} total)</span>
          )}
        </span>
        {totalUSD > 0 && (
          <span>
            · <span className="font-semibold text-blue-600">USD {totalUSD.toFixed(2)}</span> en USD
          </span>
        )}
      </div>

      {/* Tabla */}
      <div className="bg-white rounded-xl border border-gray-200">
        <ExpenseTable gastos={filtered} onRowClick={setEditing} />
      </div>

      {editing && (
        <EditGastoModal
          gasto={editing}
          categorias={categorias}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}
