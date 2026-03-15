'use client'

import { useState, useTransition } from 'react'
import { formatARS } from '@/lib/utils'
import { upsertPresupuestoAction, deletePresupuestoAction } from '@/app/presupuestos/actions'

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
        await upsertPresupuestoAction({
          categoria: newCategoria,
          mes,
          anio,
          monto_limite: parseFloat(newLimite),
        })
        setShowNew(false)
        setNewCategoria('')
        setNewLimite('')
      } catch (e: any) {
        setError(e.message)
      }
    })
  }

  function handleSaveEdit(p: PresupuestoConGasto) {
    setError(null)
    startTransition(async () => {
      try {
        await upsertPresupuestoAction({
          categoria: p.categoria,
          mes,
          anio,
          monto_limite: parseFloat(editLimite) || p.monto_limite,
        })
        setEditingId(null)
      } catch (e: any) {
        setError(e.message)
      }
    })
  }

  function handleDelete(id: string) {
    setError(null)
    startTransition(async () => {
      try {
        await deletePresupuestoAction(id)
      } catch (e: any) {
        setError(e.message)
      }
    })
  }

  return (
    <div className="space-y-4">
      {/* Presupuestos existentes */}
      {presupuestos.length === 0 && !showNew && (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
          <p className="text-gray-400 text-sm">No hay presupuestos configurados para este mes.</p>
          <button
            onClick={() => setShowNew(true)}
            className="mt-4 text-sm bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg transition-colors"
          >
            + Agregar primer presupuesto
          </button>
        </div>
      )}

      {presupuestos.map(p => {
        const excedido = p.pct > 100
        const cercano = p.pct >= 80 && p.pct <= 100
        const isEditing = editingId === p.id

        return (
          <div key={p.id} className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900">{p.categoria}</span>
                  {excedido && (
                    <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded font-medium">
                      Excedido
                    </span>
                  )}
                  {cercano && (
                    <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium">
                      {p.pct}%
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-400 mt-0.5">
                  {formatARS(p.gastado)} gastado de {formatARS(p.monto_limite)}
                  {p.monto_limite > p.gastado && (
                    <span className="text-emerald-600"> · {formatARS(p.monto_limite - p.gastado)} disponible</span>
                  )}
                  {excedido && (
                    <span className="text-red-600"> · {formatARS(p.gastado - p.monto_limite)} excedido</span>
                  )}
                </p>
              </div>

              <div className="flex items-center gap-2 ml-4">
                {isEditing ? (
                  <>
                    <input
                      type="number"
                      value={editLimite}
                      onChange={e => setEditLimite(e.target.value)}
                      className="w-28 border border-gray-300 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                      placeholder={String(p.monto_limite)}
                      autoFocus
                    />
                    <button
                      onClick={() => handleSaveEdit(p)}
                      disabled={isPending}
                      className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white px-2 py-1 rounded-lg transition-colors disabled:opacity-50"
                    >
                      OK
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="text-xs text-gray-400 hover:text-gray-600 px-1"
                    >
                      ✕
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => { setEditingId(p.id); setEditLimite(String(p.monto_limite)) }}
                      className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => handleDelete(p.id)}
                      disabled={isPending}
                      className="text-xs text-gray-300 hover:text-red-400 transition-colors"
                    >
                      ✕
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Barra de progreso */}
            <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  excedido ? 'bg-red-500' : cercano ? 'bg-amber-400' : 'bg-emerald-500'
                }`}
                style={{ width: `${Math.min(p.pct, 100)}%` }}
              />
            </div>
          </div>
        )
      })}

      {/* Formulario nuevo presupuesto */}
      {showNew ? (
        <div className="bg-white rounded-xl border border-emerald-200 p-5">
          <p className="text-sm font-medium text-gray-900 mb-3">Nuevo presupuesto</p>
          <div className="flex gap-3 flex-wrap">
            <select
              value={newCategoria}
              onChange={e => setNewCategoria(e.target.value)}
              className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <option value="">Seleccionar categoría...</option>
              {categoriasDisponibles.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <input
              type="number"
              value={newLimite}
              onChange={e => setNewLimite(e.target.value)}
              placeholder="Límite ARS"
              className="w-40 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <button
              onClick={handleSaveNew}
              disabled={isPending || !newCategoria || !newLimite}
              className="text-sm bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              {isPending ? '...' : 'Agregar'}
            </button>
            <button
              onClick={() => { setShowNew(false); setNewCategoria(''); setNewLimite('') }}
              className="text-sm text-gray-400 hover:text-gray-600 px-2"
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : presupuestos.length > 0 && (
        <button
          onClick={() => setShowNew(true)}
          className="w-full py-3 border-2 border-dashed border-gray-200 rounded-xl text-sm text-gray-400 hover:border-emerald-300 hover:text-emerald-600 transition-colors"
        >
          + Agregar categoría
        </button>
      )}

      {error && (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-4 py-2">{error}</p>
      )}
    </div>
  )
}
