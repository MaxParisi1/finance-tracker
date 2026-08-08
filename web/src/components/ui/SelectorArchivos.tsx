'use client'

import { useEffect, useMemo, useRef } from 'react'
import { AlertCircle, Check, FileText, Loader2, Upload, X } from 'lucide-react'
import { cn } from '@/lib/utils'

export const TIPOS_DOC = [
  { value: 'factura',     label: 'Factura' },
  { value: 'comprobante', label: 'Comprobante' },
  { value: 'ticket',      label: 'Ticket' },
  { value: 'recibo',      label: 'Recibo' },
]

const ACCEPT = 'application/pdf,image/jpeg,image/png,image/webp,image/heic'

export type EstadoArchivo = 'pendiente' | 'subiendo' | 'ok' | 'error'

export interface ArchivoPendiente {
  id: string
  file: File
  tipo: string
  preview: string | null
  nombre: string
  nombreEditado: boolean
  estado: EstadoArchivo
  error?: string
}

function extension(f: File): string {
  return f.type === 'application/pdf' ? 'pdf'
    : f.type === 'image/png' ? 'png'
    : f.type === 'image/webp' ? 'webp'
    : 'jpg'
}

function normalizar(texto: string): string {
  return texto.normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().trim().replace(/[\s.]+/g, '_').replace(/[^a-z0-9_\-]/g, '')
}

/**
 * Adivina el tipo por el nombre del archivo. Es solo el valor inicial y queda a
 * la vista para corregirlo: los nombres mienten (un PDF llamado "_factura"
 * puede ser un comprobante de pago), pero acierta la mayoría de las veces y
 * ahorra clicks cuando subís varios juntos.
 */
export function tipoSugerido(nombre: string): string {
  const n = nombre.toLowerCase()
  if (n.includes('comprobante') || n.includes('pago') || n.includes('transferencia')) return 'comprobante'
  if (n.includes('ticket')) return 'ticket'
  if (n.includes('recibo')) return 'recibo'
  return 'factura'
}

export function crearPendiente(file: File, i = 0): ArchivoPendiente {
  return {
    id: `${Date.now()}-${i}-${file.name}-${file.size}`,
    file,
    tipo: tipoSugerido(file.name),
    preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : null,
    nombre: '',
    nombreEditado: false,
    estado: 'pendiente',
  }
}

interface Props {
  archivos: ArchivoPendiente[]
  onChange: (archivos: ArchivoPendiente[]) => void
  /** Para armar el nombre de destino: `fecha_comercio_tipo.ext`. */
  fecha?: string
  comercio?: string
  /** Muestra y permite editar el nombre con que se guardará cada archivo. */
  mostrarNombres?: boolean
  opcional?: boolean
  disabled?: boolean
}

/**
 * Selector de varios archivos con tipo de documento por archivo.
 *
 * El estado vive en el padre (que es quien sube), así que este componente solo
 * edita la lista. Cada archivo lleva su propio estado de subida para poder
 * mostrar cuáles entraron y cuáles fallaron sin perder el resto.
 */
