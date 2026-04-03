'use client'

import { useState, useTransition } from 'react'
import type { PlanCuota } from '@/lib/types'
import { materializarPlanesFijosAction } from '@/app/cuotas/actions'
import { formatARS } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { BorderBeam } from '@/components/magicui/border-beam'
import { Plus, CheckCircle2, AlertCircle, Zap } from 'lucide-react'
import PlanCuotaModal from './PlanCuotaModal'
import RegistrarPagoCuotaModal from './RegistrarPagoCuotaModal'
import { toast } from 'sonner'

interface Props {
  planes: PlanCuota[]
  categorias: string[]
}

function diasParaVencer(fecha: string): number {
  const hoy = new Date()
  hoy.setHours(0, 0, 0, 0)
  const d = new Date(fecha + 'T00:00:00')
  return Math.round((d.getTime() - hoy.getTime()) / 86400000)
}

function urgenciaBadge(dias: number, tipo: 'fijo' | 'variable') {
  if (dias < 0) return <Badge variant="destructive">Vencida</Badge>
  if (dias === 0) return <Badge variant="destructive">Hoy</Badge>
  if (dias <= 3) return <Badge variant="warning">En {dias} días</Badge>
  if (dias <= 7) return <Badge variant="secondary">En {dias} días</Badge>
  return null
}

