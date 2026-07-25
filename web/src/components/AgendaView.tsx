'use client'

import { useState } from 'react'
import type { Obligacion, RecurrenteConCosto } from '@/lib/queries'
import RegistrarCobroModal from './RegistrarCobroModal'
import { Card, CardContent } from '@/components/ui/card'
import { formatARS, cn, MONTH_NAMES_CAP } from '@/lib/utils'
import { Paperclip } from 'lucide-react'

const WEEKDAYS = ['L', 'M', 'M', 'J', 'V', 'S', 'D']
const pad2 = (n: number) => String(n).padStart(2, '0')
const short = (n: number) => (n >= 1000 ? `$${Math.round(n / 1000)}k` : `$${Math.round(n)}`)
const hoyStr = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Argentina/Buenos_Aires' })

function fechaLabel(f: string): string {
  const [y, m, d] = f.split('-').map(Number)
  const hoy = hoyStr()
  const [hy, hm, hd] = hoy.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  const diff = Math.round((dt.getTime() - new Date(hy, hm - 1, hd).getTime()) / 86400000)
  const dow = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'][dt.getDay()]
  if (diff === 0) return 'Hoy'
  if (diff === 1) return 'Mañana'
  const base = `${dow} ${d} ${MONTH_NAMES_CAP[m - 1].slice(0, 3).toLowerCase()}`
  return diff < 0 ? `${base} · vencido` : base
}

