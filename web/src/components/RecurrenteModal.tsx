'use client'

import { useState, useTransition } from 'react'
import type { GastoRecurrente } from '@/lib/types'
import { createRecurrenteAction, updateRecurrenteAction, toggleRecurrenteAction } from '@/app/recurrentes/actions'
import { MEDIO_PAGO_LABELS } from '@/lib/utils'

const FRECUENCIA_OPTIONS = [
  { value: 'mensual', label: 'Mensual' },
  { value: 'anual', label: 'Anual' },
  { value: 'semanal', label: 'Semanal' },
]

const MEDIO_PAGO_OPTIONS = Object.entries(MEDIO_PAGO_LABELS)

interface Props {
  recurrente?: GastoRecurrente
  categorias: string[]
  onClose: () => void
}

export default function RecurrenteModal({ recurrente, categorias, onClose }: Props) {
  const isEdit = !!recurrente
  const [isPending, startTransition] = useTransition()
  const [confirmDeactivate, setConfirmDeactivate] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [form, setForm] = useState({
    descripcion: recurrente?.descripcion ?? '',
    monto_original: recurrente?.monto_original ?? 0,
    moneda: recurrente?.moneda ?? 'ARS',
    categoria: recurrente?.categoria ?? '',
    medio_pago: recurrente?.medio_pago ?? 'debito',
    frecuencia: recurrente?.frecuencia ?? 'mensual',
    dia_del_mes: recurrente?.dia_del_mes ?? 1,
    no_materializar: recurrente?.no_materializar ?? false,
  })

  function set(field: string, value: string | number) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  function handleSave() {
    setError(null)
    startTransition(async () => {
      try {
        if (isEdit) {
          await updateRecurrenteAction(recurrente!.id, form)
        } else {
          await createRecurrenteAction(form)
        }
        onClose()
      } catch (e: any) {
        setError(e.message ?? 'Error al guardar')
      }
    })
  }

  function handleToggle() {
    setError(null)
    startTransition(async () => {
      try {
        await toggleRecurrenteAction(recurrente!.id, !recurrente!.activo)
        onClose()
      } catch (e: any) {
        setError(e.message ?? 'Error')
      }
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-900">
            {isEdit ? 'Editar recurrente' : 'Nuevo gasto recurrente'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <div className="px-6 py-4 space-y-4 overflow-y-auto max-h-[60vh]">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Descripción</label>
            <input
              type="text"
              value={form.descripcion}
              onChange={e => set('descripcion', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              placeholder="Netflix, Spotify, Expensas..."
            />
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-500 mb-1">Monto</label>
              <input
                type="number"
                step="0.01"
                value={form.monto_original}
                onChange={e => set('monto_original', parseFloat(e.target.value) || 0)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Moneda</label>
              <select
                value={form.moneda}
                onChange={e => set('moneda', e.target.value)}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              >
                <option value="ARS">ARS</option>
                <option value="USD">USD</option>
              </select>
            </div>
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-500 mb-1">Frecuencia</label>
              <select
                value={form.frecuencia}
                onChange={e => set('frecuencia', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              >
                {FRECUENCIA_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Día del mes</label>
              <input
                type="number"
                min={1}
                max={31}
                value={form.dia_del_mes}
                onChange={e => set('dia_del_mes', parseInt(e.target.value) || 1)}
                className="w-20 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Categoría</label>
            <select
              value={form.categoria}
              onChange={e => set('categoria', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <option value="">Sin categoría</option>
              {categorias.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Medio de pago</label>
            <select
              value={form.medio_pago}
              onChange={e => set('medio_pago', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              {MEDIO_PAGO_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={form.no_materializar}
              onChange={e => setForm(prev => ({ ...prev, no_materializar: e.target.checked }))}
              className="mt-0.5 h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
            />
            <div>
              <p className="text-sm font-medium text-gray-700">Se debita automáticamente de tarjeta</p>
              <p className="text-xs text-gray-400 mt-0.5">No materializar — el gasto se registra solo vía email</p>
            </div>
          </label>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 gap-3">
          {isEdit ? (
            <>
              {confirmDeactivate ? (
                <>
                  <span className="text-sm text-gray-600">
                    ¿{recurrente!.activo ? 'Desactivar' : 'Activar'} "{recurrente!.descripcion}"?
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setConfirmDeactivate(false)}
                      className="text-sm px-3 py-1.5 rounded-lg border border-gray-300 hover:bg-gray-50 transition-colors"
                    >
                      Cancelar
                    </button>
                    <button
                      onClick={handleToggle}
                      disabled={isPending}
                      className={`text-sm px-3 py-1.5 rounded-lg text-white transition-colors disabled:opacity-50 ${
                        recurrente!.activo
                          ? 'bg-red-600 hover:bg-red-700'
                          : 'bg-emerald-600 hover:bg-emerald-700'
                      }`}
                    >
                      {isPending ? '...' : recurrente!.activo ? 'Desactivar' : 'Activar'}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <button
                    onClick={() => setConfirmDeactivate(true)}
                    className={`text-sm transition-colors ${
                      recurrente!.activo ? 'text-red-500 hover:text-red-700' : 'text-emerald-600 hover:text-emerald-700'
                    }`}
                  >
                    {recurrente!.activo ? 'Desactivar' : 'Activar'}
                  </button>
                  <div className="flex gap-2">
                    <button
                      onClick={onClose}
                      className="text-sm px-4 py-2 rounded-lg border border-gray-300 hover:bg-gray-50 transition-colors"
                    >
                      Cancelar
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={isPending}
                      className="text-sm px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition-colors disabled:opacity-50"
                    >
                      {isPending ? 'Guardando...' : 'Guardar'}
                    </button>
                  </div>
                </>
              )}
            </>
          ) : (
            <>
              <div />
              <div className="flex gap-2">
                <button
                  onClick={onClose}
                  className="text-sm px-4 py-2 rounded-lg border border-gray-300 hover:bg-gray-50 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleSave}
                  disabled={isPending}
                  className="text-sm px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition-colors disabled:opacity-50"
                >
                  {isPending ? 'Guardando...' : 'Agregar'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
