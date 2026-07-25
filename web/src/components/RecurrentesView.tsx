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
import { Plus, CheckCircle2, Paperclip, Pencil } from 'lucide-react'

const FRECUENCIA_LABEL: Record<string, string> = {
  mensual: 'Mensual', anual: 'Anual', semanal: 'Semanal',
}

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
}

const fechaCorta = (f: string) => new Date(f + 'T00:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })
const mesCorto = (f: string) => new Date(f + 'T00:00:00').toLocaleDateString('es-AR', { month: 'short' })

function vencInfo(dias: number): { label: string; tone: 'crit' | 'warn' | 'muted' } {
  if (dias < 0) return { label: `vencido hace ${Math.abs(dias)}d`, tone: 'crit' }
  if (dias === 0) return { label: '¡vence hoy!', tone: 'crit' }
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
  crit: 'bg-destructive', warn: 'bg-warning', muted: 'bg-muted-foreground/30', paid: 'bg-success',
}

export default function RecurrentesView({
  recurrentes, total_mensual_ars, total_anual_ars,
  tc_blue, tc_fecha, tc_es_hoy, categorias, fijos, mesLabel,
}: Props) {
  const [editing, setEditing] = useState<GastoRecurrente | null>(null)
  const [registrando, setRegistrando] = useState<RecurrenteConCosto | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [isPending, startTransition] = useTransition()
  const [materializeResult, setMaterializeResult] = useState<{ insertados: number; omitidos: number; errores: string[] } | null>(null)

  // Estado de pago del mes por recurrente
  const estado = new Map<string, FijoDelMes>()
  for (const f of [...fijos.pendientes, ...fijos.pagados]) estado.set(f.id, f)

  // Orden: pendientes por urgencia → no vencen este mes → pagados
  const rank = (r: RecurrenteConCosto): number => {
    const f = estado.get(r.id)
    if (f?.pagado) return 2
    if (f) return 0 // pendiente que vence este mes
    return 1        // no vence este mes
  }
  const ordenados = [...recurrentes].sort((a, b) => {
    const ra = rank(a), rb = rank(b)
    if (ra !== rb) return ra - rb
    return a.dias_para_vencimiento - b.dias_para_vencimiento
  })

  const porCategoria = new Map<string, number>()
  for (const r of recurrentes) {
    const cat = r.categoria ?? 'Sin categoría'
    porCategoria.set(cat, (porCategoria.get(cat) ?? 0) + r.mensual_ars)
  }
  const categoriasSorted = Array.from(porCategoria.entries())
    .map(([cat, total]) => ({ cat, total }))
    .sort((a, b) => b.total - a.total)

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
      {/* Estado de pagos del mes */}
      <Card className="mb-5">
        <CardContent className="p-6">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Estado de {mesLabel}</p>
          <div className="flex items-center gap-6 mt-4 flex-wrap">
            <Ring pct={fijos.pct_pagado} pagados={fijos.count_pagados} total={fijos.count_total} />
            <div className="min-w-0">
              {fijos.pendientes.length > 0 ? (
                <>
                  <div className="font-display text-[2.4rem] leading-none tracking-tight text-foreground tabular">
                    {formatARS(fijos.total_pendiente_ars)}
                  </div>
                  <p className="text-sm text-muted-foreground mt-2 max-w-[36ch]">
                    te faltan pagar <b className="text-foreground font-semibold">{fijos.pendientes.length} fijo{fijos.pendientes.length > 1 ? 's' : ''}</b>
                    {proxTexto ? ` · ${proxTexto}` : ''}
                  </p>
                </>
              ) : (
                <>
                  <div className="font-display text-[2.4rem] leading-none tracking-tight text-success">Al día ✓</div>
                  <p className="text-sm text-muted-foreground mt-2 max-w-[36ch]">
                    {fijos.count_total > 0 ? `pagaste los ${fijos.count_total} fijos de este mes` : 'no hay fijos que venzan este mes'}
                  </p>
                </>
              )}
            </div>
          </div>
          <div className="flex flex-wrap gap-x-8 gap-y-3 mt-6 pt-5 border-t border-border">
            <Stat k="Ya pagaste este mes" v={formatARS(fijos.total_pagado_ars)} />
            <Stat k="Compromiso mensual" v={formatARS(total_mensual_ars)} sub={`${recurrentes.length} activos`} />
            <Stat k="Compromiso anual" v={formatARS(total_anual_ars)} />
            {tc_blue && (
              <Stat
                k="Equiv. mensual USD"
                v={`US$ ${Math.round(total_mensual_ars / tc_blue).toLocaleString('es-AR')}`}
                sub={`TC $${tc_blue.toLocaleString('es-AR')}${tc_fecha ? (tc_es_hoy ? ' · hoy' : ` · ${tc_fecha}`) : ''}`}
              />
            )}
          </div>
        </CardContent>
      </Card>

      {/* Barra de acciones */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
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
              {materializeResult.errores.length > 0 && <span className="text-destructive ml-1">· {materializeResult.errores.length} errores</span>}
            </p>
          )}
        </div>
        <Button variant="outline" onClick={() => setShowNew(true)}>
          <Plus className="w-4 h-4 mr-1" /> Nuevo fijo
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Lista de fijos con estado de pago */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2"><CardTitle className="text-base">Tus fijos</CardTitle></CardHeader>
          {ordenados.length === 0 ? (
            <CardContent className="py-12 text-center text-muted-foreground text-sm">No hay fijos activos.</CardContent>
          ) : (
            <div className="divide-y divide-border/70">
              {ordenados.map(r => {
                const f = estado.get(r.id)
                const pagado = !!f?.pagado
                const pendienteDue = !!f && !f.pagado
                const info = vencInfo(r.dias_para_vencimiento)
                const stripe = pagado ? 'paid' : pendienteDue ? info.tone : 'muted'
                const monto = (r.ultimo_moneda ?? r.moneda) === 'USD'
                  ? `US$ ${(r.ultimo_monto_original ?? r.monto_original).toLocaleString('es-AR', { minimumFractionDigits: 2 })}`
                  : formatARS(r.ultimo_monto_original ?? r.monto_original)
                return (
                  <div key={r.id} className={cn('flex items-center gap-3 px-4 py-3.5', pagado && 'opacity-75')}>
                    <span className={cn('w-[3px] self-stretch rounded-full', stripeTone[stripe])} />
                    <button onClick={() => setEditing(r)} className="flex-1 min-w-0 text-left group">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium text-foreground truncate">{r.descripcion}</p>
                        <Pencil className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                        {r.no_materializar && (
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-secondary text-secondary-foreground">auto · email</span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5 text-xs text-muted-foreground">
                        <span>{r.categoria ?? 'Sin categoría'}</span><span className="opacity-40">·</span>
                        <span>{FRECUENCIA_LABEL[r.frecuencia] ?? r.frecuencia}</span><span className="opacity-40">·</span>
                        <span>Día {r.dia_del_mes}</span>
                        {pagado && f?.fecha_pago && (
                          <><span className="opacity-40">·</span><span className="text-success">pagado {fechaCorta(f.fecha_pago)}</span></>
                        )}
                      </div>
                    </button>

                    {/* Estado / chip */}
                    {pagado ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-success/12 text-success whitespace-nowrap">
                        ✓ pagado{f?.con_comprobante && <Paperclip className="w-2.5 h-2.5" />}
                      </span>
                    ) : pendienteDue ? (
                      <span className={cn('text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap', chipTone[info.tone])}>{info.label}</span>
                    ) : (
                      <span className="text-[11px] text-muted-foreground whitespace-nowrap">día {r.dia_del_mes}</span>
                    )}

                    <div className="text-right w-24 flex-shrink-0">
                      <p className="text-sm font-semibold text-foreground tabular">{monto}</p>
                      {(r.frecuencia !== 'mensual' || ((r.ultimo_moneda ?? r.moneda) === 'USD' && tc_blue)) && (
                        <p className="text-[11px] text-muted-foreground tabular">≈ {formatARS(r.mensual_ars)}/mes</p>
                      )}
                    </div>

                    {/* Acción de pago. Si ya está pagado el mes, el botón registra
                        la PRÓXIMA ocurrencia (adelantar). Disponible también en auto·email. */}
                    {!pagado ? (
                      <button
                        onClick={() => setRegistrando(r)}
                        className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:opacity-90 whitespace-nowrap flex-shrink-0"
                      >
                        Pagar
                      </button>
                    ) : (
                      <button
                        onClick={() => setRegistrando(r)}
                        title={`Adelantar el pago de ${mesCorto(r.proximo_vencimiento)}`}
                        className="text-xs font-medium px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:border-primary hover:text-primary whitespace-nowrap flex-shrink-0"
                      >
                        Pagar {mesCorto(r.proximo_vencimiento)}
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        {/* Desglose por categoría */}
        <Card className="h-fit">
          <CardHeader><CardTitle className="text-base">Por categoría</CardTitle></CardHeader>
          <CardContent className="pt-0">
            {categoriasSorted.length === 0 ? (
              <p className="text-sm text-muted-foreground">Sin datos.</p>
            ) : (
              <div className="space-y-3">
                {categoriasSorted.map(({ cat, total }) => {
                  const pct = total_mensual_ars > 0 ? Math.round((total / total_mensual_ars) * 100) : 0
                  return (
                    <div key={cat}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-foreground/80">{cat}</span>
                        <span className="font-medium text-foreground tabular">{formatARS(total)}</span>
                      </div>
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  )
                })}
                <p className="text-xs text-muted-foreground mt-4 pt-3 border-t border-border">
                  Los montos en USD se convierten al TC oficial más reciente.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {editing && <RecurrenteModal recurrente={editing} categorias={categorias} onClose={() => setEditing(null)} />}
      {showNew && <RecurrenteModal categorias={categorias} onClose={() => setShowNew(false)} />}
      {registrando && <RegistrarCobroModal recurrente={registrando} onClose={() => setRegistrando(null)} />}
    </>
  )
}

function Ring({ pct, pagados, total }: { pct: number; pagados: number; total: number }) {
  return (
    <div
      className="relative w-[104px] h-[104px] flex-shrink-0 rounded-full grid place-items-center"
      style={{ background: `conic-gradient(hsl(var(--success)) ${pct * 3.6}deg, hsl(var(--muted)) 0)` }}
    >
      <div className="absolute inset-[11px] rounded-full bg-card" />
      <div className="relative text-center">
        <div className="text-[21px] font-bold text-foreground leading-none tabular">{pagados}/{total}</div>
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
