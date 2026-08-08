'use client'

import { useState, useTransition } from 'react'
import { X, Check } from 'lucide-react'
import SelectorArchivos, { type ArchivoPendiente } from '@/components/ui/SelectorArchivos'
import type { RecurrenteConCosto } from '@/lib/queries'
import { registrarCobroAction } from '@/app/recurrentes/actions'
import { Button } from '@/components/ui/button'
import { ShimmerButton } from '@/components/magicui/shimmer-button'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import MontoInput from '@/components/ui/MontoInput'

interface Props {
  recurrente: RecurrenteConCosto
  /** Fecha precargada. En un adelanto, el 1° del mes objetivo (así se atribuye a ese mes). */
  fechaDefault?: string
  /** Nombre del mes que se está saldando (ej. "agosto") — solo para adelantos. */
  mesObjetivoLabel?: string
  onClose: () => void
}

export default function RegistrarCobroModal({ recurrente: r, fechaDefault, mesObjetivoLabel, onClose }: Props) {
  const [isPending, startTransition] = useTransition()
  const [archivos, setArchivos] = useState<ArchivoPendiente[]>([])
  const [monto, setMonto] = useState(String(r.ultimo_monto_original ?? r.monto_original))
  const [fecha, setFecha] = useState(fechaDefault ?? new Date().toISOString().split('T')[0])
  const [done, setDone] = useState(false)

  function handleSubmit() {
    const montoNum = parseFloat(monto)
    if (!fecha || isNaN(montoNum) || montoNum <= 0) {
      toast.error('Completá el monto y la fecha')
      return
    }

    startTransition(async () => {
      try {
        const fd = new FormData()
        fd.append('recurrenteId', r.id)
        fd.append('monto', String(montoNum))
        fd.append('moneda', r.moneda)
        fd.append('fecha', fecha)
        fd.append('descripcion', r.descripcion)
        fd.append('categoria', r.categoria ?? '')
        fd.append('medio_pago', r.medio_pago)
        fd.append('frecuencia', r.frecuencia)
        fd.append('proximo_vencimiento', r.proximo_vencimiento)
        for (const a of archivos) {
          fd.append('files', a.file)
          fd.append('tipos', a.tipo)
        }

        const { fallidos } = await registrarCobroAction(fd)

        if (fallidos.length > 0) {
          // El gasto ya se creó: no se puede reintentar todo desde acá sin
          // duplicarlo. Se avisa para adjuntar lo que falta desde el gasto.
          toast.error(
            `Cobro registrado, pero ${fallidos.length} archivo(s) no se subieron. ` +
            `Adjuntalos desde el gasto.`,
          )
        } else {
          toast.success(
            archivos.length === 0 ? 'Cobro registrado'
              : `Cobro registrado con ${archivos.length} documento(s)`,
          )
        }
        setDone(true)
        setTimeout(onClose, 900)
      } catch (e: any) {
        toast.error(e.message ?? 'Error al registrar')
      }
    })
  }

  const labelClass = 'block text-xs font-medium text-muted-foreground mb-1.5'
  const fieldClass = cn(
    'w-full h-9 rounded-lg border border-input bg-background px-3 text-sm',
    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors',
  )

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-card text-card-foreground rounded-2xl rounded-t-3xl sm:rounded-2xl shadow-modal border border-border w-full max-w-md flex flex-col animate-slide-up sm:animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <h2 className="text-base font-semibold">
              Registrar cobro
              {mesObjetivoLabel && <span className="text-primary font-medium"> · {mesObjetivoLabel}</span>}
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">{r.descripcion}</p>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-muted"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          {/* Monto + Fecha */}
          <div className="flex gap-3">
            <div className="flex-1">
              <label className={labelClass}>
                Monto{r.moneda !== 'ARS' && <span className="text-primary ml-1">{r.moneda}</span>}
              </label>
              <MontoInput
                value={monto}
                onChange={n => setMonto(n === null ? '' : String(n))}
                className={fieldClass}
                autoFocus
              />
            </div>
            <div>
              <label className={labelClass}>Fecha</label>
              <input
                type="date"
                value={fecha}
                onChange={e => setFecha(e.target.value)}
                className={cn(fieldClass, 'w-40')}
              />
            </div>
          </div>

          {/* Documentos — opcional, varios y con tipo por archivo */}
          <div>
            <label className={labelClass}>
              Documentos <span className="text-muted-foreground/60 font-normal">(opcional)</span>
            </label>
            <SelectorArchivos
              archivos={archivos}
              onChange={setArchivos}
              fecha={fecha}
              comercio={r.descripcion}
              opcional
              disabled={isPending}
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-border">
          <Button variant="outline" size="sm" onClick={onClose} disabled={isPending}>
            Cancelar
          </Button>
          {done ? (
            <div className="flex items-center gap-1.5 text-sm font-medium text-success px-3 py-1.5">
              <Check className="w-4 h-4" />
              Registrado
            </div>
          ) : (
            <ShimmerButton
              onClick={handleSubmit}
              disabled={isPending || !fecha || !monto}
              shimmerDuration="2s"
              borderRadius="6px"
              className="h-8 px-4 text-xs"
            >
              {isPending
                ? 'Registrando...'
                : archivos.length > 0
                ? `Registrar con ${archivos.length} doc.`
                : 'Registrar cobro'}
            </ShimmerButton>
          )}
        </div>
      </div>
    </div>
  )
}
