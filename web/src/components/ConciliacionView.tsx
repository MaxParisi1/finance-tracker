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

const CATEGORIA_IMPUESTOS = 'Impuestos y comisiones'
const A_REVISAR = new Set(['falta', 'impuesto', 'percepcion', 'bonificacion', 'descartado'])

function monto(valor: number, moneda: string): string {
  const n = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(valor)
  return moneda === 'USD' ? `US$ ${n}` : `$ ${n}`
}

/**
 * Una fila de "Para revisar". Los impuestos del resumen son UNA fila (se
 * cargan como un solo gasto); el resto es un movimiento por fila.
 */
interface Fila {
  clave: string
  ids: string[]
  titulo: string
  detalle: string
  nota?: string
  monto: number
  moneda: string
  tipo: 'consumo' | 'impuestos' | 'percepcion' | 'bonificacion'
  marcada: boolean
  categoria: string
  recurrente: string
}

function armarFilas(movimientos: MovimientoResumen[]): Fila[] {
  const revisar = movimientos.filter(m => A_REVISAR.has(m.estado))
  const esImpuesto = (m: MovimientoResumen) => m.seccion === 'impuesto' && !/^DB\.?RG\s*5617/i.test(m.descripcion)
  const filas: Fila[] = []

  for (const moneda of ['ARS', 'USD']) {
    const imp = revisar.filter(m => esImpuesto(m) && m.moneda === moneda)
    if (imp.length === 0) continue
    const descartados = imp.every(m => m.estado === 'descartado')
    filas.push({
      clave: `impuestos-${moneda}`,
      ids: imp.map(m => m.id),
      titulo: 'Impuestos y cargos del resumen',
      detalle: descartados ? 'Descartado' : `${imp.length} conceptos, se cargan como un solo gasto`,
      nota: imp.map(m => m.descripcion).join(' · '),
      monto: Math.round(imp.reduce((s, m) => s + m.monto, 0) * 100) / 100,
      moneda,
      tipo: 'impuestos',
      marcada: !descartados,
      categoria: CATEGORIA_IMPUESTOS,
      recurrente: '',
    })
  }

  for (const m of revisar) {
    if (esImpuesto(m)) continue
    const fecha = formatDate(m.fecha)
    const cuota = m.cuota_actual ? ` · cuota ${m.cuota_actual}/${m.cuotas_total}` : ''
    const base = {
      clave: m.id, ids: [m.id], titulo: m.descripcion, monto: m.monto, moneda: m.moneda,
      categoria: m.categoria_sugerida ?? '', recurrente: m.recurrente_id ?? '',
    }
    if (m.estado === 'percepcion') {
      filas.push({
        ...base, tipo: 'percepcion', marcada: false, detalle: `${fecha} · Percepción`,
        nota: 'Te la devuelven en el resumen siguiente si pagás los dólares en dólares.',
      })
    } else if (m.estado === 'bonificacion') {
      const consumo = movimientos.find(x => x.cupon === m.cupon && x.monto > 0 && x.seccion === 'consumo')
      const origen = m.gasto
      filas.push({
        ...base, tipo: 'bonificacion', marcada: true, categoria: '',
        detalle: `${fecha} · Bonificación`,
        nota: origen
          ? `Se resta de ${origen.comercio ?? 'su consumo'}: ${monto(origen.monto_original, m.moneda)} → ${monto(origen.monto_original + m.monto, m.moneda)}`
          : `Se resta de ${consumo?.descripcion ?? 'su consumo'} cuando lo cargues.`,
      })
    } else {
      filas.push({
        ...base, tipo: 'consumo',
        marcada: m.estado === 'falta' && m.monto > 0,
        detalle: `${fecha} · ${m.estado === 'descartado' ? 'Descartado' : m.monto < 0 ? 'Crédito' : 'No registrado'}${cuota}`,
      })
    }
  }
  return filas
}

