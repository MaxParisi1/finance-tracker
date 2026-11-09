'use client'

import { useRef, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { subirResumenAction } from '@/app/resumenes/actions'

export default function SubirResumen() {
  const router = useRouter()
  const input = useRef<HTMLInputElement>(null)
  const [pending, startTransition] = useTransition()
  const [arrastrando, setArrastrando] = useState(false)

  function subir(file: File | undefined) {
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    startTransition(async () => {
      const r = await subirResumenAction(fd)
      if ('error' in r) {
        toast.error(r.error)
        return
      }
      router.push(`/resumenes/${r.id}`)
    })
  }

  return (
    <button
      type="button"
      disabled={pending}
      onClick={() => input.current?.click()}
      onDragOver={e => { e.preventDefault(); setArrastrando(true) }}
      onDragLeave={() => setArrastrando(false)}
      onDrop={e => { e.preventDefault(); setArrastrando(false); subir(e.dataTransfer.files[0]) }}
      className={
        'w-full rounded-xl border-2 border-dashed p-8 flex flex-col items-center gap-2 text-sm transition-colors ' +
        (arrastrando ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50')
      }
    >
      {pending ? (
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden />
      ) : (
        <Upload className="h-6 w-6 text-muted-foreground" aria-hidden />
      )}
      <span className="font-medium text-foreground">{pending ? 'Subiendo…' : 'Subir resumen (PDF)'}</span>
      <span className="text-muted-foreground">BBVA Visa o Mastercard. Arrastralo acá o hacé click.</span>
      <input
        ref={input}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={e => { subir(e.target.files?.[0]); e.target.value = '' }}
      />
    </button>
  )
}
