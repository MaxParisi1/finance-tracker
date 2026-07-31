'use client'

import { useState, useTransition } from 'react'
import type { GastoRecurrente } from '@/lib/types'
import type { RecurrenteConCosto, FijosDelMes, FijoDelMes } from '@/lib/queries'
import RecurrenteModal from './RecurrenteModal'
import RegistrarCobroModal from './RegistrarCobroModal'
import { formatARS, cn } from '@/lib/utils'
import { materializarRecurrentesAction } from '@/app/recurrentes/actions'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Plus, CheckCircle2, Paperclip, Pencil, ChevronLeft, ChevronRight } from 'lucide-react'
import Link from 'next/link'

const FRECUENCIA_LABEL: Record<string, string> = { mensual: 'Mensual', anual: 'Anual', semanal: 'Semanal' }

const fechaCorta = (f: string) => new Date(f + 'T00:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })

interface Props {
  recurrentes: RecurrenteConCosto[]
  total_mensual_ars: number
  total_anual_ars: number
  tc_blue: number | null
  tc_fecha: string | null
  tc_es_hoy: boolean
  categorias: string[]
  fijos: FijosDelMes
  mesLabel: string
  mes: number
  anio: number
  esMesActual: boolean
}

function vencInfo(dias: number): { label: string; tone: 'crit' | 'warn' | 'muted' } {
  if (dias < 0) return { label: `vencido hace ${Math.abs(dias)}d`, tone: 'crit' }
  if (dias === 0) return { label: 'vence hoy', tone: 'crit' }
  if (dias === 1) return { label: 'vence mañana', tone: 'warn' }
  if (dias <= 5) return { label: `en ${dias} días`, tone: 'warn' }
  return { label: `en ${dias} días`, tone: 'muted' }
}
const chipTone: Record<string, string> = {
  crit: 'bg-destructive/12 text-destructive',
  warn: 'bg-warning/15 text-warning',
  muted: 'bg-muted text-muted-foreground',
}
const stripeTone: Record<string, string> = {
  crit: 'bg-destructive', warn: 'bg-warning', muted: 'bg-border', paid: 'bg-success/70',
}

export default function RecurrentesView({
  recurrentes, total_mensual_ars, total_anual_ars,
  tc_blue, tc_fecha, tc_es_hoy, categorias, fijos, mesLabel, mes, anio, esMesActual,
}: Props) {
  const [editing, setEditing] = useState<GastoRecurrente | null>(null)
  const [registrando, setRegistrando] = useState<{ rec: RecurrenteConCosto; fechaDefault?: string; mesLabel?: string } | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [isPending, startTransition] = useTransition()
  const [materializeResult, setMaterializeResult] = useState<{ insertados: number; omitidos: number; errores: string[] } | null>(null)

  const recById = new Map(recurrentes.map(r => [r.id, r]))
  const enMes = new Set([...fijos.pendientes, ...fijos.pagados].map(f => f.id))
  const otros = recurrentes.filter(r => !enMes.has(r.id))
  const nextMesCorto = new Date(anio, mes, 1).toLocaleDateString('es-AR', { month: 'short' })
  // Adelanto: el pago apunta al 1° del mes siguiente (mapea inequívocamente a ese mes,
  // sin importar el día del fijo). Ver mesDelPagoMensual() en queries.ts.
  const nextMes = mes === 12 ? 1 : mes + 1
  const nextAnio = mes === 12 ? anio + 1 : anio
  const fechaAdelanto = `${nextAnio}-${String(nextMes).padStart(2, '0')}-01`
  const nextMesLabel = new Date(nextAnio, nextMes - 1, 1).toLocaleDateString('es-AR', { month: 'long' })
  const abrirCobro = (rec: RecurrenteConCosto, adelanto?: boolean) =>
    setRegistrando(adelanto ? { rec, fechaDefault: fechaAdelanto, mesLabel: nextMesLabel } : { rec })

  const prevMes = mes === 1 ? 12 : mes - 1
  const prevAnio = mes === 1 ? anio - 1 : anio
  const hrefMes = (m: number, a: number) => `/recurrentes?mes=${m}&anio=${a}`

  const porCategoria = new Map<string, number>()
  for (const r of recurrentes) porCategoria.set(r.categoria ?? 'Sin categoría', (porCategoria.get(r.categoria ?? 'Sin categoría') ?? 0) + r.mensual_ars)
  const categoriasSorted = Array.from(porCategoria.entries()).map(([cat, total]) => ({ cat, total })).sort((a, b) => b.total - a.total)

  function handleMaterialize() {
    setMaterializeResult(null)
    startTransition(async () => setMaterializeResult(await materializarRecurrentesAction()))
  }
  const pendingCount = recurrentes.filter(r => r.dias_para_vencimiento <= 0 && !r.no_materializar).length

  const proxTexto =
    fijos.proximo_dias == null ? null
    : fijos.proximo_dias < 0 ? 'tenés pagos vencidos'
    : fijos.proximo_dias === 0 ? 'el más próximo vence hoy'
    : fijos.proximo_dias === 1 ? 'el más próximo vence mañana'
    : `el más próximo vence en ${fijos.proximo_dias} días`

  return (
    <>
      {/* Selector de mes */}
      <div className="flex items-center gap-2 mb-4">
        <Link href={hrefMes(prevMes, prevAnio)} aria-label="Mes anterior"
          className="inline-flex items-center justify-center w-8 h-8 rounded-lg border border-border text-muted-foreground hover:border-primary hover:text-primary transition-colors">
          <ChevronLeft className="w-4 h-4" />
        </Link>
        <span className="text-sm font-semibold text-foreground capitalize min-w-[9rem] text-center">{mesLabel}</span>
        <Link href={hrefMes(mes === 12 ? 1 : mes + 1, mes === 12 ? anio + 1 : anio)} aria-label="Mes siguiente"
          className="inline-flex items-center justify-center w-8 h-8 rounded-lg border border-border text-muted-foreground hover:border-primary hover:text-primary transition-colors">
          <ChevronRight className="w-4 h-4" />
        </Link>
        {!esMesActual && (
          <Link href="/recurrentes" className="ml-1 text-xs font-medium text-primary hover:underline">Hoy</Link>
        )}
      </div>

      {/* Estado de pagos del mes */}
      <Card className="mb-5">
        <CardContent className="p-6">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Estado de {mesLabel}</p>
          <div className="flex items-center gap-6 mt-4 flex-wrap">
            <Ring pct={fijos.pct_pagado} pagados={fijos.count_pagados} total={fijos.count_total} />
            <div className="min-w-0">
              {fijos.pendientes.length > 0 ? (
                <>
                  <div className="font-display text-[2.6rem] leading-none tracking-tight text-foreground tabular">{formatARS(fijos.total_pendiente_ars)}</div>
                  <p className="text-sm text-muted-foreground mt-2 max-w-[38ch]">
                    te faltan pagar <b className="text-foreground font-semibold">{fijos.pendientes.length} fijo{fijos.pendientes.length > 1 ? 's' : ''}</b>
                    {proxTexto ? ` · ${proxTexto}` : ''}
                  </p>
                </>
              ) : (
                <>
                  <div className="font-display text-[2.6rem] leading-none tracking-tight text-success">Al día ✓</div>
                  <p className="text-sm text-muted-foreground mt-2 max-w-[38ch]">
                    {fijos.count_total > 0 ? `pagaste los ${fijos.count_total} fijos de ${mesLabel.toLowerCase()}` : 'no hay fijos que venzan este mes'}
                  </p>
                </>
              )}
            </div>
          </div>
          <div className="flex flex-wrap gap-x-10 gap-y-3 mt-6 pt-5 border-t border-border">
            <Stat k="Ya pagaste este mes" v={formatARS(fijos.total_pagado_ars)} />
            <Stat k="Compromiso mensual" v={formatARS(total_mensual_ars)} sub={`${recurrentes.length} activos`} />
            <Stat k="Compromiso anual" v={formatARS(total_anual_ars)} />
            {tc_blue && (
              <Stat k="Equiv. mensual USD" v={`US$ ${Math.round(total_mensual_ars / tc_blue).toLocaleString('es-AR')}`}
                sub={`TC $${tc_blue.toLocaleString('es-AR')}${tc_fecha ? (tc_es_hoy ? ' · hoy' : ` · ${tc_fecha}`) : ''}`} />
            )}
          </div>
        </CardContent>
      </Card>

      {/* Barra de acciones */}
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          {pendingCount > 0 && (
            <Button onClick={handleMaterialize} disabled={isPending}>
              {isPending ? 'Registrando...' : `Registrar vencidos (${pendingCount})`}
            </Button>
          )}
          {materializeResult && (
            <p className="text-sm text-muted-foreground flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-success" />
              {materializeResult.insertados} registrados
              {materializeResult.omitidos > 0 && `, ${materializeResult.omitidos} ya existían`}
            </p>
          )}
        </div>
        <Button variant="outline" onClick={() => setShowNew(true)}><Plus className="w-4 h-4 mr-1" /> Nuevo fijo</Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-5">
          {/* Falta pagar */}
          {fijos.pendientes.length > 0 && (
            <Card>
              <SectionHeader title="Falta pagar" count={fijos.pendientes.length} right={formatARS(fijos.total_pendiente_ars)} rightTone="crit" />
              <div className="divide-y divide-border/70">
                {fijos.pendientes.map(f => (
                  <FijoRow key={f.id} f={f} rec={recById.get(f.id)} variant="pendiente"
                    onEdit={setEditing} onPay={abrirCobro} nextMesCorto={nextMesCorto} />
                ))}
              </div>
            </Card>
          )}

          {/* Pagados */}
          {fijos.pagados.length > 0 && (
            <Card>
              <SectionHeader title={`Pagados en ${mesLabel.split(' ')[0]}`} count={fijos.pagados.length} right={formatARS(fijos.total_pagado_ars)} rightTone="good" />
              <div className="divide-y divide-border/70">
                {fijos.pagados.map(f => (
                  <FijoRow key={f.id} f={f} rec={recById.get(f.id)} variant="pagado"
                    onEdit={setEditing} onPay={abrirCobro} nextMesCorto={nextMesCorto} />
                ))}
              </div>
            </Card>
          )}

          {/* Otros fijos (no vencen este mes) */}
          {otros.length > 0 && (
            <Card>
              <SectionHeader title="Otros fijos" count={otros.length} subtitle="no vencen este mes" />
              <div className="divide-y divide-border/70">
                {otros.map(r => (
                  <FijoRow key={r.id} rec={r} variant="otro" onEdit={setEditing} onPay={abrirCobro} nextMesCorto={nextMesCorto} />
                ))}
              </div>
            </Card>
          )}

          {recurrentes.length === 0 && (
            <Card><CardContent className="py-12 text-center text-muted-foreground text-sm">No hay fijos activos. Creá el primero con “Nuevo fijo”.</CardContent></Card>
          )}
        </div>

        {/* Desglose por categoría */}
        <Card className="h-fit">
          <CardHeader><CardTitle className="text-base">Por categoría</CardTitle></CardHeader>
          <CardContent className="pt-0">
            {categoriasSorted.length === 0 ? (
              <p className="text-sm text-muted-foreground">Sin datos.</p>
            ) : (
              <div className="space-y-3.5">
                {categoriasSorted.map(({ cat, total }) => {
                  const pct = total_mensual_ars > 0 ? Math.round((total / total_mensual_ars) * 100) : 0
                  return (
                    <div key={cat}>
                      <div className="flex justify-between text-[13px] mb-1.5">
                        <span className="text-foreground/80">{cat}</span>
                        <span className="font-medium text-foreground tabular">{formatARS(total)} <span className="text-muted-foreground font-normal">{pct}%</span></span>
                      </div>
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden"><div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} /></div>
                    </div>
                  )
                })}
                <p className="text-xs text-muted-foreground mt-4 pt-3 border-t border-border">Los montos en USD se convierten al TC oficial más reciente.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {editing && <RecurrenteModal recurrente={editing} categorias={categorias} onClose={() => setEditing(null)} />}
      {showNew && <RecurrenteModal categorias={categorias} onClose={() => setShowNew(false)} />}
      {registrando && (
        <RegistrarCobroModal
          recurrente={registrando.rec}
          fechaDefault={registrando.fechaDefault}
          mesObjetivoLabel={registrando.mesLabel}
          onClose={() => setRegistrando(null)}
        />
      )}
    </>
  )
}

function SectionHeader({ title, count, subtitle, right, rightTone }: {
  title: string; count: number; subtitle?: string; right?: string; rightTone?: 'crit' | 'good'
}) {
  return (
    <div className="flex items-baseline justify-between px-5 pt-4 pb-2">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[13px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
        <span className="text-[11px] font-semibold text-muted-foreground/70 tabular">{count}</span>
        {subtitle && <span className="text-xs text-muted-foreground/70">· {subtitle}</span>}
      </div>
      {right && <span className={cn('text-sm font-semibold tabular', rightTone === 'crit' ? 'text-foreground' : 'text-success')}>{right}</span>}
    </div>
  )
}

function FijoRow({ f, rec, variant, onEdit, onPay, nextMesCorto }: {
  f?: FijoDelMes
  rec?: RecurrenteConCosto
  variant: 'pendiente' | 'pagado' | 'otro'
  onEdit: (r: GastoRecurrente) => void
  onPay: (r: RecurrenteConCosto, adelanto?: boolean) => void
  nextMesCorto: string
}) {
  if (!rec) return null
  const info = f ? vencInfo(f.dias_para_vencimiento) : vencInfo(rec.dias_para_vencimiento)
  const stripe = variant === 'pagado' ? 'paid' : variant === 'pendiente' ? info.tone : 'muted'
  const montoStr = (rec.ultimo_moneda ?? rec.moneda) === 'USD'
    ? `US$ ${(rec.ultimo_monto_original ?? rec.monto_original).toLocaleString('es-AR', { minimumFractionDigits: 2 })}`
    : formatARS((f?.monto_ars) ?? rec.ultimo_monto_original ?? rec.monto_original)

  return (
    <div className={cn('flex items-center gap-4 px-5 py-4', variant === 'pagado' && 'opacity-[0.82]')}>
      <span className={cn('w-1 self-stretch rounded-full flex-shrink-0', stripeTone[stripe])} />

      <button onClick={() => onEdit(rec)} className="min-w-0 flex-1 text-left group">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground truncate">{rec.descripcion}</span>
          {rec.no_materializar && <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-secondary text-secondary-foreground flex-shrink-0">auto</span>}
          <Pencil className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
        </div>
        <div className="text-xs text-muted-foreground mt-0.5 truncate">
          {rec.categoria ?? 'Sin categoría'} · {FRECUENCIA_LABEL[rec.frecuencia] ?? rec.frecuencia}
          {' · '}{rec.dia_del_mes != null ? `día ${rec.dia_del_mes}` : 'sin día fija'}
        </div>
      </button>

      {/* Estado */}
      <div className="hidden sm:flex justify-end w-[132px] flex-shrink-0">
        {variant === 'pagado' && f ? (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-full bg-success/12 text-success whitespace-nowrap">
            ✓ {f.fecha_pago ? fechaCorta(f.fecha_pago) : 'pagado'}{f.con_comprobante && <Paperclip className="w-2.5 h-2.5" />}
          </span>
        ) : variant === 'pendiente' ? (
          f?.sin_dia ? (
            <span className="text-[11px] font-semibold px-2.5 py-1 rounded-full whitespace-nowrap bg-muted text-muted-foreground">este mes</span>
          ) : (
            <span className={cn('text-[11px] font-semibold px-2.5 py-1 rounded-full whitespace-nowrap', chipTone[info.tone])}>{info.label}</span>
          )
        ) : (
          <span className="text-[11px] text-muted-foreground whitespace-nowrap">próx. {fechaCorta(rec.proximo_vencimiento)}</span>
        )}
      </div>

      {/* Monto */}
      <div className="w-28 text-right flex-shrink-0">
        <p className="text-sm font-semibold text-foreground tabular">{montoStr}</p>
        {(rec.frecuencia !== 'mensual' || (rec.ultimo_moneda ?? rec.moneda) === 'USD') && (
          <p className="text-[11px] text-muted-foreground tabular">≈ {formatARS(rec.mensual_ars)}/mes</p>
        )}
      </div>

      {/* Acción */}
      <div className="w-[104px] flex justify-end flex-shrink-0">
        {variant === 'pendiente' ? (
          <button onClick={() => onPay(rec)} className="text-xs font-semibold px-3.5 py-2 rounded-lg bg-primary text-primary-foreground hover:opacity-90 whitespace-nowrap">Pagar</button>
        ) : variant === 'pagado' ? (
          f?.siguiente_pagado ? (
            <span title={`${nextMesCorto} ya adelantado`} className="inline-flex items-center gap-1 text-xs font-semibold px-3 py-2 rounded-lg bg-success/12 text-success whitespace-nowrap">✓ {nextMesCorto}</span>
          ) : (
            <button onClick={() => onPay(rec, true)} title={`Adelantar ${nextMesCorto}`} className="text-xs font-medium px-3 py-2 rounded-lg border border-border text-muted-foreground hover:border-primary hover:text-primary whitespace-nowrap">Pagar {nextMesCorto}</button>
          )
        ) : (
          <button onClick={() => onPay(rec)} className="text-xs font-medium px-3 py-2 rounded-lg border border-border text-muted-foreground hover:border-primary hover:text-primary whitespace-nowrap">Pagar</button>
        )}
      </div>
    </div>
  )
}

function Ring({ pct, pagados, total }: { pct: number; pagados: number; total: number }) {
  return (
    <div className="relative w-[108px] h-[108px] flex-shrink-0 rounded-full grid place-items-center"
      style={{ background: `conic-gradient(hsl(var(--success)) ${pct * 3.6}deg, hsl(var(--muted)) 0)` }}>
      <div className="absolute inset-[11px] rounded-full bg-card" />
      <div className="relative text-center">
        <div className="text-[22px] font-bold text-foreground leading-none tabular">{pagados}/{total}</div>
        <div className="text-[10px] text-muted-foreground mt-1 tracking-wide uppercase">pagados</div>
      </div>
    </div>
  )
}

function Stat({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div>
      <div className="text-[11.5px] text-muted-foreground font-medium">{k}</div>
      <div className="text-base font-semibold text-foreground mt-0.5 tabular">{v}</div>
      {sub && <div className="text-[11px] text-muted-foreground mt-0.5">{sub}</div>}
    </div>
  )
}
