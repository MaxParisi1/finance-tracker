'use client'

import { useState, useTransition } from 'react'
import type { PlanCuota } from '@/lib/types'
import { createPlanCuotaAction, updatePlanCuotaAction, togglePlanCuotaAction } from '@/app/cuotas/actions'
import { MEDIO_PAGO_LABELS } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ShimmerButton } from '@/components/magicui/shimmer-button'
import { X } from 'lucide-react'
import { toast } from 'sonner'

const MEDIO_PAGO_OPTIONS = Object.entries(MEDIO_PAGO_LABELS)

const labelClass = 'block text-xs font-medium text-muted-foreground mb-1.5'
const fieldClass = cn(
  'w-full h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors',
)

interface Props {
  plan?: PlanCuota
  categorias: string[]
  onClose: () => void
}

export default function PlanCuotaModal({ plan, categorias, onClose }: Props) {
  const isEdit = !!plan
  const [isPending, startTransition] = useTransition()
  const [confirmDeactivate, setConfirmDeactivate] = useState(false)

  const [form, setForm] = useState({
    descripcion: plan?.descripcion ?? '',
    comercio: plan?.comercio ?? '',
    categoria: plan?.categoria ?? '',
    medio_pago: plan?.medio_pago ?? 'debito',
    tipo: (plan?.tipo ?? 'fijo') as 'fijo' | 'variable',
    monto_cuota: plan?.monto_cuota?.toString() ?? '',
    moneda: plan?.moneda ?? 'ARS',
    cuotas_total: plan?.cuotas_total?.toString() ?? '',
    cuota_actual: plan?.cuota_actual?.toString() ?? '1',
    dia_del_mes: plan?.dia_del_mes?.toString() ?? '1',
  })

  function set(field: string, value: string) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  function handleSave() {
    if (!form.descripcion || !form.cuotas_total || !form.cuota_actual || !form.dia_del_mes) {
      toast.error('Completá los campos obligatorios')
      return
    }
    if (form.tipo === 'fijo' && !form.monto_cuota) {
      toast.error('Ingresá el monto de la cuota')
      return
    }

    startTransition(async () => {
      try {
        const payload = {
          descripcion: form.descripcion.trim(),
          comercio: form.comercio.trim() || undefined,
          categoria: form.categoria || undefined,
          medio_pago: form.medio_pago,
          tipo: form.tipo,
          monto_cuota: form.tipo === 'fijo' ? parseFloat(form.monto_cuota) : null,
          moneda: form.moneda,
          cuotas_total: parseInt(form.cuotas_total),
          cuota_actual: parseInt(form.cuota_actual),
          dia_del_mes: parseInt(form.dia_del_mes),
        }

        if (isEdit) {
          await updatePlanCuotaAction(plan!.id, payload)
          toast.success('Plan actualizado')
        } else {
          await createPlanCuotaAction(payload)
          toast.success('Plan de cuotas registrado')
        }
        onClose()
      } catch (e: any) {
        toast.error(e.message ?? 'Error al guardar')
      }
    })
  }

  function handleToggle() {
    startTransition(async () => {
      try {
        await togglePlanCuotaAction(plan!.id, !plan!.activo)
        toast.success(plan!.activo ? 'Plan pausado' : 'Plan reactivado')
        onClose()
      } catch (e: any) {
        toast.error(e.message ?? 'Error')
      }
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-card text-card-foreground rounded-2xl rounded-t-3xl sm:rounded-2xl shadow-modal border border-border w-full max-w-md flex flex-col animate-slide-up sm:animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-base font-semibold">
            {isEdit ? 'Editar plan de cuotas' : 'Registrar cuotas existentes'}
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-muted">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form */}
        <div className="px-6 py-4 space-y-4 overflow-y-auto max-h-[65vh]">

          {/* Tipo toggle */}
          <div>
            <label className={labelClass}>Tipo de cuota</label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { value: 'fijo', label: 'Sin interés', sub: 'Monto fijo · se registra solo' },
                { value: 'variable', label: 'Con interés', sub: 'Monto varía · registrás vos' },
              ].map(t => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => set('tipo', t.value)}
                  className={cn(
                    'rounded-xl border px-3 py-2.5 text-left transition-all duration-150',
                    form.tipo === t.value
                      ? 'border-primary bg-primary/8 text-primary'
                      : 'border-border text-muted-foreground hover:border-primary/40',
                  )}
                >
                  <p className="text-sm font-semibold">{t.label}</p>
                  <p className="text-[10px] mt-0.5 leading-tight opacity-80">{t.sub}</p>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className={labelClass}>Descripción *</label>
            <input
              type="text"
              value={form.descripcion}
              onChange={e => set('descripcion', e.target.value)}
              placeholder="Hipoteca BBVA, TV Samsung, Notebook..."
              className={fieldClass}
            />
          </div>

          <div>
            <label className={labelClass}>Comercio / Entidad</label>
            <input
              type="text"
              value={form.comercio}
              onChange={e => set('comercio', e.target.value)}
              placeholder="Banco, tienda, financiera..."
              className={fieldClass}
            />
          </div>

          {/* Monto (solo fijo) */}
          {form.tipo === 'fijo' && (
            <div className="flex gap-3">
              <div className="flex-1">
                <label className={labelClass}>Monto por cuota *</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.monto_cuota}
                  onChange={e => set('monto_cuota', e.target.value)}
                  className={fieldClass}
                  placeholder="0"
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
          )}

          {form.tipo === 'variable' && (
            <div>
              <label className={labelClass}>Moneda</label>
              <select value={form.moneda} onChange={e => set('moneda', e.target.value)} className={cn(fieldClass, 'w-full cursor-pointer')}>
                <option value="ARS">ARS</option>
                <option value="USD">USD</option>
              </select>
            </div>
          )}

          {/* Cuotas */}
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-1">
              <label className={labelClass}>Total cuotas *</label>
              <input
                type="number"
                min="1"
                value={form.cuotas_total}
                onChange={e => set('cuotas_total', e.target.value)}
                className={fieldClass}
                placeholder="24"
              />
            </div>
            <div className="col-span-1">
              <label className={labelClass}>Cuota actual *</label>
              <input
                type="number"
                min="1"
                value={form.cuota_actual}
                onChange={e => set('cuota_actual', e.target.value)}
                className={fieldClass}
                placeholder="5"
              />
            </div>
            <div className="col-span-1">
              <label className={labelClass}>Día del mes *</label>
              <input
                type="number"
                min="1"
                max="31"
                value={form.dia_del_mes}
                onChange={e => set('dia_del_mes', e.target.value)}
                className={fieldClass}
                placeholder="10"
              />
            </div>
          </div>

          {/* Info calculada */}
          {form.cuotas_total && form.cuota_actual && (
            <p className="text-xs text-muted-foreground bg-muted/60 rounded-lg px-3 py-2">
              Quedan <span className="font-semibold text-foreground">
                {Math.max(0, parseInt(form.cuotas_total) - parseInt(form.cuota_actual) + 1)}
              </span> cuotas por pagar de {form.cuotas_total} totales.
            </p>
          )}

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
              {MEDIO_PAGO_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border gap-3">
          {isEdit ? (
            <>
              {confirmDeactivate ? (
                <>
                  <span className="text-sm text-muted-foreground">
                    ¿{plan!.activo ? 'Pausar' : 'Reactivar'} este plan?
                  </span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => setConfirmDeactivate(false)}>Cancelar</Button>
                    <Button size="sm" variant={plan!.activo ? 'destructive' : 'default'} onClick={handleToggle} disabled={isPending}>
                      {plan!.activo ? 'Pausar' : 'Reactivar'}
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <Button
                    variant="ghost" size="sm"
                    onClick={() => setConfirmDeactivate(true)}
                    className={plan!.activo ? 'text-muted-foreground hover:text-destructive' : 'text-success hover:text-success/80'}
                  >
                    {plan!.activo ? 'Pausar' : 'Reactivar'}
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
                  {isPending ? 'Guardando...' : 'Registrar plan'}
                </ShimmerButton>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
