'use client'

import { useState, useTransition } from 'react'
import type { PlanCuota } from '@/lib/types'
import { registrarPagoCuotaAction } from '@/app/cuotas/actions'
import { formatARS } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ShimmerButton } from '@/components/magicui/shimmer-button'
import { X, Info } from 'lucide-react'
import { toast } from 'sonner'

const labelClass = 'block text-xs font-medium text-muted-foreground mb-1.5'
const fieldClass = cn(
  'w-full h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors',
)

interface Props {
  plan: PlanCuota
  onClose: () => void
}

export default function RegistrarPagoCuotaModal({ plan, onClose }: Props) {
  const [isPending, startTransition] = useTransition()
  const [monto, setMonto] = useState('')
  const [fecha, setFecha] = useState(plan.proximo_vencimiento)
  const [notas, setNotas] = useState('')

  function handleSave() {
    if (!monto || !fecha) {
      toast.error('Ingresá el monto y la fecha')
      return
    }

    startTransition(async () => {
      try {
        await registrarPagoCuotaAction(plan.id, {
          monto: parseFloat(monto),
          moneda: plan.moneda,
          fecha,
          notas: notas.trim() || undefined,
          cuotaActual: plan.cuota_actual,
          cuotasTotal: plan.cuotas_total,
          descripcion: plan.descripcion,
          comercio: plan.comercio ?? undefined,
          categoria: plan.categoria ?? undefined,
          medio_pago: plan.medio_pago,
          diaDelMes: plan.dia_del_mes,
        })
        toast.success(`Cuota ${plan.cuota_actual}/${plan.cuotas_total} registrada`)
        onClose()
      } catch (e: any) {
        toast.error(e.message ?? 'Error al registrar')
      }
    })
  }

  const esUltimaCuota = plan.cuota_actual === plan.cuotas_total

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-card text-card-foreground rounded-2xl rounded-t-3xl sm:rounded-2xl shadow-modal border border-border w-full max-w-sm flex flex-col animate-slide-up sm:animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <h2 className="text-base font-semibold">Registrar cuota {plan.cuota_actual}/{plan.cuotas_total}</h2>
            <p className="text-xs text-muted-foreground mt-0.5">{plan.descripcion}</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-muted">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          {/* Info del plan */}
          <div className="flex items-start gap-2 rounded-lg bg-muted/60 px-3 py-2.5">
            <Info className="w-3.5 h-3.5 text-muted-foreground mt-0.5 flex-shrink-0" />
            <p className="text-xs text-muted-foreground leading-relaxed">
              El monto varía cada mes. Ingresá el valor exacto de esta cuota según tu resumen.
              {esUltimaCuota && <span className="text-success font-medium"> Esta es la última cuota.</span>}
            </p>
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label className={labelClass}>Monto *</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={monto}
                onChange={e => setMonto(e.target.value)}
                placeholder="0"
                className={fieldClass}
                autoFocus
              />
            </div>
            <div className="w-16">
              <label className={labelClass}>Moneda</label>
              <div className={cn(fieldClass, 'flex items-center text-muted-foreground cursor-default')}>
                {plan.moneda}
              </div>
            </div>
          </div>

          <div>
            <label className={labelClass}>Fecha de pago *</label>
            <input
              type="date"
              value={fecha}
              onChange={e => setFecha(e.target.value)}
              className={fieldClass}
            />
          </div>

          <div>
            <label className={labelClass}>Notas</label>
            <input
              type="text"
              value={notas}
              onChange={e => setNotas(e.target.value)}
              placeholder="Opcional..."
              className={fieldClass}
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-border">
          <Button variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
          <ShimmerButton onClick={handleSave} disabled={isPending} shimmerDuration="2s" borderRadius="6px" className="h-8 px-3 text-xs">
            {isPending ? 'Registrando...' : esUltimaCuota ? 'Registrar y cerrar plan' : `Registrar cuota ${plan.cuota_actual}`}
          </ShimmerButton>
        </div>
      </div>
    </div>
  )
}