export default function SelectorArchivos({
  archivos, onChange, fecha, comercio, mostrarNombres = true, opcional = false, disabled = false,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)

  // Espejo para liberar las previews al desmontar: el cleanup de un efecto con
  // deps [] captura el estado inicial, no el actual.
  const vigentes = useRef<ArchivoPendiente[]>([])
  vigentes.current = archivos
  useEffect(() => () => {
    vigentes.current.forEach(a => a.preview && URL.revokeObjectURL(a.preview))
  }, [])

  const firma = useMemo(
    () => archivos.map(a => `${a.id}:${a.tipo}`).join('|'),
    [archivos],
  )

  // Nombres por defecto. Los repetidos se numeran: dos facturas del mismo
  // comercio y fecha generarían el mismo nombre y se pisarían en Drive.
  useEffect(() => {
    if (!mostrarNombres || !fecha || !comercio) return
    const usados = new Map<string, number>()
    let cambio = false
    const siguiente = archivos.map(a => {
      if (a.nombreEditado) return a
      const base = `${fecha}_${normalizar(comercio)}_${a.tipo}`
      const n = (usados.get(base) ?? 0) + 1
      usados.set(base, n)
      const nombre = `${base}${n > 1 ? `_${n}` : ''}.${extension(a.file)}`
      if (nombre === a.nombre) return a
      cambio = true
      return { ...a, nombre }
    })
    if (cambio) onChange(siguiente)
  }, [fecha, comercio, firma, mostrarNombres]) // eslint-disable-line react-hooks/exhaustive-deps

  function agregar(files: FileList | File[]) {
    onChange([...archivos, ...Array.from(files).map((f, i) => crearPendiente(f, i))])
  }

  function quitar(id: string) {
    // El revoke va fuera del updater: React puede invocar el updater dos veces.
    const a = archivos.find(x => x.id === id)
    if (a?.preview) URL.revokeObjectURL(a.preview)
    onChange(archivos.filter(x => x.id !== id))
  }

  function actualizar(id: string, cambios: Partial<ArchivoPendiente>) {
    onChange(archivos.map(a => (a.id === id ? { ...a, ...cambios } : a)))
  }

  return (
    <div className="space-y-3">
      <div
        onClick={() => !disabled && inputRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => {
          e.preventDefault()
          if (!disabled && e.dataTransfer.files.length) agregar(e.dataTransfer.files)
        }}
        className={cn(
          'flex flex-col items-center justify-center rounded-xl border-2 border-dashed transition-all duration-200',
          disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-primary/50 hover:bg-muted/50',
          archivos.length > 0 ? 'p-3' : 'p-6',
          'border-border',
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          disabled={disabled}
          onChange={e => { if (e.target.files?.length) agregar(e.target.files); e.target.value = '' }}
        />
        <Upload className={cn('text-muted-foreground', archivos.length > 0 ? 'w-5 h-5 mb-1' : 'w-7 h-7 mb-1.5')} />
        <p className="text-sm font-medium text-foreground">
          {archivos.length > 0 ? 'Agregar más archivos' : 'Arrastrá o hacé click'}
        </p>
        {archivos.length === 0 && (
          <p className="text-xs text-muted-foreground mt-0.5">
            PDF, JPG, PNG, WEBP · podés soltar varios juntos{opcional ? ' · opcional' : ''}
          </p>
        )}
      </div>

      {archivos.map(a => (
        <div
          key={a.id}
          className={cn(
            'rounded-xl border p-3 transition-colors',
            a.estado === 'ok' ? 'border-success/50 bg-success/5'
              : a.estado === 'error' ? 'border-destructive/50 bg-destructive/5'
              : 'border-border',
          )}
        >
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-muted flex items-center justify-center overflow-hidden">
              {a.estado === 'subiendo' ? <Loader2 className="w-4 h-4 animate-spin text-primary" />
                : a.estado === 'ok' ? <Check className="w-4 h-4 text-success" />
                : a.estado === 'error' ? <AlertCircle className="w-4 h-4 text-destructive" />
                : a.preview ? <img src={a.preview} alt="" className="w-full h-full object-cover" />
                : <FileText className="w-4 h-4 text-muted-foreground" />}
            </div>

            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{a.file.name}</p>
              <p className="text-xs text-muted-foreground">
                {(a.file.size / 1024).toFixed(0)} KB
                {a.error && <span className="text-destructive"> · {a.error}</span>}
              </p>
            </div>

            <select
              value={a.tipo}
              onChange={e => actualizar(a.id, { tipo: e.target.value, nombreEditado: false })}
              disabled={disabled || a.estado === 'ok' || a.estado === 'subiendo'}
              aria-label={`Tipo de ${a.file.name}`}
              className={cn(
                'h-8 rounded-lg border border-input bg-background px-2 text-xs cursor-pointer flex-shrink-0',
                'focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50',
              )}
            >
              {TIPOS_DOC.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>

            {a.estado !== 'subiendo' && !disabled && (
              <button
                type="button"
                onClick={() => quitar(a.id)}
                aria-label={`Quitar ${a.file.name}`}
                className="text-muted-foreground hover:text-destructive transition-colors p-1 flex-shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {mostrarNombres && a.nombre && a.estado !== 'ok' && (
            <div className="mt-2 flex items-center gap-2">
              <input
                type="text"
                value={a.nombre}
                onChange={e => actualizar(a.id, { nombre: e.target.value, nombreEditado: true })}
                className="flex-1 min-w-0 bg-muted rounded-md px-2 py-1 text-[11px] font-mono focus:outline-none focus:ring-1 focus:ring-ring"
                spellCheck={false}
                disabled={disabled}
              />
              {a.nombreEditado && (
                <button
                  type="button"
                  onClick={() => actualizar(a.id, { nombreEditado: false })}
                  className="text-[10px] text-primary hover:underline flex-shrink-0"
                >
                  Restaurar
                </button>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
