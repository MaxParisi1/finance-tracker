'use client'

import { useState, useTransition } from 'react'
import type { PlanCuota } from '@/lib/types'
import { materializarPlanesFijosAction } from '@/app/cuotas/actions'
import { formatARS, cn, MONTH_NAMES_CAP } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Plus, CheckCircle2, AlertCircle, Zap } from 'lucide-react'
import PlanCuotaModal from './PlanCuotaModal'
import RegistrarPagoCuotaModal from './RegistrarPagoCuotaModal'
import { toast } from 'sonner'

interface Props {
  planes: PlanCuota[]
  categorias: string[]
}

function diasParaVencer(fecha: string): number {
  const hoy = new Date(); hoy.setHours(0, 0, 0, 0)
  return Math.round((new Date(fecha + 'T00:00:00').getTime() - hoy.getTime()) / 86400000)
}
function urgenciaBadge(dias: number) {
  if (dias < 0) return <Badge variant="destructive">Vencida</Badge>
  if (dias === 0) return <Badge variant="destructive">Hoy</Badge>
  if (dias <= 3) return <Badge variant="warning">En {dias} días</Badge>
  if (dias <= 7) return <Badge variant="secondary">En {dias} días</Badge>
  return null
}
/** Mes/año en que termina el plan (última cuota). */
function finPlan(p: PlanCuota): { y: number; m: number } {
  const [y, m] = p.proximo_vencimiento.split('-').map(Number)
  const restantes = Math.max(0, p.cuotas_total - p.cuota_actual)
  const total = (m - 1) + restantes
  return { y: y + Math.floor(total / 12), m: (total % 12) + 1 }
}

