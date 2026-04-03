'use client'

import { useState, useTransition } from 'react'
import type { GastoRecurrente } from '@/lib/types'
import { createRecurrenteAction, updateRecurrenteAction, toggleRecurrenteAction } from '@/app/recurrentes/actions'
import { MEDIO_PAGO_LABELS } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ShimmerButton } from '@/components/magicui/shimmer-button'
import { toast } from 'sonner'

const FRECUENCIA_OPTIONS = [
  { value: 'mensual', label: 'Mensual' },
  { value: 'anual', label: 'Anual' },
  { value: 'semanal', label: 'Semanal' },
]

const MEDIO_PAGO_OPTIONS = Object.entries(MEDIO_PAGO_LABELS)

const labelClass = 'block text-xs font-medium text-muted-foreground mb-1.5'
const fieldClass = cn(
  'w-full h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'placeholder:text-muted-foreground',
  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors'
)

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
          toast.success('Recurrente actualizado')
        } else {
          await createRecurrenteAction(form)
          toast.success('Gasto recurrente creado')
        }
        onClose()
      } catch (e: any) {
        const msg = e.message ?? 'Error al guardar'
        setError(msg)
        toast.error(msg)
      }
    })
  }

  function handleToggle() {
    setError(null)
    startTransition(async () => {
      try {
        await toggleRecurrenteAction(recurrente!.id, !recurrente!.activo)
        toast.success(recurrente!.activo ? 'Recurrente desactivado' : 'Recurrente activado')
        onClose()
      } catch (e: any) {
        const msg = e.message ?? 'Error'
        setError(msg)
        toast.error(msg)
      }
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-card text-card-foreground rounded-2xl sm:rounded-2xl rounded-t-3xl shadow-modal border border-border w-full max-w-md flex flex-col animate-slide-up sm:animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-base font-semibold">
            {isEdit ? 'Editar recurrente' : 'Nuevo gasto recurrente'}
          </h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-muted"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <div className="px-6 py-4 space-y-4 overflow-y-auto max-h-[60vh]">
          <div>
            <label className={labelClass}>Descripción</label>
            <input
              type="text" value={form.descripcion}
              onChange={e => set('descripcion', e.target.value)}
              className={fieldClass}
              placeholder="Netflix, Spotify, Expensas..."
            />
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label className={labelClass}>Monto</label>
              <input
                type="number" step="0.01" value={form.monto_original}
                onChange={e => set('monto_original', parseFloat(e.target.value) || 0)}
                className={fieldClass}
              />
            </div>
            <div>
              <label className={labelClass}>Moneda</label>
              <select value={form.moneda} onChange={e => set('moneda', e.target.value)} className={cn(fieldClass, 'w-24 cursor-pointer')}>
                <option value="ARS">ARS</option>
                <option value="USD">USD</option>
              </select>
            </div>
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label className={labelClass}>Frecuencia</label>
              <select value={form.frecuencia} onChange={e => set('frecuencia', e.target.value)} className={cn(fieldClass, 'cursor-pointer')}>
                {FRECUENCIA_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <label className={labelClass}>Día del mes</label>
              <input
                type="number" min={1} max={31} value={form.dia_del_mes}
                onChange={e => set('dia_del_mes', parseInt(e.target.value) || 1)}
                className={cn(fieldClass, 'w-20')}
              />
            </div>
          </div>

          <div>
            <label className={labelClass}>Categoría</label>
            <select value={form.categoria} onChange={e => set('categoria', e.target.value)} className={cn(fieldClass, 'cursor-pointer')}>
              <option value="">Sin categoría</option>
              {categorias.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div>
            <label className={labelClass}>Medio de pago</label>
            <select value={form.medio_pago} onChange={e => set('medio_pago', e.target.value)} className={cn(fieldClass, 'cursor-pointer')}>
              {MEDIO_PAGO_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="checkbox"
              checked={form.no_materializar}
              onChange={e => setForm(prev => ({ ...prev, no_materializar: e.target.checked }))}
              className="mt-0.5 h-4 w-4 rounded border-input accent-primary"
            />
            <div>
              <p className="text-sm font-medium text-foreground">Se debita automáticamente de tarjeta</p>
              <p className="text-xs text-muted-foreground mt-0.5">No materializar — el gasto se registra solo vía email</p>
            </div>
          </label>

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border gap-3">
          {isEdit ? (
            <>
              {confirmDeactivate ? (
                <>
                  <span className="text-sm text-muted-foreground">
                    ¿{recurrente!.activo ? 'Desactivar' : 'Activar'} "{recurrente!.descripcion}"?
                  </span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => setConfirmDeactivate(false)}>Cancelar</Button>
                    <Button
                      size="sm"
                      variant={recurrente!.activo ? 'destructive' : 'default'}
                      onClick={handleToggle}
                      disabled={isPending}
                    >
                      {isPending ? '...' : recurrente!.activo ? 'Desactivar' : 'Activar'}
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <Button
                    variant="ghost" size="sm"
                    onClick={() => setConfirmDeactivate(true)}
                    className={recurrente!.activo ? 'text-muted-foreground hover:text-destructive' : 'text-success hover:text-success/80'}
                  >
                    {recurrente!.activo ? 'Desactivar' : 'Activar'}
                  </Button>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
                    <ShimmerButton onClick={handleSave} disabled={isPending} shimmerDuration="2s" borderRadius="6px" className="h-8 px-3 text-xs">
                      {isPending ? 'Guardando...' : 'Guardar'}
                    </ShimmerButton>
                  </div>
                </>
              )}
            </>
          ) : (
            <>
              <div />
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
                <ShimmerButton onClick={handleSave} disabled={isPending} shimmerDuration="2s" borderRadius="6px" className="h-8 px-3 text-xs">
                  {isPending ? 'Guardando...' : 'Agregar'}
                </ShimmerButton>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
