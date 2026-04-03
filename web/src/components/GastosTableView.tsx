'use client'

import { useState, useMemo } from 'react'
import type { Gasto } from '@/lib/types'
import ExpenseTable from './ExpenseTable'
import EditGastoModal from './EditGastoModal'
import { formatARS } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { Search, X, Download } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

interface Props {
  gastos: Gasto[]
  categorias: string[]
  comercios?: string[]
  archivoCounts?: Record<string, number>
}

const selectClass = cn(
  'h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  'transition-colors text-foreground cursor-pointer'
)

export default function GastosTableView({ gastos, categorias, comercios: comerciosProp, archivoCounts }: Props) {
  const [search, setSearch] = useState('')
  const [categoria, setCategoria] = useState('')
  const [moneda, setMoneda] = useState('')
  const [mediopago, setMediopago] = useState('')
  const [editing, setEditing] = useState<Gasto | null>(null)

  const mediosPago = useMemo(
    () => Array.from(new Set(gastos.map(g => g.medio_pago).filter(Boolean))).sort(),
    [gastos],
  )

  const comerciosDelMes = useMemo(
    () => Array.from(new Set(gastos.map(g => g.comercio).filter((c): c is string => !!c))).sort(),
    [gastos],
  )
  const comercios = comerciosProp ?? comerciosDelMes

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
      <div className="flex flex-wrap gap-2 mb-5">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar descripción o comercio..."
            className={cn(
              'h-9 w-56 rounded-lg border border-input bg-background pl-9 pr-8 text-sm',
              'ring-offset-background placeholder:text-muted-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors'
            )}
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <select value={categoria} onChange={e => setCategoria(e.target.value)} className={selectClass}>
          <option value="">Todas las categorías</option>
          {categorias.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        <select value={mediopago} onChange={e => setMediopago(e.target.value)} className={selectClass}>
          <option value="">Todos los medios de pago</option>
          {mediosPago.map(mp => <option key={mp} value={mp}>{mp}</option>)}
        </select>

        <select value={moneda} onChange={e => setMoneda(e.target.value)} className={selectClass}>
          <option value="">ARS + USD</option>
          <option value="ARS">Solo ARS</option>
          <option value="USD">Solo USD</option>
        </select>

        {hasFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { setSearch(''); setCategoria(''); setMoneda(''); setMediopago('') }}
          >
            <X className="w-3.5 h-3.5 mr-1" />
            Limpiar
          </Button>
        )}

        <Button variant="outline" size="sm" onClick={exportCSV} className="ml-auto gap-1.5">
          <Download className="w-3.5 h-3.5" />
          CSV
        </Button>
      </div>

      {/* Resumen de resultados */}
      <div className="flex items-center gap-3 mb-4 text-sm text-muted-foreground">
        <span>
          <span className="font-semibold text-foreground">{filtered.length}</span> gastos ·{' '}
          <span className="font-semibold text-foreground">{formatARS(totalARS)}</span>
          {hasFilters && gastos.length !== filtered.length && (
            <span className="text-muted-foreground"> (de {gastos.length} total)</span>
          )}
        </span>
        {totalUSD > 0 && (
          <span className="text-blue-500 font-medium">
            · USD {totalUSD.toFixed(2)}
          </span>
        )}
      </div>

      {/* Tabla */}
      <Card className="overflow-hidden">
        <ExpenseTable gastos={filtered} onRowClick={setEditing} archivoCounts={archivoCounts} />
      </Card>

      {editing && (
        <EditGastoModal
          gasto={editing}
          categorias={categorias}
          comercios={comercios}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}