export default function PlanesCuotaView({ planes, categorias }: Props) {
  const [showNew, setShowNew] = useState(false)
  const [editing, setEditing] = useState<PlanCuota | null>(null)
  const [registrando, setRegistrando] = useState<PlanCuota | null>(null)
  const [isPending, startTransition] = useTransition()

  const activos = planes.filter(p => p.activo)
  const inactivos = planes.filter(p => !p.activo)
  const fijosVencidos = activos.filter(p => p.tipo === 'fijo' && diasParaVencer(p.proximo_vencimiento) <= 0)

  // KPIs de deuda
  const fijos = activos.filter(p => p.tipo === 'fijo' && p.monto_cuota != null && p.moneda === 'ARS')
  const cuotaMensual = fijos.reduce((s, p) => s + (p.monto_cuota ?? 0), 0)
  const comprometidoRestante = fijos.reduce((s, p) => s + (p.monto_cuota ?? 0) * Math.max(0, p.cuotas_total - p.cuota_actual + 1), 0)

  // Próximas liberaciones (planes fijos que terminan, con el alivio mensual)
  const liberaciones = fijos
    .map(p => ({ p, fin: finPlan(p) }))
    .sort((a, b) => (a.fin.y - b.fin.y) || (a.fin.m - b.fin.m))
    .slice(0, 4)

  function handleMaterializar() {
    startTransition(async () => {
      try {
        const r = await materializarPlanesFijosAction()
        if (r.insertados > 0) toast.success(`${r.insertados} cuota(s) registrada(s)`)
        else toast.info('No hay cuotas nuevas para registrar')
        if (r.errores.length > 0) toast.error(`Errores: ${r.errores.join(', ')}`)
      } catch (e: any) { toast.error(e.message) }
    })
  }

  return (
    <div className="space-y-6">
      {/* KPIs de deuda */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-border bg-card px-4 py-3">
          <p className="text-xs text-muted-foreground">Comprometido restante</p>
          <p className="font-display text-2xl text-foreground mt-1 tabular">{formatARS(comprometidoRestante)}</p>
          <p className="text-xs text-muted-foreground mt-0.5">en cuotas fijas ARS</p>
        </div>
        <div className="rounded-xl border border-border bg-card px-4 py-3">
          <p className="text-xs text-muted-foreground">Cuota mensual</p>
          <p className="font-display text-2xl text-foreground mt-1 tabular">{formatARS(cuotaMensual)}</p>
          <p className="text-xs text-muted-foreground mt-0.5">/mes comprometido</p>
        </div>
        <div className="rounded-xl border border-border bg-card px-4 py-3">
          <p className="text-xs text-muted-foreground">Planes activos</p>
          <p className="font-display text-2xl text-foreground mt-1 tabular">{activos.length}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{fijosVencidos.length > 0 ? `${fijosVencidos.length} vencida(s)` : 'al día'}</p>
        </div>
      </div>

      {/* Alerta fijos vencidos */}
      {fijosVencidos.length > 0 && (
        <div className="flex items-center justify-between rounded-xl border border-warning/40 bg-warning/5 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 text-warning flex-shrink-0" />
            <p className="text-sm text-foreground"><span className="font-semibold">{fijosVencidos.length}</span> cuota{fijosVencidos.length > 1 ? 's fijas vencidas' : ' fija vencida'} sin registrar</p>
          </div>
          <Button size="sm" onClick={handleMaterializar} disabled={isPending} className="gap-1.5 flex-shrink-0"><Zap className="w-3.5 h-3.5" />{isPending ? 'Registrando...' : 'Registrar ahora'}</Button>
        </div>
      )}

      {/* Próximas liberaciones */}
      {liberaciones.length > 0 && (
        <div className="rounded-xl border border-border bg-card px-5 py-4">
          <p className="text-sm font-semibold text-foreground mb-3">Próximas liberaciones</p>
          <div className="space-y-2">
            {liberaciones.map(({ p, fin }) => (
              <div key={p.id} className="flex items-center gap-3 text-sm">
                <span className="text-xs text-muted-foreground w-20 flex-shrink-0">{MONTH_NAMES_CAP[fin.m - 1].slice(0, 3)} {String(fin.y).slice(2)}</span>
                <span className="text-foreground truncate flex-1">{p.descripcion}</span>
                <span className="text-success font-medium tabular whitespace-nowrap">libera {formatARS(p.monto_cuota ?? 0)}/mes</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Header acciones */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">{activos.length}</span> plan{activos.length !== 1 ? 'es' : ''} activo{activos.length !== 1 ? 's' : ''}</p>
        <Button size="sm" onClick={() => setShowNew(true)} className="gap-1.5"><Plus className="w-3.5 h-3.5" />Registrar cuotas</Button>
      </div>

      {activos.length === 0 && (
        <Card><CardContent className="py-12 text-center">
          <p className="text-muted-foreground text-sm mb-4">No tenés planes de cuotas activos.</p>
          <Button onClick={() => setShowNew(true)}><Plus className="w-4 h-4 mr-1.5" />Registrar primer plan</Button>
        </CardContent></Card>
      )}

      {activos.map(plan => {
        const pct = Math.round(((plan.cuota_actual - 1) / plan.cuotas_total) * 100)
        const dias = diasParaVencer(plan.proximo_vencimiento)
        const vencida = dias < 0
        const proxima = dias >= 0 && dias <= 7
        const stripe = vencida ? 'bg-destructive' : proxima ? 'bg-warning' : 'bg-border'
        return (
          <Card key={plan.id} className="overflow-hidden cursor-pointer transition-shadow hover:shadow-card-hover" onClick={() => setEditing(plan)}>
            <div className="flex">
              <span className={cn('w-1 flex-shrink-0', stripe)} />
              <CardContent className="py-4 px-5 flex-1">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-foreground truncate">{plan.descripcion}</span>
                      <Badge variant={plan.tipo === 'fijo' ? 'secondary' : 'default'} className="text-[10px] flex-shrink-0">{plan.tipo === 'fijo' ? 'Sin interés' : 'Con interés'}</Badge>
                      {urgenciaBadge(dias)}
                    </div>
                    {plan.comercio && <p className="text-xs text-muted-foreground mt-0.5">{plan.comercio}</p>}
                  </div>
                  <div className="text-right flex-shrink-0">
                    {plan.tipo === 'fijo' && plan.monto_cuota != null ? (
                      <p className="text-sm font-bold text-foreground tabular">{plan.moneda === 'USD' ? `US$ ${plan.monto_cuota.toLocaleString('es-AR')}` : formatARS(plan.monto_cuota)}<span className="text-xs font-normal text-muted-foreground">/mes</span></p>
                    ) : <p className="text-xs text-muted-foreground">Monto variable</p>}
                  </div>
                </div>
                <div className="mb-2.5"><Progress value={pct} className="h-1.5" indicatorClassName={vencida ? 'bg-destructive' : proxima ? 'bg-warning' : undefined} /></div>
                <div className="flex items-center justify-between">
                  <p className="text-xs text-muted-foreground">Cuota <span className="font-medium text-foreground">{plan.cuota_actual}</span> de {plan.cuotas_total} · vence día {plan.dia_del_mes} · termina {MONTH_NAMES_CAP[finPlan(plan).m - 1].slice(0, 3)} {String(finPlan(plan).y).slice(2)}</p>
                  <div className="flex items-center gap-2">
                    {plan.tipo === 'variable' && <Button size="sm" variant="outline" className="h-7 px-2.5 text-xs" onClick={e => { e.stopPropagation(); setRegistrando(plan) }}>Registrar pago</Button>}
                    <p className="text-xs text-muted-foreground">{pct}%</p>
                  </div>
                </div>
              </CardContent>
            </div>
          </Card>
        )
      })}

      {inactivos.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">Terminados / pausados ({inactivos.length})</p>
          <div className="space-y-2">
            {inactivos.map(plan => (
              <div key={plan.id} className="flex items-center justify-between rounded-lg border border-border/50 px-4 py-3 opacity-60 cursor-pointer hover:opacity-80 transition-opacity" onClick={() => setEditing(plan)}>
                <div className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-muted-foreground" /><span className="text-sm text-muted-foreground">{plan.descripcion}</span></div>
                <span className="text-xs text-muted-foreground">{Math.min(plan.cuota_actual, plan.cuotas_total)}/{plan.cuotas_total} cuotas</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {showNew && <PlanCuotaModal categorias={categorias} onClose={() => setShowNew(false)} />}
      {editing && <PlanCuotaModal plan={editing} categorias={categorias} onClose={() => setEditing(null)} />}
      {registrando && <RegistrarPagoCuotaModal plan={registrando} onClose={() => setRegistrando(null)} />}
    </div>
  )
}
