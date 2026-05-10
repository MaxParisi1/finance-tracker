'use client'

import { useRef, useState, useTransition } from 'react'
import { Upload, X, FileText, Check } from 'lucide-react'
import type { RecurrenteConCosto } from '@/lib/queries'
import { registrarCobroAction } from '@/app/recurrentes/actions'
import { Button } from '@/components/ui/button'
import { ShimmerButton } from '@/components/magicui/shimmer-button'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

const TIPOS_DOC = [
  { value: 'factura',     label: 'Factura' },
  { value: 'comprobante', label: 'Comprobante' },
  { value: 'ticket',      label: 'Ticket' },
  { value: 'recibo',      label: 'Recibo' },
]

const ACCEPT = 'application/pdf,image/jpeg,image/png,image/webp,image/heic'

interface Props {
  recurrente: RecurrenteConCosto
  onClose: () => void
}

export default function RegistrarCobroModal({ recurrente: r, onClose }: Props) {
  const [isPending, startTransition] = useTransition()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [tipo_doc, setTipoDoc] = useState('factura')
  const [monto, setMonto] = useState(String(r.ultimo_monto_original ?? r.monto_original))
  const [fecha, setFecha] = useState(new Date().toISOString().split('T')[0])
  const [dragOver, setDragOver] = useState(false)
  const [done, setDone] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function handleFile(f: File) {
    setFile(f)
    setPreview(f.type.startsWith('image/') ? URL.createObjectURL(f) : null)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

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
        if (file) {
          fd.append('file', file)
          fd.append('tipo_doc', tipo_doc)
        }

        await registrarCobroAction(fd)

        setDone(true)
        toast.success(`Cobro registrado${file ? ' con comprobante' : ''}`)
        setTimeout(onClose, 800)
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
            <h2 className="text-base font-semibold">Registrar cobro</h2>
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
              <input
                type="number"
                step="0.01"
                value={monto}
                onChange={e => setMonto(e.target.value)}
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

          {/* Drop zone — opcional */}
          <div>
            <label className={labelClass}>
              Comprobante <span className="text-muted-foreground/60 font-normal">(opcional)</span>
            </label>
            <div
              onClick={() => inputRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              className={cn(
                'relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-5 cursor-pointer transition-all duration-200',
                dragOver
                  ? 'border-primary bg-primary/5 scale-[1.01]'
                  : file
                  ? 'border-success/60 bg-success/5'
                  : 'border-border hover:border-primary/50 hover:bg-muted/50',
              )}
            >
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
              />

              {preview ? (
                <img src={preview} alt="preview" className="max-h-24 rounded-lg object-contain mb-2" />
              ) : file ? (
                <FileText className="w-8 h-8 text-success mb-1.5" />
              ) : (
                <Upload className="w-7 h-7 text-muted-foreground mb-1.5" />
              )}

              {file ? (
                <div className="text-center">
                  <p className="text-sm font-medium text-foreground truncate max-w-[240px]">{file.name}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {(file.size / 1024).toFixed(0)} KB · Click para cambiar
                  </p>
                </div>
              ) : (
                <div className="text-center">
                  <p className="text-sm font-medium text-foreground">Arrastrá o hacé click</p>
                  <p className="text-xs text-muted-foreground mt-0.5">PDF, JPG, PNG, WEBP</p>
                </div>
              )}
            </div>
          </div>

          {/* Tipo de doc — solo cuando hay archivo */}
          {file && (
            <div>
              <label className={labelClass}>Tipo de documento</label>
              <div className="grid grid-cols-4 gap-2">
                {TIPOS_DOC.map(t => (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => setTipoDoc(t.value)}
                    className={cn(
                      'py-2 px-1 rounded-lg text-xs font-medium border transition-all duration-150',
                      tipo_doc === t.value
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border text-muted-foreground hover:border-primary/40 hover:text-foreground',
                    )}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
          )}
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
                : file ? 'Registrar con comprobante' : 'Registrar cobro'}
            </ShimmerButton>
          )}
        </div>
      </div>
    </div>
  )
}