export default function AgendaView({
  obligaciones,
  recurrentes,
}: {
  obligaciones: Obligacion[]
  recurrentes: RecurrenteConCosto[]
}) {
  const [registrando, setRegistrando] = useState<RecurrenteConCosto | null>(null)
  const recById = new Map(recurrentes.map(r => [r.id, r]))
  const hoy = hoyStr()

  // Próximos 30 días (pendiente)
  const en30 = new Date(); en30.setDate(en30.getDate() + 30)
  const en30Str = en30.toLocaleDateString('sv-SE')
  const pendientes = obligaciones.filter(o => o.estado === 'pendiente')
  const prox30 = pendientes.filter(o => o.fecha >= hoy && o.fecha <= en30Str)
  const totalProx30 = prox30.reduce((s, o) => s + o.monto_ars, 0)

  // Día pico (suma pendiente por fecha)
  const porFecha = new Map<string, number>()
  for (const o of prox30) porFecha.set(o.fecha, (porFecha.get(o.fecha) ?? 0) + o.monto_ars)
  let pico: { fecha: string; total: number } | null = null
  for (const [fecha, total] of porFecha) if (!pico || total > pico.total) pico = { fecha, total }

  // Meses a mostrar: actual y siguiente
  const now = new Date()
  const meses = [
    { mes: now.getMonth() + 1, anio: now.getFullYear() },
    { mes: now.getMonth() === 11 ? 1 : now.getMonth() + 2, anio: now.getMonth() === 11 ? now.getFullYear() + 1 : now.getFullYear() },
  ]

  // Agenda: pendientes desde hoy, agrupadas por fecha
  const upcoming = pendientes.filter(o => o.fecha >= hoy).sort((a, b) => a.fecha.localeCompare(b.fecha))
  const grupos: { fecha: string; items: Obligacion[] }[] = []
  for (const o of upcoming) {
    const last = grupos[grupos.length - 1]
    if (last && last.fecha === o.fecha) last.items.push(o)
    else grupos.push({ fecha: o.fecha, items: [o] })
  }

  return (
    <>
      {/* Resumen */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <Card><CardContent className="py-4">
          <p className="text-xs font-medium text-muted-foreground">Próximos 30 días</p>
          <p className="font-display text-3xl text-foreground mt-1 tabular">{formatARS(totalProx30)}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{prox30.length} pago{prox30.length !== 1 ? 's' : ''} pendiente{prox30.length !== 1 ? 's' : ''}</p>
        </CardContent></Card>
        <Card><CardContent className="py-4">
          <p className="text-xs font-medium text-muted-foreground">Día con más carga</p>
          <p className="font-display text-3xl text-foreground mt-1 tabular">{pico ? formatARS(pico.total) : '—'}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{pico ? fechaLabel(pico.fecha) : 'sin vencimientos'}</p>
        </CardContent></Card>
        <Card><CardContent className="py-4">
          <p className="text-xs font-medium text-muted-foreground">Próximo vencimiento</p>
          <p className="font-display text-3xl text-foreground mt-1 tabular truncate">{grupos[0] ? short(grupos[0].items.reduce((s, o) => s + o.monto_ars, 0)) : '—'}</p>
          <p className="text-xs text-muted-foreground mt-0.5 truncate">{grupos[0] ? `${fechaLabel(grupos[0].fecha)} · ${grupos[0].items[0].titulo}` : 'todo al día'}</p>
        </CardContent></Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Calendarios */}
        <div className="lg:col-span-3 space-y-5">
          {meses.map(({ mes, anio }) => (
            <MesCalendario key={`${anio}-${mes}`} mes={mes} anio={anio} obligaciones={obligaciones} hoy={hoy} />
          ))}
          <div className="flex items-center gap-4 text-xs text-muted-foreground px-1">
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-primary" /> pendiente</span>
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-success/70" /> pagado</span>
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm ring-2 ring-primary ring-offset-1 ring-offset-background" /> hoy</span>
          </div>
        </div>

        {/* Agenda */}
        <div className="lg:col-span-2">
          <Card>
            <div className="px-5 py-4 border-b border-border">
              <h2 className="text-base font-semibold text-foreground">Agenda</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Lo que viene, por fecha</p>
            </div>
            {grupos.length === 0 ? (
              <CardContent className="py-12 text-center text-sm text-muted-foreground">Nada pendiente. Estás al día 🎉</CardContent>
            ) : (
              <div className="divide-y divide-border/70 max-h-[560px] overflow-y-auto">
                {grupos.map(g => {
                  const vencido = g.fecha < hoy
                  return (
                    <div key={g.fecha} className="px-5 py-3">
                      <div className="flex items-baseline justify-between mb-2">
                        <span className={cn('text-xs font-semibold uppercase tracking-wide', vencido ? 'text-destructive' : 'text-muted-foreground')}>{fechaLabel(g.fecha)}</span>
                        <span className="text-xs font-semibold text-foreground tabular">{formatARS(g.items.reduce((s, o) => s + o.monto_ars, 0))}</span>
                      </div>
                      <div className="space-y-2">
                        {g.items.map((o, i) => {
                          const rec = o.recurrente_id ? recById.get(o.recurrente_id) : undefined
                          return (
                            <div key={i} className="flex items-center gap-3">
                              <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', o.tipo === 'fijo' ? 'bg-primary' : 'bg-primary/40')} />
                              <div className="min-w-0 flex-1">
                                <p className="text-sm text-foreground truncate leading-tight">{o.titulo}</p>
                                <p className="text-[11px] text-muted-foreground">{o.subtitulo}</p>
                              </div>
                              <span className="text-sm font-medium text-foreground tabular whitespace-nowrap">
                                {o.moneda === 'USD' ? `US$ ${o.monto_original}` : formatARS(o.monto_ars)}
                              </span>
                              {rec ? (
                                <button onClick={() => setRegistrando(rec)} className="text-[11px] font-semibold px-2.5 py-1 rounded-md bg-primary text-primary-foreground hover:opacity-90 whitespace-nowrap">Pagar</button>
                              ) : (
                                <a href="/cuotas" className="text-[11px] font-medium px-2.5 py-1 rounded-md border border-border text-muted-foreground hover:text-primary hover:border-primary whitespace-nowrap">Ver</a>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </Card>
        </div>
      </div>

      {registrando && <RegistrarCobroModal recurrente={registrando} onClose={() => setRegistrando(null)} />}
    </>
  )
}

function MesCalendario({ mes, anio, obligaciones, hoy }: { mes: number; anio: number; obligaciones: Obligacion[]; hoy: string }) {
  const primero = new Date(anio, mes - 1, 1)
  const startCol = (primero.getDay() + 6) % 7 // lunes = 0
  const dias = new Date(anio, mes, 0).getDate()

  // Obligaciones por día
  const porDia = new Map<number, Obligacion[]>()
  for (const o of obligaciones) {
    const [y, m] = o.fecha.split('-').map(Number)
    if (y === anio && m === mes) {
      const d = Number(o.fecha.split('-')[2])
      porDia.set(d, [...(porDia.get(d) ?? []), o])
    }
  }

  const celdas: (number | null)[] = [...Array(startCol).fill(null), ...Array.from({ length: dias }, (_, i) => i + 1)]
  while (celdas.length % 7 !== 0) celdas.push(null)

  return (
    <Card>
      <div className="px-5 pt-4 pb-3">
        <h3 className="text-sm font-semibold text-foreground">{MONTH_NAMES_CAP[mes - 1]} <span className="text-muted-foreground font-normal">{anio}</span></h3>
      </div>
      <div className="px-3 pb-3">
        <div className="grid grid-cols-7 gap-1 mb-1">
          {WEEKDAYS.map((w, i) => <div key={i} className="text-center text-[10px] font-semibold text-muted-foreground/70 py-1">{w}</div>)}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {celdas.map((d, i) => {
            if (d === null) return <div key={i} />
            const fecha = `${anio}-${pad2(mes)}-${pad2(d)}`
            const items = porDia.get(d) ?? []
            const total = items.reduce((s, o) => s + o.monto_ars, 0)
            const hayPend = items.some(o => o.estado === 'pendiente')
            const esHoy = fecha === hoy
            const vencidoPend = hayPend && fecha < hoy
            return (
              <div
                key={i}
                title={items.map(o => `${o.titulo} · ${formatARS(o.monto_ars)}${o.estado === 'pagado' ? ' ✓' : ''}`).join('\n')}
                className={cn(
                  'min-h-[52px] rounded-lg border p-1.5 flex flex-col',
                  esHoy ? 'border-primary ring-1 ring-primary/40' : 'border-border/60',
                  items.length > 0 ? 'bg-muted/30' : '',
                )}
              >
                <span className={cn('text-[11px] tabular', esHoy ? 'font-bold text-primary' : 'text-muted-foreground')}>{d}</span>
                {items.length > 0 && (
                  <div className="mt-auto">
                    <div className={cn('h-1 rounded-full mb-0.5', vencidoPend ? 'bg-destructive' : hayPend ? 'bg-primary' : 'bg-success/70')} />
                    <span className={cn('text-[9px] font-semibold tabular leading-none', hayPend ? 'text-foreground' : 'text-muted-foreground')}>{short(total)}</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </Card>
  )
}
