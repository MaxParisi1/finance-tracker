'use client'

import { useState, useTransition, useMemo } from 'react'
import { X, Search, Link2, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { vincularArchivoExistenteAction } from '@/app/comprobantes/actions'
import { toast } from 'sonner'
import { formatARS, formatDate, cn } from '@/lib/utils'
import type { Gasto } from '@/lib/types'

interface Props {
  archivoId: string
  comercio?: string | null
  gastos: Gasto[]
  onClose: () => void
}

export default function VincularGastoModal({ archivoId, comercio, gastos, onClose }: Props) {
  const [search, setSearch] = useState(comercio ?? '')
  const [selected, setSelected] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()
  const [done, setDone] = useState(false)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return gastos.slice(0, 30)
    return gastos
      .filter(g => {
        const desc = (g.descripcion ?? '').toLowerCase()
        const com = (g.comercio ?? '').toLowerCase()
        return desc.includes(q) || com.includes(q)
      })
      .slice(0, 30)
  }, [gastos, search])

  function handleConfirm() {
    if (!selected) return
    startTransition(async () => {
      try {
        await vincularArchivoExistenteAction(archivoId, selected)
        setDone(true)
        toast.success('Comprobante vinculado al gasto')
        setTimeout(onClose, 800)
      } catch {
        toast.error('No se pudo vincular el comprobante')
      }
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-background border border-border rounded-2xl shadow-xl w-full max-w-md flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <Link2 className="w-4 h-4 text-indigo-500" />
            <h2 className="font-semibold text-foreground text-sm">Vincular a un gasto</h2>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Search */}
        <div className="px-4 py-3 border-b border-border flex-shrink-0">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
            <input
              autoFocus
              type="text"
              value={search}
              onChange={e => { setSearch(e.target.value); setSelected(null) }}
              placeholder="Buscar por comercio o descripción…"
              className={cn(
                'w-full h-9 rounded-lg border border-input bg-muted/30 pl-9 pr-3 text-sm',
                'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors',
              )}
            />
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {filtered.length === 0 ? (
            <p className="text-center text-muted-foreground text-sm py-8">Sin resultados</p>
          ) : (
            <ul className="space-y-0.5">
              {filtered.map(g => (
                <li key={g.id}>
                  <button
                    onClick={() => setSelected(g.id === selected ? null : g.id)}
                    className={cn(
                      'w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-left transition-colors',
                      selected === g.id
                        ? 'bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/30'
                        : 'hover:bg-muted/50',
                    )}
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">
                        {g.comercio || g.descripcion}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {formatDate(g.fecha)} · {g.categoria ?? '—'}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 ml-3 flex-shrink-0">
                      <span className="text-sm font-semibold text-foreground">
                        {formatARS(g.monto_ars ?? 0)}
                      </span>
                      {selected === g.id && (
                        <Check className="w-4 h-4 text-indigo-500" />
                      )}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-border flex gap-2 justify-end flex-shrink-0">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={isPending}>
            Cancelar
          </Button>
          <Button
            size="sm"
            onClick={handleConfirm}
            disabled={!selected || isPending || done}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            {done ? <Check className="w-4 h-4" /> : isPending ? 'Vinculando…' : 'Vincular'}
          </Button>
        </div>
      </div>
    </div>
  )
}
