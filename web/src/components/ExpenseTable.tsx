'use client'

import type { Gasto } from '@/lib/types'
import { formatARS, formatDate, MEDIO_PAGO_LABELS } from '@/lib/utils'

interface ExpenseTableProps {
  gastos: Gasto[]
  compact?: boolean
  onRowClick?: (gasto: Gasto) => void
  archivoCounts?: Record<string, number>
}

export default function ExpenseTable({ gastos, compact = false, onRowClick, archivoCounts }: ExpenseTableProps) {
  if (gastos.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400 text-sm">
        No hay gastos registrados en este período.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Fecha
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Descripción
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Categoría
            </th>
            {!compact && (
              <th className="text-left py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
                Medio de pago
              </th>
            )}
            <th className="text-right py-3 px-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Monto
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {gastos.map(g => (
            <tr
              key={g.id}
              onClick={() => onRowClick?.(g)}
              className={`hover:bg-gray-50 transition-colors ${onRowClick ? 'cursor-pointer' : ''}`}
            >
              <td className="py-3 px-4 text-gray-500 whitespace-nowrap">
                {formatDate(g.fecha)}
              </td>
              <td className="py-3 px-4">
                <div className="flex items-center gap-1.5">
                  <span className="text-gray-900">{g.descripcion}</span>
                  {g.cuotas > 1 && (
                    <span className="text-xs text-gray-400">
                      ({g.cuota_actual}/{g.cuotas})
                    </span>
                  )}
                  {g.moneda === 'USD' && (
                    <span className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">
                      USD
                    </span>
                  )}
                  {archivoCounts && archivoCounts[g.id] > 0 && (
                    <span
                      className="text-xs bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded flex items-center gap-0.5"
                      title={`${archivoCounts[g.id]} archivo(s) en Drive`}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-3 h-3">
                        <path fillRule="evenodd" d="M4 2a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7.414A2 2 0 0 0 13.414 6L10 2.586A2 2 0 0 0 8.586 2H4Zm6 5.5a.5.5 0 1 0-1 0V9H7.5a.5.5 0 0 0 0 1H9v1.5a.5.5 0 1 0 1 0V10h1.5a.5.5 0 1 0 0-1H10V7.5Z" clipRule="evenodd" />
                      </svg>
                      {archivoCounts[g.id]}
                    </span>
                  )}
                </div>
              </td>
              <td className="py-3 px-4">
                <span className="text-gray-600">{g.categoria ?? '—'}</span>
              </td>
              {!compact && (
                <td className="py-3 px-4 text-gray-500">
                  {MEDIO_PAGO_LABELS[g.medio_pago] ?? g.medio_pago}
                </td>
              )}
              <td className="py-3 px-4 text-right font-medium text-gray-900 whitespace-nowrap">
                {formatARS(g.monto_ars)}
                {g.moneda === 'USD' && (
                  <span className="block text-xs text-gray-400 font-normal">
                    USD {g.monto_original.toFixed(2)}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
