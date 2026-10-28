'use client'

import { useEffect, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { createGastoAction, getOpcionesGastoAction } from '@/app/gastos/actions'
import { MEDIO_PAGO_LABELS, cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import MontoInput from '@/components/ui/MontoInput'
import { Modal, ModalTitle } from '@/components/ui/dialog'

/** Evento que disparan los botones "Registrar gasto" de la navegación. */
export const EVENTO_NUEVO_GASTO = 'nuevo-gasto'

const MEDIO_PAGO_OPTIONS = Object.entries(MEDIO_PAGO_LABELS)

const labelClass = 'block text-xs font-medium text-muted-foreground mb-1.5'
const fieldClass = cn(
  'w-full h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'placeholder:text-muted-foreground',
  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors'
)

const VACIO = {
  descripcion: '',
  comercio: '',
  monto: null as number | null,
  moneda: 'ARS',
  categoria: '',
  // Lo que llega por mail ya se registra solo: a mano se carga sobre todo efectivo.
  medio_pago: 'efectivo_ars',
  fecha: '',
  notas: '',
}

/**
 * Alta manual de un gasto. Vive montado una sola vez en el layout y se abre con
 * el evento EVENTO_NUEVO_GASTO, así el botón "+" funciona desde cualquier
 * pantalla sin que cada página tenga que pasarle categorías y comercios.
 */
export default function NuevoGastoModal() {
  const router = useRouter()
  const [abierto, setAbierto] = useState(false)
  const [isPending, startTransition] = useTransition()
  const [opciones, setOpciones] = useState<{ categorias: string[]; comercios: string[] } | null>(null)
  const [form, setForm] = useState(VACIO)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    function abrir() {
      setError(null)
      setForm(VACIO)
      setAbierto(true)
      getOpcionesGastoAction()
        .then(o => {
          setOpciones({ categorias: o.categorias, comercios: o.comercios })
          setForm(prev => ({ ...prev, fecha: prev.fecha || o.hoy }))
        })
        .catch(() => setError('No pude cargar las categorías. Cerrá y probá de nuevo.'))
    }
    window.addEventListener(EVENTO_NUEVO_GASTO, abrir)
    return () => window.removeEventListener(EVENTO_NUEVO_GASTO, abrir)
  }, [])

  if (!abierto) return null

  function set(field: keyof typeof VACIO, value: string | number | null) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  const falta =
    !form.descripcion.trim() ? 'Poné una descripción'
    : !form.monto || form.monto <= 0 ? 'Poné el monto'
    : !form.categoria ? 'Elegí una categoría'
    : !form.fecha ? 'Elegí la fecha'
    : null

  function handleSave() {
    if (falta) { setError(falta); return }
    setError(null)
    startTransition(async () => {
      try {
        await createGastoAction({ ...form, monto: form.monto as number })
        toast.success('Gasto registrado')
        setAbierto(false)
        router.refresh()
      } catch (e: any) {
        const msg = e.message ?? 'Error al guardar'
        setError(msg)
        toast.error(msg)
      }
    })
  }

  return (
    <Modal onClose={() => setAbierto(false)} className="max-w-md">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border">
        <ModalTitle>Registrar gasto</ModalTitle>
        <button
          onClick={() => setAbierto(false)}
          aria-label="Cerrar"
          className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-muted"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
          </svg>
        </button>
      </div>

      <div className="px-6 py-4 space-y-4 overflow-y-auto max-h-[60vh]">
        <div className="flex gap-3">
          <div className="flex-1">
            <label className={labelClass}>Monto</label>
            <MontoInput value={form.monto} onChange={n => set('monto', n)} className={fieldClass} autoFocus placeholder="0,00" />
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
          <label className={labelClass}>Descripción</label>
          <input type="text" value={form.descripcion} onChange={e => set('descripcion', e.target.value)} className={fieldClass} placeholder="Qué fue" />
        </div>

        <div>
          <label className={labelClass}>Comercio</label>
          <input
            type="text"
            list="nuevo-gasto-comercios"
            value={form.comercio}
            onChange={e => set('comercio', e.target.value)}
            placeholder="Opcional"
            className={fieldClass}
          />
          <datalist id="nuevo-gasto-comercios">
            {(opciones?.comercios ?? []).map(c => <option key={c} value={c} />)}
          </datalist>
        </div>

        <div>
          <label className={labelClass}>Categoría</label>
          <select value={form.categoria} onChange={e => set('categoria', e.target.value)} className={cn(fieldClass, 'cursor-pointer')} disabled={!opciones}>
            <option value="">{opciones ? 'Elegí una' : 'Cargando…'}</option>
            {(opciones?.categorias ?? []).map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <div className="flex gap-3">
          <div className="flex-1">
            <label className={labelClass}>Medio de pago</label>
            <select value={form.medio_pago} onChange={e => set('medio_pago', e.target.value)} className={cn(fieldClass, 'cursor-pointer')}>
              {MEDIO_PAGO_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className={labelClass}>Fecha</label>
            <input type="date" value={form.fecha} onChange={e => set('fecha', e.target.value)} className={fieldClass} />
          </div>
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

        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>

      <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-border">
        <Button variant="ghost" onClick={() => setAbierto(false)} disabled={isPending}>Cancelar</Button>
        <Button onClick={handleSave} disabled={isPending}>{isPending ? 'Guardando…' : 'Guardar'}</Button>
      </div>
    </Modal>
  )
}
