'use client'

import { useState, useTransition } from 'react'
import { formatARS } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { upsertPresupuestoAction, deletePresupuestoAction } from '@/app/presupuestos/actions'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Plus, X, Pencil } from 'lucide-react'
import { toast } from 'sonner'
import { BorderBeam } from '@/components/magicui/border-beam'

interface PresupuestoConGasto {
  id: string
  categoria: string
  mes: number
  anio: number
  monto_limite: number
  gastado: number
  pct: number
}

interface Props {
  presupuestos: PresupuestoConGasto[]
  categorias: string[]
  mes: number
  anio: number
}

const inputClass = cn(
  'h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'ring-offset-background placeholder:text-muted-foreground',
  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors'
)

const selectClass = cn(inputClass, 'cursor-pointer')

export default function PresupuestosView({ presupuestos, categorias, mes, anio }: Props) {
  const [isPending, startTransition] = useTransition()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [newCategoria, setNewCategoria] = useState('')
  const [newLimite, setNewLimite] = useState('')
  const [editLimite, setEditLimite] = useState('')
  const [error, setError] = useState<string | null>(null)

  const categoriasUsadas = new Set(presupuestos.map(p => p.categoria))
  const categoriasDisponibles = categorias.filter(c => !categoriasUsadas.has(c))

  function handleSaveNew() {
    if (!newCategoria || !newLimite) return
    setError(null)
    startTransition(async () => {
      try {
        await upsertPresupuestoAction({ categoria: newCategoria, mes, anio, monto_limite: parseFloat(newLimite) })
        setShowNew(false)
        setNewCategoria('')
        setNewLimite('')
        toast.success('Presupuesto creado')
      } catch (e: any) {
        setError(e.message)
        toast.error(e.message ?? 'Error al crear presupuesto')
      }
    })
  }

  function handleSaveEdit(p: PresupuestoConGasto) {
    setError(null)
    startTransition(async () => {
      try {
        await upsertPresupuestoAction({ categoria: p.categoria, mes, anio, monto_limite: parseFloat(editLimite) || p.monto_limite })
        setEditingId(null)
        toast.success('Presupuesto actualizado')
      } catch (e: any) {
        setError(e.message)
        toast.error(e.message ?? 'Error al actualizar presupuesto')
      }
    })
  }

  function handleDelete(id: string) {
    setError(null)
    startTransition(async () => {
      try {
        await deletePresupuestoAction(id)
        toast.success('Presupuesto eliminado')
      } catch (e: any) {
        setError(e.message)
        toast.error(e.message ?? 'Error al eliminar')
      }
    })
  }

  return (
    <div className="space-y-3">
      {/* Empty state */}
      {presupuestos.length === 0 && !showNew && (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground text-sm mb-4">No hay presupuestos configurados para este mes.</p>
            <Button onClick={() => setShowNew(true)}>
              <Plus className="w-4 h-4 mr-1" />
              Agregar primer presupuesto
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Presupuestos existentes */}
      {presupuestos.map(p => {
        const excedido = p.pct > 100
        const cercano  = p.pct >= 80 && p.pct <= 100
        const isEditing = editingId === p.id

        return (
          <Card key={p.id} className="relative overflow-hidden">
            {excedido && (
              <BorderBeam colorFrom="#ef4444" colorTo="#f97316" duration={3} size={80} borderWidth={1.5} />
            )}
            {cercano && !excedido && (
              <BorderBeam colorFrom="#f59e0b" colorTo="#eab308" duration={4} size={60} borderWidth={1} />
            )}
            <CardContent className="py-4">
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-foreground">{p.categoria}</span>
                    {excedido && <Badge variant="destructive">Excedido</Badge>}
                    {cercano  && <Badge variant="warning">{p.pct}%</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 tabular">
                    {formatARS(p.gastado)} de {formatARS(p.monto_limite)}
                    {!excedido && (
                      <span className="text-success"> · {formatARS(p.monto_limite - p.gastado)} disponible</span>
                    )}
                    {excedido && (
                      <span className="text-destructive"> · {formatARS(p.gastado - p.monto_limite)} excedido</span>
                    )}
                  </p>
                </div>

                <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                  {isEditing ? (
                    <>
                      <input
                        type="number"
                        value={editLimite}
                        onChange={e => setEditLimite(e.target.value)}
                        className={cn(inputClass, 'w-28')}
                        placeholder={String(p.monto_limite)}
                        autoFocus
                      />
                      <Button size="sm" onClick={() => handleSaveEdit(p)} disabled={isPending}>OK</Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button
                        size="sm" variant="ghost"
                        onClick={() => { setEditingId(p.id); setEditLimite(String(p.monto_limite)) }}
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        size="sm" variant="ghost"
                        onClick={() => handleDelete(p.id)}
                        disabled={isPending}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </>
                  )}
                </div>
              </div>

              <Progress
                value={Math.min(p.pct, 100)}
                indicatorClassName={cn(
                  excedido ? 'bg-destructive' :
                  cercano  ? 'bg-warning' :
                             'gradient-primary'
                )}
              />
            </CardContent>
          </Card>
        )
      })}

      {/* Formulario nuevo presupuesto */}
      {showNew ? (
        <Card className="border-primary/30">
          <CardContent className="py-4">
            <p className="text-sm font-medium text-foreground mb-3">Nuevo presupuesto</p>
            <div className="flex gap-2 flex-wrap">
              <select value={newCategoria} onChange={e => setNewCategoria(e.target.value)} className={cn(selectClass, 'flex-1 min-w-[160px]')}>
                <option value="">Seleccionar categoría...</option>
                {categoriasDisponibles.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <input
                type="number"
                value={newLimite}
                onChange={e => setNewLimite(e.target.value)}
                placeholder="Límite ARS"
                className={cn(inputClass, 'w-36')}
              />
              <Button onClick={handleSaveNew} disabled={isPending || !newCategoria || !newLimite}>
                {isPending ? '...' : 'Agregar'}
              </Button>
              <Button variant="ghost" onClick={() => { setShowNew(false); setNewCategoria(''); setNewLimite('') }}>
                Cancelar
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : presupuestos.length > 0 && (
        <button
          onClick={() => setShowNew(true)}
          className="w-full py-3 border-2 border-dashed border-border rounded-xl text-sm text-muted-foreground hover:border-primary/50 hover:text-primary transition-colors"
        >
          <Plus className="w-4 h-4 inline mr-1" />
          Agregar categoría
        </button>
      )}

      {error && (
        <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-4 py-2">{error}</p>
      )}
    </div>
  )
}
