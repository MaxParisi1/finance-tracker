'use client'

import { useState, useTransition, useEffect } from 'react'
import type { Gasto, ArchivoDrive } from '@/lib/types'
import { updateGastoAction, deleteGastoAction } from '@/app/gastos/actions'
import { MEDIO_PAGO_LABELS } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ShimmerButton } from '@/components/magicui/shimmer-button'
import { Trash2, Paperclip, ExternalLink, Plus } from 'lucide-react'
import { toast } from 'sonner'
import AdjuntarArchivoModal from '@/components/AdjuntarArchivoModal'

const MEDIO_PAGO_OPTIONS = Object.entries(MEDIO_PAGO_LABELS)

const labelClass = 'block text-xs font-medium text-muted-foreground mb-1.5'
const fieldClass = cn(
  'w-full h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'placeholder:text-muted-foreground',
  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors'
)

interface Props {
  gasto: Gasto
  categorias: string[]
  comercios: string[]
  onClose: () => void
}

export default function EditGastoModal({ gasto, categorias, comercios, onClose }: Props) {
  const [isPending, startTransition] = useTransition()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAdjuntar, setShowAdjuntar] = useState(false)
  const [archivos, setArchivos] = useState<ArchivoDrive[]>([])

  useEffect(() => {
    fetch(`/api/archivos?gastoId=${gasto.id}`)
      .then(r => r.json())
      .then(data => { if (Array.isArray(data)) setArchivos(data) })
      .catch(() => {})
  }, [gasto.id])

  function recargarArchivos() {
    fetch(`/api/archivos?gastoId=${gasto.id}`)
      .then(r => r.json())
      .then(data => { if (Array.isArray(data)) setArchivos(data) })
      .catch(() => {})
  }

  const [form, setForm] = useState({
    descripcion: gasto.descripcion ?? '',
    monto: gasto.monto_original,
    moneda: gasto.moneda,
    categoria: gasto.categoria ?? '',
    medio_pago: gasto.medio_pago ?? '',
    fecha: gasto.fecha,
    notas: gasto.notas ?? '',
    comercio: gasto.comercio ?? '',
  })

  function set(field: string, value: string | number) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  function handleSave() {
    setError(null)
    startTransition(async () => {
      try {
        await updateGastoAction(gasto.id, form)
        toast.success('Gasto actualizado')
        onClose()
      } catch (e: any) {
        const msg = e.message ?? 'Error al guardar'
        setError(msg)
        toast.error(msg)
      }
    })
  }

  function handleDelete() {
    setError(null)
    startTransition(async () => {
      try {
        await deleteGastoAction(gasto.id)
        toast.success('Gasto eliminado')
        onClose()
      } catch (e: any) {
        const msg = e.message ?? 'Error al eliminar'
        setError(msg)
        toast.error(msg)
      }
    })
  }

  return (
  <>
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-card text-card-foreground rounded-2xl sm:rounded-2xl rounded-t-3xl shadow-modal border border-border w-full max-w-md flex flex-col animate-slide-up sm:animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-base font-semibold">Editar gasto</h2>
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
            <input type="text" value={form.descripcion} onChange={e => set('descripcion', e.target.value)} className={fieldClass} />
          </div>

          <div>
            <label className={labelClass}>Comercio</label>
            <input
              type="text"
              list="comercios-list"
              value={form.comercio}
              onChange={e => set('comercio', e.target.value)}
              placeholder="Sin comercio"
              className={fieldClass}
            />
            <datalist id="comercios-list">
              {comercios.map(c => <option key={c} value={c} />)}
            </datalist>
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label className={labelClass}>Monto</label>
              <input
                type="number" step="0.01" value={form.monto}
                onChange={e => set('monto', parseFloat(e.target.value) || 0)}
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

          <div>
            <label className={labelClass}>Fecha</label>
            <input type="date" value={form.fecha} onChange={e => set('fecha', e.target.value)} className={fieldClass} />
          </div>

          <div>
            <label className={labelClass}>Notas</label>
            <textarea
              value={form.notas}
              onChange={e => set('notas', e.target.value)}
              rows={2}
              className={cn(fieldClass, 'h-auto py-2 resize-none')}
            />
          </div>

          {/* Comprobantes vinculados */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className={labelClass} style={{ marginBottom: 0 }}>
                Comprobantes ({archivos.length})
              </label>
              <button
                type="button"
                onClick={() => setShowAdjuntar(true)}
                className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 transition-colors font-medium"
              >
                <Plus className="w-3 h-3" />
                Adjuntar
              </button>
            </div>

            {archivos.length === 0 ? (
              <button
                type="button"
                onClick={() => setShowAdjuntar(true)}
                className={cn(
                  'w-full flex items-center justify-center gap-2 rounded-lg border border-dashed border-border',
                  'py-3 text-xs text-muted-foreground hover:border-primary/50 hover:text-primary transition-all duration-150',
                )}
              >
                <Paperclip className="w-3.5 h-3.5" />
                Adjuntar factura o comprobante
              </button>
            ) : (
              <div className="space-y-1.5">
                {archivos.map(a => (
                  <div
                    key={a.id}
                    className="flex items-center justify-between gap-2 rounded-lg bg-muted/60 px-3 py-2"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Paperclip className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-foreground truncate">{a.drive_file_name}</p>
                        <p className="text-[10px] text-muted-foreground">{a.tipo} · {a.fecha}</p>
                      </div>
                    </div>
                    {a.drive_web_view_link && (
                      <a
                        href={a.drive_web_view_link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted-foreground hover:text-primary transition-colors flex-shrink-0"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => setShowAdjuntar(true)}
                  className="w-full text-xs text-muted-foreground hover:text-primary transition-colors text-left px-1 pt-0.5"
                >
                  + Agregar otro comprobante
                </button>
              </div>
            )}
          </div>

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border gap-3">
          {confirmDelete ? (
            <>
              <span className="text-sm text-muted-foreground">¿Eliminar este gasto?</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setConfirmDelete(false)}>Cancelar</Button>
                <Button variant="destructive" size="sm" onClick={handleDelete} disabled={isPending}>
                  {isPending ? 'Eliminando...' : 'Sí, eliminar'}
                </Button>
              </div>
            </>
          ) : (
            <>
              <Button
                variant="ghost" size="sm"
                onClick={() => setConfirmDelete(true)}
                className="text-muted-foreground hover:text-destructive gap-1.5"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Eliminar
              </Button>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
                <ShimmerButton
                  onClick={handleSave}
                  disabled={isPending}
                  shimmerDuration="2s"
                  borderRadius="6px"
                  className="h-8 px-3 text-xs"
                >
                  {isPending ? 'Guardando...' : 'Guardar'}
                </ShimmerButton>
              </div>
            </>
          )}
        </div>
      </div>
    </div>

    {showAdjuntar && (
      <AdjuntarArchivoModal
        gastoId={gasto.id}
        comercio={form.comercio || gasto.comercio || ''}
        fecha={form.fecha}
        categoria={form.categoria}
        onClose={() => setShowAdjuntar(false)}
        onSuccess={recargarArchivos}
      />
    )}
  </>
  )
}