export default function PlanesCuotaView({ planes, categorias }: Props) {
  const [showNew, setShowNew] = useState(false)
  const [editing, setEditing] = useState<PlanCuota | null>(null)
  const [registrando, setRegistrando] = useState<PlanCuota | null>(null)
  const [isPending, startTransition] = useTransition()
  const [materializeResult, setMaterializeResult] = useState<{ insertados: number; omitidos: number } | null>(null)

  const activos = planes.filter(p => p.activo)
  const inactivos = planes.filter(p => !p.activo)

  const fijosVencidos = activos.filter(p => p.tipo === 'fijo' && diasParaVencer(p.proximo_vencimiento) <= 0)

  function handleMaterializar() {
    startTransition(async () => {
      try {
        const r = await materializarPlanesFijosAction()
        setMaterializeResult({ insertados: r.insertados, omitidos: r.omitidos })
        if (r.insertados > 0) toast.success(`${r.insertados} cuota${r.insertados > 1 ? 's' : ''} registrada${r.insertados > 1 ? 's' : ''} automáticamente`)
        else toast.info('No hay cuotas nuevas para registrar')
        if (r.errores.length > 0) toast.error(`Errores: ${r.errores.join(', ')}`)
      } catch (e: any) {
        toast.error(e.message)
      }
    })
  }

  return (
    <div className="space-y-6">

      {/* Alerta fijos vencidos */}
      {fijosVencidos.length > 0 && (
        <div className="flex items-center justify-between rounded-xl border border-warning/40 bg-warning/5 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 text-warning flex-shrink-0" />
            <p className="text-sm text-foreground">
              <span className="font-semibold">{fijosVencidos.length}</span> cuota{fijosVencidos.length > 1 ? 's fijas vencidas' : ' fija vencida'} sin registrar en gastos
            </p>
          </div>
          <Button size="sm" onClick={handleMaterializar} disabled={isPending} className="gap-1.5 flex-shrink-0">
            <Zap className="w-3.5 h-3.5" />
            {isPending ? 'Registrando...' : 'Registrar ahora'}
          </Button>
        </div>
      )}

      {/* Header acciones */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          <span className="font-semibold text-foreground">{activos.length}</span> plan{activos.length !== 1 ? 'es' : ''} activo{activos.length !== 1 ? 's' : ''}
        </p>
        <Button size="sm" onClick={() => setShowNew(true)} className="gap-1.5">
          <Plus className="w-3.5 h-3.5" />
          Registrar cuotas
        </Button>
      </div>

      {/* Planes activos */}
      {activos.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground text-sm mb-4">No tenés planes de cuotas activos.</p>
            <Button onClick={() => setShowNew(true)}>
              <Plus className="w-4 h-4 mr-1.5" />
              Registrar primer plan
            </Button>
          </CardContent>
        </Card>
      )}

      {activos.map(plan => {
        const pct = Math.round(((plan.cuota_actual - 1) / plan.cuotas_total) * 100)
        const dias = diasParaVencer(plan.proximo_vencimiento)
        const badge = urgenciaBadge(dias, plan.tipo)
        const vencida = dias < 0
        const proxima = dias <= 7

        return (
          <Card
            key={plan.id}
            className={cn('relative overflow-hidden cursor-pointer transition-shadow hover:shadow-card-hover')}
            onClick={() => setEditing(plan)}
          >
            {(vencida) && <BorderBeam colorFrom="#ef4444" colorTo="#f97316" duration={3} size={80} borderWidth={1.5} />}
            {(!vencida && proxima) && <BorderBeam colorFrom="#f59e0b" colorTo="#eab308" duration={4} size={60} borderWidth={1} />}

            <CardContent className="py-4 px-5">
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-foreground truncate">{plan.descripcion}</span>
                    <Badge variant={plan.tipo === 'fijo' ? 'secondary' : 'default'} className="text-[10px] flex-shrink-0">
                      {plan.tipo === 'fijo' ? 'Sin interés' : 'Con interés'}
                    </Badge>
                    {badge}
                  </div>
                  {plan.comercio && (
                    <p className="text-xs text-muted-foreground mt-0.5">{plan.comercio}</p>
                  )}
                </div>

                <div className="text-right flex-shrink-0">
                  {plan.tipo === 'fijo' && plan.monto_cuota != null ? (
                    <p className="text-sm font-bold text-foreground tabular">
                      {plan.moneda === 'USD' ? `USD ${plan.monto_cuota.toLocaleString('es-AR')}` : formatARS(plan.monto_cuota)}
                      <span className="text-xs font-normal text-muted-foreground">/mes</span>
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">Monto variable</p>
                  )}
                </div>
              </div>

              {/* Progreso */}
              <div className="mb-2.5">
                <Progress
                  value={pct}
                  className="h-1.5"
                  indicatorClassName={vencida ? 'bg-destructive' : proxima ? 'bg-warning' : undefined}
                />
              </div>

              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Cuota <span className="font-medium text-foreground">{plan.cuota_actual}</span> de {plan.cuotas_total}
                  {' · '}
                  vence el día {plan.dia_del_mes}
                </p>
                <div className="flex items-center gap-2">
                  {plan.tipo === 'variable' && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 px-2.5 text-xs"
                      onClick={e => { e.stopPropagation(); setRegistrando(plan) }}
                    >
                      Registrar pago
                    </Button>
                  )}
                  <p className="text-xs text-muted-foreground">{pct}%</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )
      })}

      {/* Planes terminados / pausados */}
      {inactivos.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">
            Terminados / pausados ({inactivos.length})
          </p>
          <div className="space-y-2">
            {inactivos.map(plan => (
              <div
                key={plan.id}
                className="flex items-center justify-between rounded-lg border border-border/50 px-4 py-3 opacity-60 cursor-pointer hover:opacity-80 transition-opacity"
                onClick={() => setEditing(plan)}
              >
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">{plan.descripcion}</span>
                </div>
                <span className="text-xs text-muted-foreground">
                  {Math.min(plan.cuota_actual, plan.cuotas_total)}/{plan.cuotas_total} cuotas
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modales */}
      {showNew && (
        <PlanCuotaModal categorias={categorias} onClose={() => setShowNew(false)} />
      )}
      {editing && (
        <PlanCuotaModal plan={editing} categorias={categorias} onClose={() => setEditing(null)} />
      )}
      {registrando && (
        <RegistrarPagoCuotaModal plan={registrando} onClose={() => setRegistrando(null)} />
      )}
    </div>
  )
}