export default function ConciliacionView({ resumen, movimientos, categorias, recurrentes }: Props) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()

  const filas = useMemo(() => armarFilas(movimientos), [movimientos])
  const enCarga = movimientos.filter(m => m.estado === 'a_cargar')
  const cargados = movimientos.filter(m => m.estado === 'cargado' || m.estado === 'aplicada')
  const registrados = movimientos.filter(m => m.estado === 'coincide' || m.estado === 'cuota_registrada')
  const pagos = movimientos.filter(m => m.estado === 'pago' || m.estado === 'reintegro')

  const [marcadas, setMarcadas] = useState<Set<string>>(() => new Set(filas.filter(f => f.marcada).map(f => f.clave)))
  const [categoria, setCategoria] = useState<Record<string, string>>(
    () => Object.fromEntries(filas.map(f => [f.clave, f.categoria])),
  )
  const [recurrente, setRecurrente] = useState<Record<string, string>>(
    () => Object.fromEntries(filas.map(f => [f.clave, f.recurrente])),
  )

  // El bot procesa el resumen y carga los gastos en segundo plano: mientras
  // haya algo en curso, se vuelve a pedir la página.
  const esperando = resumen.estado === 'pendiente' || enCarga.length > 0
  useEffect(() => {
    if (!esperando) return
    const t = setInterval(() => router.refresh(), 3000)
    return () => clearInterval(t)
  }, [esperando, router])

  const elegidas = filas.filter(f => marcadas.has(f.clave))
  const sinCategoria = elegidas.filter(f => f.tipo !== 'bonificacion' && !categoria[f.clave])

  function alternar(clave: string) {
    setMarcadas(prev => {
      const s = new Set(prev)
      if (s.has(clave)) s.delete(clave)
      else s.add(clave)
      return s
    })
  }

  function cargar() {
    startTransition(async () => {
      const items = elegidas.flatMap(f => f.ids.map(id => ({
        id,
        categoria: f.tipo === 'bonificacion' ? '' : categoria[f.clave],
        recurrente_id: recurrente[f.clave] || null,
      })))
      const r = await cargarMovimientosAction(resumen.id, items)
      if ('error' in r) toast.error(r.error)
      else {
        toast.success('Cargando… tarda unos segundos.')
        setMarcadas(new Set())
        router.refresh()
      }
    })
  }

  function descartar() {
    startTransition(async () => {
      const r = await descartarMovimientosAction(resumen.id, elegidas.flatMap(f => f.ids))
      if ('error' in r) toast.error(r.error)
      else {
        setMarcadas(new Set())
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
            {filas.length === 0 ? (
              <p className="rounded-xl border border-border p-4 text-sm text-muted-foreground flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-500" aria-hidden /> No falta nada.
              </p>
            ) : (
              <>
                <div className="rounded-xl border border-border divide-y divide-border">
                  {filas.map(f => (
                    <div key={f.clave} className="p-3 flex flex-col md:flex-row md:items-center gap-3">
                      <label className="flex items-start gap-3 flex-1 min-w-0 cursor-pointer">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 accent-primary"
                          checked={marcadas.has(f.clave)}
                          onChange={() => alternar(f.clave)}
                        />
                        <span className="min-w-0">
                          <span className="block font-medium text-foreground truncate" title={f.titulo}>{f.titulo}</span>
                          <span className="block text-xs text-muted-foreground">{f.detalle}</span>
                          {f.nota && (
                            <span className="block text-xs text-muted-foreground mt-0.5" title={f.nota}>{f.nota}</span>
                          )}
                        </span>
                      </label>
                      <span className="tabular-nums font-medium text-foreground md:w-32 md:text-right">
                        {monto(f.monto, f.moneda)}
                      </span>
                      {f.tipo !== 'bonificacion' && (
                        <select
                          aria-label="Categoría"
                          value={categoria[f.clave]}
                          onChange={ev => setCategoria(c => ({ ...c, [f.clave]: ev.target.value }))}
                          className="h-9 rounded-md border border-input bg-background px-2 text-sm md:w-44"
                        >
                          <option value="">Categoría…</option>
                          {categorias.map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                      )}
                      {f.tipo === 'consumo' && (
                        <select
                          aria-label="Gasto fijo"
                          value={recurrente[f.clave]}
                          onChange={ev => {
                            const id = ev.target.value
                            setRecurrente(r => ({ ...r, [f.clave]: id }))
                            const rec = recurrentes.find(x => x.id === id)
                            if (rec) setCategoria(c => ({ ...c, [f.clave]: rec.categoria }))
                          }}
                          className="h-9 rounded-md border border-input bg-background px-2 text-sm md:w-44"
                        >
                          <option value="">Sin gasto fijo</option>
                          {recurrentes.map(r => <option key={r.id} value={r.id}>{r.descripcion}</option>)}
                        </select>
                      )}
                    </div>
                  ))}
                </div>
                <div className="mt-3 flex items-center gap-2 flex-wrap">
                  <Button onClick={cargar} disabled={pending || elegidas.length === 0 || sinCategoria.length > 0}>
                    {pending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
                    Cargar {elegidas.length} seleccionado{elegidas.length === 1 ? '' : 's'}
                  </Button>
                  <Button variant="outline" onClick={descartar} disabled={pending || elegidas.length === 0}>
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
                      <span className="truncate" title={m.descripcion}>
                        {m.descripcion}
                        {m.estado === 'aplicada' && <span className="text-muted-foreground"> · restada de su consumo</span>}
                      </span>
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
