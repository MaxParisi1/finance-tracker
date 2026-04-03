'use client'

import type { Gasto } from '@/lib/types'
import { formatARS, formatDate, MEDIO_PAGO_LABELS } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { Paperclip } from 'lucide-react'

interface ExpenseTableProps {
  gastos: Gasto[]
  compact?: boolean
  onRowClick?: (gasto: Gasto) => void
  archivoCounts?: Record<string, number>
}

export default function ExpenseTable({ gastos, compact = false, onRowClick, archivoCounts }: ExpenseTableProps) {
  if (gastos.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground text-sm">
        No hay gastos registrados en este período.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Fecha
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Comercio / Descripción
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Categoría
            </th>
            {!compact && (
              <th className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Medio de pago
              </th>
            )}
            <th className="text-right py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Monto
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {gastos.map(g => (
            <tr
              key={g.id}
              onClick={() => onRowClick?.(g)}
              className={cn(
                'transition-colors',
                onRowClick && 'cursor-pointer hover:bg-muted/50'
              )}
            >
              <td className="py-3 px-4 text-muted-foreground whitespace-nowrap tabular">
                {formatDate(g.fecha)}
              </td>
              <td className="py-3 px-4">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-foreground font-medium">{g.comercio ?? g.descripcion}</span>
                  {g.comercio && (
                    <span className="text-xs text-muted-foreground truncate max-w-[180px]">{g.descripcion}</span>
                  )}
                  {g.cuotas > 1 && (
                    <span className="text-xs text-muted-foreground">
                      ({g.cuota_actual}/{g.cuotas})
                    </span>
                  )}
                  {g.moneda === 'USD' && (
                    <span className="text-xs bg-blue-500/10 text-blue-500 dark:text-blue-400 px-1.5 py-0.5 rounded-full font-medium">
                      USD
                    </span>
                  )}
                  {archivoCounts && archivoCounts[g.id] > 0 && (
                    <span
                      className="inline-flex items-center gap-0.5 text-xs bg-success/10 text-success px-1.5 py-0.5 rounded-full font-medium"
                      title={`${archivoCounts[g.id]} archivo(s) en Drive`}
                    >
                      <Paperclip className="w-2.5 h-2.5" />
                      {archivoCounts[g.id]}
                    </span>
                  )}
                </div>
              </td>
              <td className="py-3 px-4">
                <span className="text-foreground/80">{g.categoria ?? '—'}</span>
              </td>
              {!compact && (
                <td className="py-3 px-4 text-muted-foreground">
                  {MEDIO_PAGO_LABELS[g.medio_pago] ?? g.medio_pago}
                </td>
              )}
              <td className="py-3 px-4 text-right font-semibold text-foreground whitespace-nowrap tabular">
                {formatARS(g.monto_ars)}
                {g.moneda === 'USD' && (
                  <span className="block text-xs text-muted-foreground font-normal">
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
