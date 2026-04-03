'use client'

import { useState, useTransition } from 'react'
import type { GastoRecurrente } from '@/lib/types'
import type { RecurrenteConCosto } from '@/lib/queries'
import RecurrenteModal from './RecurrenteModal'
import { formatARS } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { materializarRecurrentesAction } from '@/app/recurrentes/actions'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Plus, CheckCircle2, AlertCircle } from 'lucide-react'

const FRECUENCIA_LABEL: Record<string, string> = {
  mensual: 'Mensual',
  anual: 'Anual',
  semanal: 'Semanal',
}

interface Props {
  recurrentes: RecurrenteConCosto[]
  total_mensual_ars: number
  total_anual_ars: number
  tc_blue: number | null
  tc_fecha: string | null
  tc_es_hoy: boolean
  categorias: string[]
}

export default function RecurrentesView({
  recurrentes, total_mensual_ars, total_anual_ars,
  tc_blue, tc_fecha, tc_es_hoy, categorias,
}: Props) {
  const [editing, setEditing] = useState<GastoRecurrente | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [isPending, startTransition] = useTransition()
  const [materializeResult, setMaterializeResult] = useState<{
    insertados: number; omitidos: number; errores: string[]
  } | null>(null)

  const recurrentesSorted = [...recurrentes].sort(
    (a, b) => a.dias_para_vencimiento - b.dias_para_vencimiento,
  )

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
    startTransition(async () => {
      const result = await materializarRecurrentesAction()
      setMaterializeResult(result)
    })
  }

  const pendingCount = recurrentes.filter(r => r.dias_para_vencimiento <= 0 && !r.no_materializar).length

  return (
    <>
      {/* Resumen total */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <Card className="relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-0.5 gradient-primary opacity-60" />
          <CardContent className="py-4">
            <p className="text-xs font-medium text-muted-foreground">Compromiso mensual</p>
            <p className="text-2xl font-bold text-foreground mt-1 tabular">{formatARS(total_mensual_ars)}</p>
            <p className="text-xs text-primary mt-0.5">{recurrentes.length} activos</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs font-medium text-muted-foreground">Compromiso anual</p>
            <p className="text-2xl font-bold text-foreground mt-1 tabular">{formatARS(total_anual_ars)}</p>
            <p className="text-xs text-muted-foreground mt-0.5">proyectado 12 meses</p>
          </CardContent>
        </Card>
        {tc_blue && (
          <Card>
            <CardContent className="py-4">
              <p className="text-xs font-medium text-muted-foreground">Equiv. mensual USD</p>
              <p className="text-2xl font-bold text-foreground mt-1 tabular">
                USD {Math.round(total_mensual_ars / tc_blue).toLocaleString('es-AR')}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                TC ${tc_blue.toLocaleString('es-AR')}
                {tc_fecha && (
                  <span className={cn('ml-1', tc_es_hoy ? 'text-success' : 'text-warning')}>
                    · {tc_es_hoy ? 'hoy' : tc_fecha}
                  </span>
                )}
              </p>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Barra de acciones */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          {pendingCount > 0 && (
            <Button onClick={handleMaterialize} disabled={isPending}>
              {isPending ? 'Materializando...' : `Registrar vencidos (${pendingCount})`}
            </Button>
          )}
          {materializeResult && (
            <p className="text-sm text-muted-foreground flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-success" />
              {materializeResult.insertados} registrados
              {materializeResult.omitidos > 0 && `, ${materializeResult.omitidos} ya existían`}
              {materializeResult.errores.length > 0 && (
                <span className="text-destructive ml-1">· {materializeResult.errores.length} errores</span>
              )}
            </p>
          )}
        </div>
        <Button variant="outline" onClick={() => setShowNew(true)}>
          <Plus className="w-4 h-4 mr-1" />
          Nuevo recurrente
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Lista de recurrentes */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-0">
            <CardTitle className="text-base">Detalle</CardTitle>
          </CardHeader>

          {recurrentesSorted.length === 0 ? (
            <CardContent className="py-12 text-center text-muted-foreground text-sm">
              No hay gastos recurrentes activos.
            </CardContent>
          ) : (
            <div className="divide-y divide-border/60">
              {recurrentesSorted.map(r => {
                const urgente = r.dias_para_vencimiento >= 0 && r.dias_para_vencimiento <= 3
                const proximo = r.dias_para_vencimiento > 3 && r.dias_para_vencimiento <= 7
                const vencido = r.dias_para_vencimiento < 0

                return (
                  <button
                    key={r.id}
                    onClick={() => setEditing(r)}
                    className="w-full flex items-center justify-between px-5 py-4 hover:bg-muted/50 transition-colors text-left"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium text-foreground truncate">{r.descripcion}</p>
                        {r.no_materializar && (
                          <Badge variant="secondary">auto</Badge>
                        )}
                        {!r.no_materializar && vencido && (
                          <Badge variant="destructive">Vencido</Badge>
                        )}
                        {!r.no_materializar && urgente && !vencido && (
                          <Badge variant="destructive">
                            {r.dias_para_vencimiento === 0 ? '¡Hoy!' : `${r.dias_para_vencimiento}d`}
                          </Badge>
                        )}
                        {!r.no_materializar && proximo && (
                          <Badge variant="warning">{r.dias_para_vencimiento}d</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5 text-xs text-muted-foreground">
                        <span>{r.categoria ?? 'Sin categoría'}</span>
                        <span className="opacity-40">·</span>
                        <span>{FRECUENCIA_LABEL[r.frecuencia] ?? r.frecuencia}</span>
                        <span className="opacity-40">·</span>
                        <span>Día {r.dia_del_mes}</span>
                      </div>
                    </div>
                    <div className="text-right ml-4">
                      <p className="text-sm font-semibold text-foreground tabular">
                        {r.moneda === 'USD'
                          ? `USD ${r.monto_original.toLocaleString('es-AR', { minimumFractionDigits: 2 })}`
                          : formatARS(r.monto_original)}
                      </p>
                      {(r.frecuencia !== 'mensual' || (r.moneda === 'USD' && tc_blue)) && (
                        <p className="text-xs text-muted-foreground mt-0.5 tabular">≈ {formatARS(r.mensual_ars)}/mes</p>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </Card>

        {/* Desglose por categoría */}
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="text-base">Por categoría</CardTitle>
          </CardHeader>
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
                        <div className="h-full gradient-primary rounded-full" style={{ width: `${pct}%` }} />
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

      {editing && (
        <RecurrenteModal recurrente={editing} categorias={categorias} onClose={() => setEditing(null)} />
      )}
      {showNew && (
        <RecurrenteModal categorias={categorias} onClose={() => setShowNew(false)} />
      )}
    </>
  )
}
