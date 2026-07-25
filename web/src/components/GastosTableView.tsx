'use client'

import { useState, useMemo, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import type { Gasto, GastoRecurrente } from '@/lib/types'
import EditGastoModal from './EditGastoModal'
import { formatARS, MEDIO_PAGO_LABELS, cn } from '@/lib/utils'
import { Search, X, Download, Paperclip, Trash2, Tag } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { bulkRecategorizarAction, bulkDeleteGastosAction } from '@/app/gastos/actions'
import { toast } from 'sonner'

interface Props {
  gastos: Gasto[]
  categorias: string[]
  colores?: Record<string, string>
  comercios?: string[]
  archivoCounts?: Record<string, number>
  recurrentes?: GastoRecurrente[]
}

const selectClass = cn(
  'h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors text-foreground cursor-pointer',
)
const DOW = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']
const MES3 = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
function diaLabel(fecha: string): string {
  const [y, m, d] = fecha.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  const hoy = new Date(); hoy.setHours(0, 0, 0, 0)
  const diff = Math.round((dt.getTime() - hoy.getTime()) / 86400000)
  if (diff === 0) return 'Hoy'
  if (diff === -1) return 'Ayer'
  return `${DOW[dt.getDay()]} ${d} ${MES3[m - 1]}`
}

export default function GastosTableView({ gastos, categorias, colores = {}, comercios: comerciosProp, archivoCounts, recurrentes }: Props) {
  const router = useRouter()
  const [search, setSearch] = useState('')
  const [categoria, setCategoria] = useState('')
  const [moneda, setMoneda] = useState('')
  const [mediopago, setMediopago] = useState('')
  const [editing, setEditing] = useState<Gasto | null>(null)
  const [sel, setSel] = useState<Set<string>>(new Set())
  const [bulkCat, setBulkCat] = useState('')
  const [isPending, startTransition] = useTransition()

  const mediosPago = useMemo(() => Array.from(new Set(gastos.map(g => g.medio_pago).filter(Boolean))).sort(), [gastos])
  const comerciosDelMes = useMemo(() => Array.from(new Set(gastos.map(g => g.comercio).filter((c): c is string => !!c))).sort(), [gastos])
  const comercios = comerciosProp ?? comerciosDelMes

  const filtered = useMemo(() => gastos.filter(g => {
    if (categoria && g.categoria !== categoria) return false
    if (moneda && g.moneda !== moneda) return false
    if (mediopago && g.medio_pago !== mediopago) return false
    if (search) {
      const q = search.toLowerCase()
      if (!(g.descripcion ?? '').toLowerCase().includes(q) && !(g.comercio ?? '').toLowerCase().includes(q)) return false
    }
    return true
  }), [gastos, search, categoria, moneda, mediopago])

  const totalARS = filtered.reduce((s, g) => s + (g.monto_ars ?? 0), 0)
  const totalUSD = filtered.filter(g => g.moneda === 'USD').reduce((s, g) => s + g.monto_original, 0)

  // Distribución por categoría (para el strip)
  const distrib = useMemo(() => {
    const m = new Map<string, number>()
    for (const g of filtered) m.set(g.categoria ?? 'Sin categoría', (m.get(g.categoria ?? 'Sin categoría') ?? 0) + (g.monto_ars ?? 0))
    const arr = Array.from(m.entries()).map(([cat, total]) => ({ cat, total, color: colores[cat] ?? '#9E9E9E' })).sort((a, b) => b.total - a.total)
    const top = arr.slice(0, 6)
    const resto = arr.slice(6)
    if (resto.length) top.push({ cat: 'Otras', total: resto.reduce((s, x) => s + x.total, 0), color: '#9E9E9E' })
    return top
  }, [filtered, colores])

  // Agrupar por día (filtered ya viene desc por fecha)
  const grupos = useMemo(() => {
    const m = new Map<string, Gasto[]>()
    for (const g of filtered) { if (!m.has(g.fecha)) m.set(g.fecha, []); m.get(g.fecha)!.push(g) }
    return Array.from(m.entries())
  }, [filtered])

  const hasFilters = search || categoria || moneda || mediopago
  const filteredIds = useMemo(() => filtered.map(g => g.id), [filtered])
  const allSelected = filteredIds.length > 0 && filteredIds.every(id => sel.has(id))

  function toggle(id: string) {
    setSel(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  }
  function toggleAll() {
    setSel(allSelected ? new Set() : new Set(filteredIds))
  }
  function clearSel() { setSel(new Set()) }

  function exportCSV() {
    const headers = ['Fecha', 'Descripcion', 'Comercio', 'Categoria', 'Medio de Pago', 'Moneda', 'Monto Original', 'Monto ARS', 'Cuotas']
    const rows = filtered.map(g => [g.fecha, `"${(g.descripcion ?? '').replace(/"/g, '""')}"`, `"${(g.comercio ?? '').replace(/"/g, '""')}"`, g.categoria ?? '', g.medio_pago ?? '', g.moneda, g.monto_original, g.monto_ars, g.cuotas > 1 ? `${g.cuota_actual}/${g.cuotas}` : '1'])
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'gastos.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  function doBulkRecat() {
    if (!bulkCat) return
    const ids = [...sel]
    startTransition(async () => {
      try { await bulkRecategorizarAction(ids, bulkCat); toast.success(`${ids.length} gasto(s) → ${bulkCat}`); clearSel(); setBulkCat(''); router.refresh() }
      catch (e: any) { toast.error(e.message ?? 'Error') }
    })
  }
  function doBulkDelete() {
    const ids = [...sel]
    if (!confirm(`¿Eliminar ${ids.length} gasto(s)?`)) return
    startTransition(async () => {
      try { await bulkDeleteGastosAction(ids); toast.success(`${ids.length} gasto(s) eliminado(s)`); clearSel(); router.refresh() }
      catch (e: any) { toast.error(e.message ?? 'Error') }
    })
  }

  return (
    <div className="pb-20">
      {/* Filtros */}
      <div className="flex flex-wrap gap-2 mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
          <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar descripción o comercio..."
            className="h-9 w-56 rounded-lg border border-input bg-background pl-9 pr-8 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors" />
          {search && <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"><X className="w-3.5 h-3.5" /></button>}
        </div>
        <select value={categoria} onChange={e => setCategoria(e.target.value)} className={selectClass}>
          <option value="">Todas las categorías</option>
          {categorias.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={mediopago} onChange={e => setMediopago(e.target.value)} className={selectClass}>
          <option value="">Todos los medios</option>
          {mediosPago.map(mp => <option key={mp} value={mp}>{MEDIO_PAGO_LABELS[mp] ?? mp}</option>)}
        </select>
        <select value={moneda} onChange={e => setMoneda(e.target.value)} className={selectClass}>
          <option value="">ARS + USD</option>
          <option value="ARS">Solo ARS</option>
          <option value="USD">Solo USD</option>
        </select>
        {hasFilters && <Button variant="ghost" size="sm" onClick={() => { setSearch(''); setCategoria(''); setMoneda(''); setMediopago('') }}><X className="w-3.5 h-3.5 mr-1" />Limpiar</Button>}
        <Button variant="outline" size="sm" onClick={exportCSV} className="ml-auto gap-1.5"><Download className="w-3.5 h-3.5" />CSV</Button>
      </div>

      {/* Resumen + strip de distribución */}
      <div className="flex items-center gap-3 mb-2 text-sm text-muted-foreground">
        <span><span className="font-semibold text-foreground">{filtered.length}</span> gastos · <span className="font-semibold text-foreground">{formatARS(totalARS)}</span>
          {hasFilters && gastos.length !== filtered.length && <span> (de {gastos.length})</span>}</span>
        {totalUSD > 0 && <span className="text-primary font-medium">· USD {totalUSD.toFixed(2)}</span>}
      </div>
      {distrib.length > 0 && totalARS > 0 && (
        <div className="mb-5">
          <div className="flex gap-0.5 h-2.5 rounded-full overflow-hidden mb-2">
            {distrib.map(d => <div key={d.cat} title={`${d.cat} · ${formatARS(d.total)}`} style={{ width: `${(d.total / totalARS) * 100}%`, backgroundColor: d.color }} />)}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {distrib.map(d => (
              <span key={d.cat} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: d.color }} />
                {d.cat} <span className="text-foreground font-medium tabular">{Math.round((d.total / totalARS) * 100)}%</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Lista agrupada por día */}
      {filtered.length === 0 ? (
        <Card><div className="text-center py-12 text-muted-foreground text-sm">No hay gastos con estos filtros.</div></Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border bg-muted/30">
            <input type="checkbox" checked={allSelected} onChange={toggleAll} className="h-4 w-4 rounded border-input accent-primary cursor-pointer" title="Seleccionar todo" />
            <span className="text-xs text-muted-foreground">{sel.size > 0 ? `${sel.size} seleccionados` : 'Seleccionar'}</span>
          </div>
          {grupos.map(([fecha, items]) => {
            const subtotal = items.reduce((s, g) => s + (g.monto_ars ?? 0), 0)
            return (
              <div key={fecha}>
                <div className="flex items-center justify-between px-4 py-1.5 bg-muted/40 border-b border-border/60">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{diaLabel(fecha)}</span>
                  <span className="text-[11px] font-semibold text-muted-foreground tabular">{formatARS(subtotal)}</span>
                </div>
                <div className="divide-y divide-border/50">
                  {items.map(g => {
                    const selected = sel.has(g.id)
                    return (
                      <div key={g.id} className={cn('flex items-center gap-3 px-4 py-2.5 transition-colors', selected ? 'bg-secondary/60' : 'hover:bg-muted/40')}>
                        <input type="checkbox" checked={selected} onChange={() => toggle(g.id)} onClick={e => e.stopPropagation()} className="h-4 w-4 rounded border-input accent-primary cursor-pointer flex-shrink-0" />
                        <button onClick={() => setEditing(g)} className="flex items-center gap-3 min-w-0 flex-1 text-left">
                          <span className="w-2 h-2 rounded-sm flex-shrink-0" style={{ backgroundColor: colores[g.categoria] ?? '#9E9E9E' }} />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <span className="text-sm font-medium text-foreground truncate">{g.comercio || g.descripcion}</span>
                              {g.cuotas > 1 && <span className="text-[11px] text-muted-foreground flex-shrink-0">{g.cuota_actual}/{g.cuotas}</span>}
                              {archivoCounts && archivoCounts[g.id] > 0 && <Paperclip className="w-3 h-3 text-success flex-shrink-0" />}
                            </div>
                            <p className="text-xs text-muted-foreground truncate">{g.categoria ?? 'Sin categoría'} · {MEDIO_PAGO_LABELS[g.medio_pago] ?? g.medio_pago}</p>
                          </div>
                        </button>
                        <div className="text-right flex-shrink-0">
                          <p className="text-sm font-semibold text-foreground tabular">{formatARS(g.monto_ars)}</p>
                          {g.moneda === 'USD' && <p className="text-[11px] text-muted-foreground tabular">US$ {g.monto_original.toLocaleString('es-AR')}</p>}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </Card>
      )}

      {/* Barra de acciones en lote */}
      {sel.size > 0 && (
        <div className="fixed bottom-0 left-0 right-0 md:left-60 z-40 border-t border-border bg-card/95 backdrop-blur-xl px-4 py-3">
          <div className="max-w-5xl mx-auto flex items-center gap-3 flex-wrap">
            <span className="text-sm font-medium text-foreground">{sel.size} seleccionados</span>
            <div className="flex items-center gap-1.5">
              <Tag className="w-4 h-4 text-muted-foreground" />
              <select value={bulkCat} onChange={e => setBulkCat(e.target.value)} className={cn(selectClass, 'h-8')}>
                <option value="">Recategorizar a…</option>
                {categorias.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <Button size="sm" onClick={doBulkRecat} disabled={!bulkCat || isPending}>Aplicar</Button>
            </div>
            <Button size="sm" variant="outline" onClick={doBulkDelete} disabled={isPending} className="text-destructive hover:text-destructive gap-1.5"><Trash2 className="w-3.5 h-3.5" />Eliminar</Button>
            <Button size="sm" variant="ghost" onClick={clearSel} className="ml-auto">Cancelar</Button>
          </div>
        </div>
      )}

      {editing && <EditGastoModal gasto={editing} categorias={categorias} comercios={comercios} recurrentes={recurrentes} onClose={() => setEditing(null)} />}
    </div>
  )
}
