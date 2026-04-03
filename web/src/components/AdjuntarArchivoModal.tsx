'use client'

import { useRef, useState, useTransition } from 'react'
import { Upload, X, FileText, Image, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ShimmerButton } from '@/components/magicui/shimmer-button'
import { subirYVincularArchivoAction } from '@/app/comprobantes/actions'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

const TIPOS = [
  { value: 'factura',     label: 'Factura' },
  { value: 'comprobante', label: 'Comprobante' },
  { value: 'ticket',      label: 'Ticket' },
  { value: 'recibo',      label: 'Recibo' },
]

const ACCEPT = 'application/pdf,image/jpeg,image/png,image/webp,image/heic'

interface Props {
  gastoId: string
  comercio?: string
  fecha?: string
  categoria?: string
  onClose: () => void
  onSuccess?: () => void
}

export default function AdjuntarArchivoModal({
  gastoId,
  comercio = '',
  fecha = '',
  categoria = '',
  onClose,
  onSuccess,
}: Props) {
  const [isPending, startTransition] = useTransition()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [tipo, setTipo] = useState('factura')
  const [comercioVal, setComercioVal] = useState(comercio)
  const [fechaVal, setFechaVal] = useState(fecha)
  const [dragOver, setDragOver] = useState(false)
  const [done, setDone] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function handleFile(f: File) {
    setFile(f)
    if (f.type.startsWith('image/')) {
      setPreview(URL.createObjectURL(f))
    } else {
      setPreview(null)
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  function handleSubmit() {
    if (!file || !fechaVal || !tipo) {
      toast.error('Seleccioná un archivo, fecha y tipo')
      return
    }

    startTransition(async () => {
      try {
        const fd = new FormData()
        fd.append('file', file)
        fd.append('gastoId', gastoId)
        fd.append('comercio', comercioVal || 'Sin comercio')
        fd.append('fecha', fechaVal)
        fd.append('tipo', tipo)
        if (categoria) fd.append('categoria', categoria)

        await subirYVincularArchivoAction(fd)

        setDone(true)
        toast.success(`${file.name} subido y vinculado`)
        setTimeout(() => {
          onSuccess?.()
          onClose()
        }, 800)
      } catch (e: any) {
        toast.error(e.message ?? 'Error al subir el archivo')
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
          <h2 className="text-base font-semibold">Adjuntar comprobante</h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-muted"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          {/* Drop zone */}
          <div
            onClick={() => inputRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={cn(
              'relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 cursor-pointer transition-all duration-200',
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
              <img src={preview} alt="preview" className="max-h-32 rounded-lg object-contain mb-2" />
            ) : file ? (
              <FileText className="w-10 h-10 text-success mb-2" />
            ) : (
              <Upload className="w-8 h-8 text-muted-foreground mb-2" />
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

          {/* Tipo */}
          <div>
            <label className={labelClass}>Tipo de documento</label>
            <div className="grid grid-cols-4 gap-2">
              {TIPOS.map(t => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setTipo(t.value)}
                  className={cn(
                    'py-2 px-1 rounded-lg text-xs font-medium border transition-all duration-150',
                    tipo === t.value
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground hover:border-primary/40 hover:text-foreground',
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Comercio */}
          <div>
            <label className={labelClass}>Comercio / Emisor</label>
            <input
              type="text"
              value={comercioVal}
              onChange={e => setComercioVal(e.target.value)}
              placeholder="Ej: Mercado Libre, ARBA..."
              className={fieldClass}
            />
          </div>

          {/* Fecha */}
          <div>
            <label className={labelClass}>Fecha del documento</label>
            <input
              type="date"
              value={fechaVal}
              onChange={e => setFechaVal(e.target.value)}
              className={fieldClass}
            />
          </div>

          {/* Nombre resultante */}
          {file && fechaVal && comercioVal && (
            <div className="rounded-lg bg-muted px-3 py-2.5">
              <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-0.5">
                Se guardará como
              </p>
              <p className="text-xs font-mono text-foreground break-all">
                {fechaVal}_{comercioVal.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '')}_{tipo}.
                {file.type === 'application/pdf' ? 'pdf'
                  : file.type === 'image/png' ? 'png'
                  : file.type === 'image/webp' ? 'webp'
                  : 'jpg'}
              </p>
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
              Subido
            </div>
          ) : (
            <ShimmerButton
              onClick={handleSubmit}
              disabled={isPending || !file || !fechaVal}
              shimmerDuration="2s"
              borderRadius="6px"
              className="h-8 px-4 text-xs"
            >
              {isPending ? 'Subiendo...' : 'Subir y vincular'}
            </ShimmerButton>
          )}
        </div>
      </div>
    </div>
  )
}
