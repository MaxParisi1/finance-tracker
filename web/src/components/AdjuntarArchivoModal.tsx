'use client'

import { useState, useTransition } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ShimmerButton } from '@/components/magicui/shimmer-button'
import SelectorArchivos, { type ArchivoPendiente } from '@/components/ui/SelectorArchivos'
import { subirYVincularArchivoAction } from '@/app/comprobantes/actions'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Modal, ModalTitle } from '@/components/ui/dialog'

interface Props {
  gastoId: string
  comercio?: string
  fecha?: string
  categoria?: string
  onClose: () => void
  onSuccess?: () => void
}

export default function AdjuntarArchivoModal({
  gastoId, comercio = '', fecha = '', categoria = '', onClose, onSuccess,
}: Props) {
  const [isPending, startTransition] = useTransition()
  const [archivos, setArchivos] = useState<ArchivoPendiente[]>([])
  const [fechaVal, setFechaVal] = useState(fecha)

  const restantes = archivos.filter(a => a.estado !== 'ok').length

  function handleSubmit() {
    const aSubir = archivos.filter(a => a.estado !== 'ok')
    if (aSubir.length === 0 || !fechaVal) {
      toast.error('Agregá al menos un archivo y completá la fecha')
      return
    }

    startTransition(async () => {
      let ok = 0
      const fallaron: string[] = []
      // Copia local: el estado de React no se ve actualizado dentro del loop.
      let lista = archivos

      const marcar = (id: string, cambios: Partial<ArchivoPendiente>) => {
        lista = lista.map(a => (a.id === id ? { ...a, ...cambios } : a))
        setArchivos(lista)
      }

      // Secuencial a propósito: da estado por archivo y no satura la API de Drive.
      for (const a of aSubir) {
        marcar(a.id, { estado: 'subiendo', error: undefined })
        try {
          const fd = new FormData()
          fd.append('file', a.file)
          fd.append('gastoId', gastoId)
          fd.append('comercio', comercio || 'Sin comercio')
          fd.append('fecha', fechaVal)
          fd.append('tipo', a.tipo)
          if (categoria) fd.append('categoria', categoria)
          if (a.nombre) fd.append('nombreArchivo', a.nombre)

          await subirYVincularArchivoAction(fd)
          marcar(a.id, { estado: 'ok' })
          ok++
        } catch (e: any) {
          marcar(a.id, { estado: 'error', error: e?.message ?? 'Error al subir' })
          fallaron.push(a.file.name)
        }
      }

      if (fallaron.length === 0) {
        toast.success(ok === 1 ? 'Archivo subido y vinculado' : `${ok} archivos subidos y vinculados`)
        setTimeout(() => { onSuccess?.(); onClose() }, 800)
      } else {
        // No se cierra: los que fallaron quedan a la vista para reintentar.
        toast.error(
          ok > 0
            ? `${ok} subidos, ${fallaron.length} fallaron. Revisá los marcados en rojo.`
            : 'No se pudo subir ningún archivo.',
        )
        onSuccess?.()
      }
    })
  }

  const fieldClass = cn(
    'w-full h-9 rounded-lg border border-input bg-background px-3 text-sm',
    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors',
  )

  return (
    <Modal onClose={onClose} className="max-w-lg max-h-[90vh]">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border flex-shrink-0">
        <ModalTitle>
          Adjuntar documentos
          {archivos.length > 0 && (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {archivos.length} {archivos.length === 1 ? 'archivo' : 'archivos'}
            </span>
          )}
        </ModalTitle>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-muted"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="px-6 py-4 space-y-4 overflow-y-auto">
        <SelectorArchivos
          archivos={archivos}
          onChange={setArchivos}
          fecha={fechaVal}
          comercio={comercio}
          disabled={isPending}
        />

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1.5">
            Fecha de los documentos
          </label>
          <input
            type="date"
            value={fechaVal}
            onChange={e => setFechaVal(e.target.value)}
            className={fieldClass}
            disabled={isPending}
          />
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-border flex-shrink-0">
        <Button variant="outline" size="sm" onClick={onClose} disabled={isPending}>
          Cerrar
        </Button>
        <ShimmerButton
          onClick={handleSubmit}
          disabled={isPending || restantes === 0 || !fechaVal}
          shimmerDuration="2s"
          borderRadius="6px"
          className="h-8 px-4 text-xs"
        >
          {isPending ? 'Subiendo...'
            : restantes <= 1 ? 'Subir y vincular'
            : `Subir ${restantes} y vincular`}
        </ShimmerButton>
      </div>
    </Modal>
  )
}
