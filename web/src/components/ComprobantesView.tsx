'use client'

import { useState, useMemo } from 'react'
import type { ArchivoDrive } from '@/lib/types'
import { formatARS, formatDate } from '@/lib/utils'

const TIPO_LABELS: Record<string, string> = {
  factura: 'Factura',
  comprobante: 'Comprobante',
  ticket: 'Ticket',
  recibo: 'Recibo',
  resumen: 'Resumen',
}

const TIPO_COLORS: Record<string, string> = {
  factura: 'bg-blue-50 text-blue-700',
  comprobante: 'bg-emerald-50 text-emerald-700',
  ticket: 'bg-amber-50 text-amber-700',
  recibo: 'bg-purple-50 text-purple-700',
  resumen: 'bg-gray-100 text-gray-700',
}

interface Props {
  archivos: ArchivoDrive[]
  categorias: string[]
}

export default function ComprobantesView({ archivos, categorias }: Props) {
  const [search, setSearch] = useState('')
  const [categoria, setCategoria] = useState('')
  const [tipo, setTipo] = useState('')

  const tipos = useMemo(
    () => Array.from(new Set(archivos.map(a => a.tipo).filter(Boolean))).sort(),
    [archivos],
  )

  const filtered = useMemo(() => {
    return archivos.filter(a => {
      if (categoria && a.categoria !== categoria) return false
      if (tipo && a.tipo !== tipo) return false
      if (search) {
        const q = search.toLowerCase()
        const com = (a.comercio ?? '').toLowerCase()
        const name = (a.drive_file_name ?? '').toLowerCase()
        if (!com.includes(q) && !name.includes(q)) return false
      }
      return true
    })
  }, [archivos, search, categoria, tipo])

  const hasFilters = search || categoria || tipo

  return (
    <div>
      {/* Filtros */}
      <div className="flex flex-wrap gap-3 mb-5">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Buscar por comercio o archivo..."
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500 w-64"
        />

        <select
          value={categoria}
          onChange={e => setCategoria(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <option value="">Todas las categorías</option>
          {categorias.map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>

        <select
          value={tipo}
          onChange={e => setTipo(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <option value="">Todos los tipos</option>
          {tipos.map(t => (
            <option key={t} value={t}>{TIPO_LABELS[t] ?? t}</option>
          ))}
        </select>

        {hasFilters && (
          <button
            onClick={() => { setSearch(''); setCategoria(''); setTipo('') }}
            className="text-sm text-gray-400 hover:text-gray-600 px-2"
          >
            ✕ Limpiar
          </button>
        )}
      </div>

      {/* Resumen */}
      <div className="flex items-center gap-4 mb-4 text-sm text-gray-500">
        <span>
          <span className="font-semibold text-gray-900">{filtered.length}</span> archivos
          {hasFilters && archivos.length !== filtered.length && (
            <span className="text-gray-400"> (de {archivos.length} total)</span>
          )}
        </span>
      </div>

      {/* Tabla */}
      <div className="bg-white rounded-xl border border-gray-200">
        {filtered.length === 0 ? (
          <div className="text-center py-12 text-gray-400 text-sm">
            No hay comprobantes en este período.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Fecha
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Comercio
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Tipo
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Categoría
                  </th>
                  <th className="text-right py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Monto
                  </th>
                  <th className="text-center py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Gasto
                  </th>
                  <th className="text-center py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Archivo
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map(a => (
                  <tr key={a.id} className="hover:bg-gray-50 transition-colors">
                    <td className="py-3 px-4 text-gray-500 whitespace-nowrap">
                      {formatDate(a.fecha)}
                    </td>
                    <td className="py-3 px-4 text-gray-900">
                      {a.comercio ?? '—'}
                    </td>
                    <td className="py-3 px-4">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TIPO_COLORS[a.tipo] ?? 'bg-gray-100 text-gray-600'}`}>
                        {TIPO_LABELS[a.tipo] ?? a.tipo}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-gray-600">
                      {a.categoria ?? '—'}
                    </td>
                    <td className="py-3 px-4 text-right font-medium text-gray-900 whitespace-nowrap">
                      {a.monto != null ? (
                        <>
                          {a.moneda === 'USD' ? `USD ${a.monto.toFixed(2)}` : formatARS(a.monto)}
                        </>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {a.gasto_id ? (
                        <span className="text-emerald-600 text-xs font-medium">Vinculado</span>
                      ) : (
                        <span className="text-gray-400 text-xs">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {a.drive_web_view_link ? (
                        <a
                          href={a.drive_web_view_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800 text-xs font-medium underline"
                        >
                          Ver en Drive
                        </a>
                      ) : (
                        <span className="text-gray-400 text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
