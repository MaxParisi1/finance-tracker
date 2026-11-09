'use client'

import { useEffect, useMemo, useState, useTransition } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { AlertTriangle, ArrowLeft, Check, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { formatDate } from '@/lib/utils'
import type { MovimientoResumen, ResumenTarjeta } from '@/lib/queries'
import {
  cargarMovimientosAction, descartarMovimientosAction, reprocesarResumenAction,
} from '@/app/resumenes/actions'

interface Props {
  resumen: ResumenTarjeta
  movimientos: MovimientoResumen[]
  categorias: string[]
  recurrentes: { id: string; descripcion: string; categoria: string }[]
}

/** Lo que el usuario tiene que decidir. */
const A_REVISAR = new Set(['falta', 'impuesto', 'percepcion', 'descartado'])

function monto(valor: number, moneda: string): string {
  const n = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(valor)
  return moneda === 'USD' ? `US$ ${n}` : `$ ${n}`
}

function etiqueta(m: MovimientoResumen): { texto: string; nota?: string } {
  if (m.estado === 'percepcion') {
    return {
      texto: 'Percepción',
      nota: 'Te la devuelven en el resumen siguiente si pagás los dólares en dólares.',
    }
  }
  if (m.estado === 'impuesto') return { texto: 'Impuesto o cargo' }
  if (m.estado === 'descartado') return { texto: 'Descartado' }
  if (m.monto < 0) return { texto: 'Bonificación' }
  return { texto: 'No registrado' }
}

/** Marcado por defecto: lo que es un gasto real que falta. */
function marcadoInicial(m: MovimientoResumen): boolean {
  if (m.estado === 'falta') return m.monto > 0
  return m.estado === 'impuesto'
}

export default function ConciliacionView({ resumen, movimientos, categorias, recurrentes }: Props) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()

  const revisar = movimientos.filter(m => A_REVISAR.has(m.estado))
  const enCarga = movimientos.filter(m => m.estado === 'a_cargar')
  const cargados = movimientos.filter(m => m.estado === 'cargado')
  const registrados = movimientos.filter(m => m.estado === 'coincide' || m.estado === 'cuota_registrada')
  const pagos = movimientos.filter(m => m.estado === 'pago' || m.estado === 'reintegro')

  const [marcados, setMarcados] = useState<Set<string>>(
    () => new Set(revisar.filter(marcadoInicial).map(m => m.id)),
  )
  const [categoria, setCategoria] = useState<Record<string, string>>(
    () => Object.fromEntries(revisar.map(m => [m.id, m.categoria_sugerida ?? ''])),
  )
  const [recurrente, setRecurrente] = useState<Record<string, string>>(
    () => Object.fromEntries(revisar.map(m => [m.id, m.recurrente_id ?? ''])),
  )

  // El bot procesa el resumen y carga los gastos en segundo plano: mientras
  // haya algo en curso, se vuelve a pedir la página.
  const esperando = resumen.estado === 'pendiente' || enCarga.length > 0
  useEffect(() => {
    if (!esperando) return
    const t = setInterval(() => router.refresh(), 3000)
    return () => clearInterval(t)
  }, [esperando, router])

  const elegidos = useMemo(() => revisar.filter(m => marcados.has(m.id)), [revisar, marcados])
  const sinCategoria = elegidos.filter(m => !categoria[m.id])

  function alternar(id: string) {
    setMarcados(prev => {
      const s = new Set(prev)
      if (s.has(id)) s.delete(id)
      else s.add(id)
      return s
    })
  }

  function cargar() {
    startTransition(async () => {
      const r = await cargarMovimientosAction(
        resumen.id,
        elegidos.map(m => ({ id: m.id, categoria: categoria[m.id], recurrente_id: recurrente[m.id] || null })),
      )
      if ('error' in r) toast.error(r.error)
      else {
        toast.success(`Cargando ${elegidos.length} gasto${elegidos.length === 1 ? '' : 's'}…`)
        setMarcados(new Set())
        router.refresh()
      }
    })
  }

  function descartar() {
    startTransition(async () => {
      const r = await descartarMovimientosAction(resumen.id, elegidos.map(m => m.id))
      if ('error' in r) toast.error(r.error)
      else {
        setMarcados(new Set())
        router.refresh()
      }
    })
  }

  function reintentar() {
    startTransition(async () => {
      const r = await reprocesarResumenAction(resumen.id)
      if ('error' in r) toast.error(r.error)
      else router.refresh()
    })
  }

  const tarjeta = resumen.tarjeta ? `${resumen.tarjeta.nombre ?? resumen.tarjeta.red} ${resumen.tarjeta.sufijo}` : 'Resumen'

  return (
    <div>
      <Link href="/resumenes" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4">
        <ArrowLeft className="h-4 w-4" aria-hidden /> Resúmenes
      </Link>

      <div className="mb-6 flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">{tarjeta}</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {resumen.cierre
              ? `Cierre ${formatDate(resumen.cierre)} · vence ${formatDate(resumen.vencimiento!)}`
              : resumen.nombre_archivo}
          </p>
        </div>
        {resumen.saldo_actual && (
          <div className="text-right">
            <p className="text-xs text-muted-foreground">Saldo actual</p>
            <p className="font-semibold tabular-nums text-foreground">
              {monto(Number(resumen.saldo_actual.ARS ?? 0), 'ARS')}
              {Number(resumen.saldo_actual.USD ?? 0) !== 0 && ` · ${monto(Number(resumen.saldo_actual.USD), 'USD')}`}
            </p>
          </div>
        )}
      </div>

      {resumen.estado === 'pendiente' && (
        <div className="rounded-xl border border-border p-6 flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
          El bot está leyendo el resumen. Tarda unos segundos.
        </div>
      )}

      {resumen.estado === 'error' && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-6 text-sm">
          <p className="flex items-center gap-2 font-medium text-red-600 dark:text-red-400">
            <AlertTriangle className="h-4 w-4" aria-hidden /> No se cargó nada
          </p>
          <p className="mt-2 text-foreground">{resumen.error}</p>
          <p className="mt-2 text-muted-foreground">
            El resumen solo se acepta si lo leído cierra al centavo con sus propios totales.
          </p>
          <Button variant="outline" size="sm" className="mt-4" onClick={reintentar} disabled={pending}>
            Reintentar
          </Button>
        </div>
      )}

      {resumen.estado === 'procesado' && (
        <div className="space-y-8">
          <section>
            <h2 className="text-lg font-semibold text-foreground">Para revisar</h2>
            <p className="text-sm text-muted-foreground mb-3">
              Está en el resumen y no en tus gastos. Elegí qué cargar.
            </p>
            {revisar.length === 0 ? (
              <p className="rounded-xl border border-border p-4 text-sm text-muted-foreground flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-500" aria-hidden /> No falta nada.
              </p>
            ) : (
              <>
                <div className="rounded-xl border border-border divide-y divide-border">
                  {revisar.map(m => {
                    const e = etiqueta(m)
                    return (
                      <div key={m.id} className="p-3 flex flex-col md:flex-row md:items-center gap-3">
                        <label className="flex items-start gap-3 flex-1 min-w-0 cursor-pointer">
                          <input
                            type="checkbox"
                            className="mt-1 h-4 w-4 accent-primary"
                            checked={marcados.has(m.id)}
                            onChange={() => alternar(m.id)}
                          />
                          <span className="min-w-0">
                            <span className="block font-medium text-foreground truncate" title={m.descripcion}>
                              {m.descripcion}
                            </span>
                            <span className="block text-xs text-muted-foreground">
                              {formatDate(m.fecha)} · {e.texto}
                              {m.cuota_actual && ` · cuota ${m.cuota_actual}/${m.cuotas_total}`}
                            </span>
                            {e.nota && <span className="block text-xs text-muted-foreground mt-0.5">{e.nota}</span>}
                          </span>
                        </label>
                        <span className="tabular-nums font-medium text-foreground md:w-32 md:text-right">
                          {monto(m.monto, m.moneda)}
                        </span>
                        <select
                          aria-label="Categoría"
                          value={categoria[m.id]}
                          onChange={ev => setCategoria(c => ({ ...c, [m.id]: ev.target.value }))}
                          className="h-9 rounded-md border border-input bg-background px-2 text-sm md:w-44"
                        >
                          <option value="">Categoría…</option>
                          {categorias.map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                        {m.seccion === 'consumo' && (
                          <select
                            aria-label="Gasto fijo"
                            value={recurrente[m.id]}
                            onChange={ev => {
                              const id = ev.target.value
                              setRecurrente(r => ({ ...r, [m.id]: id }))
                              const rec = recurrentes.find(x => x.id === id)
                              if (rec && !categoria[m.id]) setCategoria(c => ({ ...c, [m.id]: rec.categoria }))
                            }}
                            className="h-9 rounded-md border border-input bg-background px-2 text-sm md:w-44"
                          >
                            <option value="">Sin gasto fijo</option>
                            {recurrentes.map(r => <option key={r.id} value={r.id}>{r.descripcion}</option>)}
                          </select>
                        )}
                      </div>
                    )
                  })}
                </div>
                <div className="mt-3 flex items-center gap-2 flex-wrap">
                  <Button onClick={cargar} disabled={pending || elegidos.length === 0 || sinCategoria.length > 0}>
                    {pending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
                    Cargar {elegidos.length} seleccionado{elegidos.length === 1 ? '' : 's'}
                  </Button>
                  <Button variant="outline" onClick={descartar} disabled={pending || elegidos.length === 0}>
                    Descartar
                  </Button>
                  {sinCategoria.length > 0 && (
                    <span className="text-sm text-amber-600 dark:text-amber-400">
                      {sinCategoria.length} sin categoría
                    </span>
                  )}
                </div>
              </>
            )}
          </section>

          {(enCarga.length > 0 || cargados.length > 0) && (
            <section>
              <h2 className="text-lg font-semibold text-foreground mb-3">Cargados desde este resumen</h2>
              <div className="rounded-xl border border-border divide-y divide-border">
                {[...enCarga, ...cargados].map(m => (
                  <div key={m.id} className="p-3 flex items-center justify-between gap-3 text-sm">
                    <span className="flex items-center gap-2 min-w-0">
                      {m.estado === 'a_cargar'
                        ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground shrink-0" aria-label="Cargando" />
                        : <Check className="h-4 w-4 text-emerald-500 shrink-0" aria-label="Cargado" />}
                      <span className="truncate">{m.descripcion}</span>
                    </span>
                    <span className="tabular-nums">{monto(m.monto, m.moneda)}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {resumen.sin_movimiento.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold text-foreground">Registrados que no aparecen en el resumen</h2>
              <p className="text-sm text-muted-foreground mb-3">
                Puede ser un reverso, o un consumo de los últimos días que entra en el resumen siguiente.
              </p>
              <div className="rounded-xl border border-border divide-y divide-border">
                {resumen.sin_movimiento.map(g => (
                  <div key={g.id} className="p-3 flex items-center justify-between gap-3 text-sm">
                    <span className="truncate">{formatDate(g.fecha)} · {g.comercio}</span>
                    <span className="tabular-nums">{monto(Number(g.monto ?? 0), g.moneda ?? 'ARS')}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          <details className="rounded-xl border border-border">
            <summary className="p-4 cursor-pointer text-sm font-medium text-foreground">
              Ya registrados ({registrados.length})
            </summary>
            <div className="divide-y divide-border border-t border-border">
              {registrados.map(m => (
                <div key={m.id} className="p-3 flex items-center justify-between gap-3 text-sm">
                  <span className="truncate">
                    {formatDate(m.fecha)} · {m.descripcion}
                    {m.estado === 'cuota_registrada' && (
                      <span className="text-muted-foreground"> · cuota de una compra registrada por el total</span>
                    )}
                  </span>
                  <span className="tabular-nums">{monto(m.monto, m.moneda)}</span>
                </div>
              ))}
            </div>
          </details>

          {pagos.length > 0 && (
            <details className="rounded-xl border border-border">
              <summary className="p-4 cursor-pointer text-sm font-medium text-foreground">
                Pagos y reintegros ({pagos.length})
              </summary>
              <div className="divide-y divide-border border-t border-border">
                {pagos.map(m => (
                  <div key={m.id} className="p-3 flex items-center justify-between gap-3 text-sm">
                    <span className="truncate">{formatDate(m.fecha)} · {m.descripcion}</span>
                    <span className="tabular-nums">{monto(m.monto, m.moneda)}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  )
}
