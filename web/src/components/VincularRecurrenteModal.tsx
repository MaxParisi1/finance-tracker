'use client'

import { useState, useTransition, useMemo } from 'react'
import type { GastoRecurrente } from '@/lib/types'
import { vincularRecurrenteAction } from '@/app/gastos/actions'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { Search, Link2, Repeat2 } from 'lucide-react'
import { formatARS } from '@/lib/utils'

const FRECUENCIA_LABELS: Record<string, string> = {
  mensual: 'Mensual',
  anual: 'Anual',
  semanal: 'Semanal',
}

interface Props {
  gastoId: string
  comercio?: string
  recurrentes: GastoRecurrente[]
  recurrenteActualId?: string | null
  onClose: (newRecurrenteId?: string | null) => void
}

export default function VincularRecurrenteModal({ gastoId, comercio, recurrentes, recurrenteActualId, onClose }: Props) {
  const [isPending, startTransition] = useTransition()
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(recurrenteActualId ?? null)

  const filtered = useMemo(() => {
    if (!search.trim()) return recurrentes
    const q = search.toLowerCase()
    return recurrentes.filter(r => r.descripcion.toLowerCase().includes(q))
  }, [recurrentes, search])

  function handleConfirm() {
    startTransition(async () => {
      try {
        await vincularRecurrenteAction(gastoId, selected, comercio)
        if (selected) {
          const rec = recurrentes.find(r => r.id === selected)
          toast.success(`Vinculado a "${rec?.descripcion}"`)
        } else {
          toast.success('Vínculo eliminado')
        }
        onClose(selected)
      } catch (e: any) {
        toast.error(e.message ?? 'Error al vincular')
      }
    })
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-card text-card-foreground rounded-2xl sm:rounded-2xl rounded-t-3xl shadow-modal border border-border w-full max-w-md flex flex-col animate-slide-up sm:animate-fade-in">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Link2 className="w-4 h-4 text-primary" />
            <h2 className="text-base font-semibold">Vincular a recurrente</h2>
          </div>
          <button onClick={() => onClose()} className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-muted">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>

        <div className="px-4 pt-4 pb-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
            <input
              type="text"
              placeholder="Buscar recurrente..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              autoFocus
              className="w-full h-9 pl-9 pr-3 rounded-lg border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        </div>

        <div className="px-4 pb-4 overflow-y-auto max-h-72 space-y-1.5">
          {recurrenteActualId && (
            <button
              onClick={() => setSelected(null)}
              className={`w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                selected === null ? 'bg-destructive/10 ring-1 ring-destructive/30' : 'hover:bg-muted/60'
              }`}
            >
              <span className="text-sm text-destructive font-medium">— Desvincular</span>
            </button>
          )}

          {filtered.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-6">Sin resultados</p>
          )}

          {filtered.map(r => {
            const isSelected = selected === r.id
            return (
              <button
                key={r.id}
                onClick={() => setSelected(r.id)}
                className={`w-full flex items-start gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                  isSelected ? 'bg-primary/10 ring-1 ring-primary/30' : 'hover:bg-muted/60'
                }`}
              >
                <Repeat2 className={`w-4 h-4 mt-0.5 flex-shrink-0 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`} />
                <div className="min-w-0 flex-1">
                  <p className={`text-sm font-medium ${isSelected ? 'text-primary' : 'text-foreground'}`}>
                    {r.descripcion}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {formatARS(r.monto_original)} {r.moneda} · {FRECUENCIA_LABELS[r.frecuencia] ?? r.frecuencia}
                    {r.proximo_vencimiento && ` · vence ${r.proximo_vencimiento}`}
                  </p>
                </div>
                {isSelected && (
                  <span className="text-xs text-primary font-semibold self-center">✓</span>
                )}
              </button>
            )
          })}
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-border">
          <Button variant="outline" size="sm" onClick={() => onClose()}>Cancelar</Button>
          <Button
            size="sm"
            onClick={handleConfirm}
            disabled={isPending || selected === recurrenteActualId}
          >
            {isPending ? 'Guardando...' : 'Confirmar'}
          </Button>
        </div>
      </div>
    </div>
  )
}
