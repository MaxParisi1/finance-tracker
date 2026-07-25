'use client'

import { useState, useMemo, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import type { ArchivoDrive, Gasto } from '@/lib/types'
import { formatDate, formatARS, cn } from '@/lib/utils'
import { Search, X, ExternalLink, Link2, Unlink, Trash2, FileText, Image as ImageIcon, LayoutGrid, List, Paperclip } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import VincularGastoModal from './VincularGastoModal'
import AdjuntarArchivoModal from './AdjuntarArchivoModal'

const TIPO_LABELS: Record<string, string> = {
  factura: 'Factura', comprobante: 'Comprobante', ticket: 'Ticket', recibo: 'Recibo', resumen: 'Resumen',
}
const TIPO_VARIANTS: Record<string, 'default' | 'secondary' | 'warning' | 'muted'> = {
  factura: 'default', comprobante: 'secondary', ticket: 'warning', recibo: 'muted', resumen: 'muted',
}

const selectClass = cn(
  'h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors text-foreground cursor-pointer',
)

function esImagen(a: ArchivoDrive) {
  return (a.mime_type ?? '').startsWith('image/')
}

interface Props {
  archivos: ArchivoDrive[]
  categorias: string[]
  gastos: Gasto[]
}

export default function ComprobantesView({ archivos, categorias, gastos }: Props) {
  const router = useRouter()
  const [search, setSearch] = useState('')
  const [categoria, setCategoria] = useState('')
  const [tipo, setTipo] = useState('')
  const [vista, setVista] = useState<'galeria' | 'tabla'>('galeria')
  const [vinculando, setVinculando] = useState<ArchivoDrive | null>(null)
  const [adjuntando, setAdjuntando] = useState<Gasto | null>(null)
  const [archivosState, setArchivosState] = useState<ArchivoDrive[]>(archivos)
  const [eliminando, setEliminando] = useState<string | null>(null)
  const [desvinculando, setDesvinculando] = useState<string | null>(null)

  // Re-sincronizar cuando el server revalida (ej: tras adjuntar)
  useEffect(() => { setArchivosState(archivos) }, [archivos])

  // ── Cobertura: qué gastos del mes tienen comprobante ──
  const gastoIdsConArchivo = useMemo(
    () => new Set(archivosState.map(a => a.gasto_id).filter(Boolean) as string[]),
    [archivosState],
  )
  const sinComprobante = useMemo(
    () => gastos
      .filter(g => !gastoIdsConArchivo.has(g.id))
      .sort((a, b) => {
        // Prioridad: fijos primero, luego por monto desc
        const af = a.es_recurrente || a.recurrente_id ? 1 : 0
        const bf = b.es_recurrente || b.recurrente_id ? 1 : 0
        if (af !== bf) return bf - af
        return (b.monto_ars ?? 0) - (a.monto_ars ?? 0)
      }),
    [gastos, gastoIdsConArchivo],
  )
  const conComprobante = gastos.length - sinComprobante.length
  const cobertura = gastos.length > 0 ? Math.round((conComprobante / gastos.length) * 100) : 100

  async function handleEliminar(id: string) {
    if (!confirm('¿Eliminar este comprobante de la base de datos?')) return
    setEliminando(id)
    try {
      const res = await fetch(`/api/archivos?id=${id}`, { method: 'DELETE' })
      if (res.ok) setArchivosState(prev => prev.filter(a => a.id !== id))
    } finally { setEliminando(null) }
  }

  async function handleDesvincular(id: string) {
    if (!confirm('¿Desvincular este comprobante del gasto?')) return
    setDesvinculando(id)
    try {
      const res = await fetch(`/api/archivos?id=${id}`, { method: 'PATCH' })
      if (res.ok) setArchivosState(prev => prev.map(a => a.id === id ? { ...a, gasto_id: null } : a))
    } finally { setDesvinculando(null) }
  }

  const tipos = useMemo(() => Array.from(new Set(archivosState.map(a => a.tipo).filter(Boolean))).sort(), [archivosState])

  const filtered = useMemo(() => archivosState.filter(a => {
    if (categoria && a.categoria !== categoria) return false
    if (tipo && a.tipo !== tipo) return false
    if (search) {
      const q = search.toLowerCase()
      if (!(a.comercio ?? '').toLowerCase().includes(q) && !(a.drive_file_name ?? '').toLowerCase().includes(q)) return false
    }
    return true
  }), [archivosState, search, categoria, tipo])

  const hasFilters = search || categoria || tipo

  return (
    <div>
      {/* Cobertura */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        <div className="rounded-xl border border-border bg-card px-4 py-3">
          <p className="text-xs text-muted-foreground">Gastos del mes</p>
          <p className="text-lg font-semibold text-foreground mt-0.5 tabular">{gastos.length}</p>
        </div>
        <div className="rounded-xl border border-border bg-card px-4 py-3">
          <p className="text-xs text-muted-foreground">Con comprobante</p>
          <p className="text-lg font-semibold text-foreground mt-0.5 tabular">{conComprobante} <span className="text-sm font-normal text-muted-foreground">de {gastos.length}</span></p>
        </div>
        <div className="rounded-xl border border-border bg-card px-4 py-3">
          <p className="text-xs text-muted-foreground">Cobertura</p>
          <div className="flex items-center gap-2 mt-1">
            <p className={cn('text-lg font-semibold tabular', cobertura >= 80 ? 'text-success' : cobertura >= 50 ? 'text-warning' : 'text-foreground')}>{cobertura}%</p>
            <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
              <div className={cn('h-full rounded-full', cobertura >= 80 ? 'bg-success' : cobertura >= 50 ? 'bg-warning' : 'bg-primary')} style={{ width: `${cobertura}%` }} />
            </div>
          </div>
        </div>
      </div>

      {/* Gastos sin comprobante */}
      {sinComprobante.length > 0 && (
        <Card className="mb-6">
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <div>
              <h2 className="text-base font-semibold text-foreground">Gastos sin comprobante</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Adjuntá la factura o ticket de estos pagos</p>
            </div>
            <Badge variant="warning">{sinComprobante.length}</Badge>
          </div>
          <div className="divide-y divide-border/70 max-h-[340px] overflow-y-auto">
            {sinComprobante.map(g => {
              const esFijo = g.es_recurrente || g.recurrente_id
              return (
                <div key={g.id} className="flex items-center gap-3 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground truncate">{g.comercio || g.descripcion}</span>
                      {esFijo && <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-secondary text-secondary-foreground flex-shrink-0">fijo</span>}
                    </div>
                    <p className="text-xs text-muted-foreground">{formatDate(g.fecha)} · {g.categoria ?? 'Sin categoría'}</p>
                  </div>
                  <span className="text-sm font-semibold text-foreground tabular whitespace-nowrap">{formatARS(g.monto_ars ?? 0)}</span>
                  <button
                    onClick={() => setAdjuntando(g)}
                    className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:opacity-90 whitespace-nowrap inline-flex items-center gap-1"
                  >
                    <Paperclip className="w-3 h-3" /> Adjuntar
                  </button>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Filtros + toggle vista */}
      <div className="flex flex-wrap items-center gap-2 mb-5">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
          <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar comercio o archivo..."
            className={cn('h-9 w-56 rounded-lg border border-input bg-background pl-9 pr-8 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors')} />
          {search && <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"><X className="w-3.5 h-3.5" /></button>}
        </div>
        <select value={categoria} onChange={e => setCategoria(e.target.value)} className={selectClass}>
          <option value="">Todas las categorías</option>
          {categorias.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={tipo} onChange={e => setTipo(e.target.value)} className={selectClass}>
          <option value="">Todos los tipos</option>
          {tipos.map(t => <option key={t} value={t}>{TIPO_LABELS[t] ?? t}</option>)}
        </select>
        {hasFilters && <Button variant="ghost" size="sm" onClick={() => { setSearch(''); setCategoria(''); setTipo('') }}><X className="w-3.5 h-3.5 mr-1" />Limpiar</Button>}

        <div className="ml-auto flex items-center gap-2">
          <span className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">{filtered.length}</span> archivos</span>
          <div className="flex rounded-lg border border-input p-0.5 bg-background">
            <button onClick={() => setVista('galeria')} className={cn('p-1.5 rounded-md transition-colors', vista === 'galeria' ? 'bg-secondary text-primary' : 'text-muted-foreground hover:text-foreground')} title="Galería"><LayoutGrid className="w-4 h-4" /></button>
            <button onClick={() => setVista('tabla')} className={cn('p-1.5 rounded-md transition-colors', vista === 'tabla' ? 'bg-secondary text-primary' : 'text-muted-foreground hover:text-foreground')} title="Tabla"><List className="w-4 h-4" /></button>
          </div>
        </div>
      </div>

      {/* Archivos */}
      {filtered.length === 0 ? (
        <Card><div className="text-center py-12 text-muted-foreground text-sm">No hay comprobantes en este período.</div></Card>
      ) : vista === 'galeria' ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {filtered.map(a => (
            <div key={a.id} className="group rounded-xl border border-border bg-card overflow-hidden flex flex-col hover:shadow-card-hover transition-shadow">
              <div className="relative aspect-[4/3] bg-muted/50 flex items-center justify-center">
                {esImagen(a) ? <ImageIcon className="w-9 h-9 text-muted-foreground/60" /> : <FileText className="w-9 h-9 text-muted-foreground/60" />}
                <span className="absolute top-2 left-2"><Badge variant={TIPO_VARIANTS[a.tipo] ?? 'muted'} className="text-[10px]">{TIPO_LABELS[a.tipo] ?? a.tipo}</Badge></span>
                {a.gasto_id ? (
                  <span className="absolute top-2 right-2"><Badge variant="success" className="text-[10px]">🔗</Badge></span>
                ) : (
                  <button onClick={() => setVinculando(a)} title="Vincular a un gasto" className="absolute top-2 right-2 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-background/90 border border-border text-muted-foreground hover:text-primary hover:border-primary">Vincular</button>
                )}
              </div>
              <div className="p-3 flex-1 flex flex-col">
                <p className="text-sm font-medium text-foreground truncate">{a.comercio ?? '—'}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{formatDate(a.fecha)}{a.monto != null ? ` · ${a.moneda === 'USD' ? 'US$ ' : '$'}${a.monto.toLocaleString('es-AR')}` : ''}</p>
                <div className="flex items-center justify-between mt-2 pt-2 border-t border-border/60">
                  {a.drive_web_view_link ? (
                    <a href={a.drive_web_view_link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:opacity-80 font-medium">Ver <ExternalLink className="w-3 h-3" /></a>
                  ) : <span className="text-xs text-muted-foreground">—</span>}
                  <div className="flex items-center gap-2">
                    {a.gasto_id && <button onClick={() => handleDesvincular(a.id)} disabled={desvinculando === a.id} title="Desvincular" className="text-muted-foreground hover:text-warning disabled:opacity-40"><Unlink className="w-3.5 h-3.5" /></button>}
                    <button onClick={() => handleEliminar(a.id)} disabled={eliminando === a.id} title="Eliminar" className="text-muted-foreground hover:text-destructive disabled:opacity-40"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  {['Fecha', 'Comercio', 'Tipo', 'Gasto', 'Archivo', ''].map((h, i) => (
                    <th key={h || 'acc'} className={cn('py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wide', i < 3 ? 'text-left' : 'text-center')}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {filtered.map(a => (
                  <tr key={a.id} className="hover:bg-muted/50 transition-colors">
                    <td className="py-3 px-4 text-muted-foreground whitespace-nowrap tabular">{formatDate(a.fecha)}</td>
                    <td className="py-3 px-4 font-medium text-foreground">{a.comercio ?? '—'}</td>
                    <td className="py-3 px-4"><Badge variant={TIPO_VARIANTS[a.tipo] ?? 'muted'}>{TIPO_LABELS[a.tipo] ?? a.tipo}</Badge></td>
                    <td className="py-3 px-4 text-center">
                      {a.gasto_id ? (
                        <div className="inline-flex items-center gap-1.5">
                          <Badge variant="success" className="text-[10px]">Vinculado</Badge>
                          <button onClick={() => handleDesvincular(a.id)} disabled={desvinculando === a.id} className="text-muted-foreground hover:text-warning transition-colors disabled:opacity-40" title="Desvincular"><Unlink className="w-3.5 h-3.5" /></button>
                        </div>
                      ) : (
                        <button onClick={() => setVinculando(a)} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary transition-colors" title="Vincular"><Link2 className="w-3.5 h-3.5" />Vincular</button>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {a.drive_web_view_link ? (
                        <a href={a.drive_web_view_link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:opacity-80 font-medium">Ver <ExternalLink className="w-3 h-3" /></a>
                      ) : <span className="text-muted-foreground text-xs">—</span>}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <button onClick={() => handleEliminar(a.id)} disabled={eliminando === a.id} className="text-muted-foreground hover:text-destructive transition-colors disabled:opacity-40" title="Eliminar"><Trash2 className="w-3.5 h-3.5" /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {vinculando && (
        <VincularGastoModal
          archivoId={vinculando.id} comercio={vinculando.comercio} gastos={gastos}
          onClose={() => setVinculando(null)}
          onVinculado={(id, gastoId) => setArchivosState(prev => prev.map(a => a.id === id ? { ...a, gasto_id: gastoId } : a))}
        />
      )}
      {adjuntando && (
        <AdjuntarArchivoModal
          gastoId={adjuntando.id}
          comercio={adjuntando.comercio ?? adjuntando.descripcion}
          fecha={adjuntando.fecha}
          categoria={adjuntando.categoria ?? ''}
          onClose={() => setAdjuntando(null)}
          onSuccess={() => router.refresh()}
        />
      )}
    </div>
  )
}
