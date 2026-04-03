'use client'

import { useState, useMemo } from 'react'
import type { ArchivoDrive } from '@/lib/types'
import { formatDate } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { Search, X, ExternalLink } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const TIPO_LABELS: Record<string, string> = {
  factura: 'Factura',
  comprobante: 'Comprobante',
  ticket: 'Ticket',
  recibo: 'Recibo',
  resumen: 'Resumen',
}

const TIPO_VARIANTS: Record<string, 'default' | 'secondary' | 'warning' | 'muted'> = {
  factura:     'default',
  comprobante: 'secondary',
  ticket:      'warning',
  recibo:      'muted',
  resumen:     'muted',
}

const selectClass = cn(
  'h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  'transition-colors text-foreground cursor-pointer'
)

interface Props {
  archivos: ArchivoDrive[]
  categorias: string[]
}

export default function ComprobantesView({ archivos, categorias }: Props) {
  const [search, setSearch] = useState('')
  const [categoria, setCategoria] = useState('')
  const [tipo, setTipo] = useState('')

  const tipos = useMemo(
    () => Array.from(new Set(archivos.map(a => a.tipo).filter(Boolean))).sort(),
    [archivos],
  )

  const filtered = useMemo(() => {
    return archivos.filter(a => {
      if (categoria && a.categoria !== categoria) return false
      if (tipo && a.tipo !== tipo) return false
      if (search) {
        const q = search.toLowerCase()
        const com = (a.comercio ?? '').toLowerCase()
        const name = (a.drive_file_name ?? '').toLowerCase()
        if (!com.includes(q) && !name.includes(q)) return false
      }
      return true
    })
  }, [archivos, search, categoria, tipo])

  const hasFilters = search || categoria || tipo

  return (
    <div>
      {/* Filtros */}
      <div className="flex flex-wrap gap-2 mb-5">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por comercio o archivo..."
            className={cn(
              'h-9 w-56 rounded-lg border border-input bg-background pl-9 pr-8 text-sm',
              'placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors'
            )}
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <select value={categoria} onChange={e => setCategoria(e.target.value)} className={selectClass}>
          <option value="">Todas las categorías</option>
          {categorias.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        <select value={tipo} onChange={e => setTipo(e.target.value)} className={selectClass}>
          <option value="">Todos los tipos</option>
          {tipos.map(t => <option key={t} value={t}>{TIPO_LABELS[t] ?? t}</option>)}
        </select>

        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={() => { setSearch(''); setCategoria(''); setTipo('') }}>
            <X className="w-3.5 h-3.5 mr-1" />
            Limpiar
          </Button>
        )}
      </div>

      {/* Resumen */}
      <div className="flex items-center gap-3 mb-4 text-sm text-muted-foreground">
        <span>
          <span className="font-semibold text-foreground">{filtered.length}</span> archivos
          {hasFilters && archivos.length !== filtered.length && (
            <span> (de {archivos.length} total)</span>
          )}
        </span>
      </div>

      {/* Tabla */}
      <Card className="overflow-hidden">
        {filtered.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground text-sm">
            No hay comprobantes en este período.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  {['Fecha', 'Comercio', 'Tipo', 'Gasto', 'Archivo'].map((h, i) => (
                    <th
                      key={h}
                      className={cn(
                        'py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wide',
                        i < 3 ? 'text-left' : 'text-center'
                      )}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {filtered.map(a => (
                  <tr key={a.id} className="hover:bg-muted/50 transition-colors">
                    <td className="py-3 px-4 text-muted-foreground whitespace-nowrap tabular">
                      {formatDate(a.fecha)}
                    </td>
                    <td className="py-3 px-4 font-medium text-foreground">
                      {a.comercio ?? '—'}
                    </td>
                    <td className="py-3 px-4">
                      <Badge variant={TIPO_VARIANTS[a.tipo] ?? 'muted'}>
                        {TIPO_LABELS[a.tipo] ?? a.tipo}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-center">
                      {a.gasto_id ? (
                        <Badge variant="success" className="text-[10px]">Vinculado</Badge>
                      ) : (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {a.drive_web_view_link ? (
                        <a
                          href={a.drive_web_view_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary/80 font-medium transition-colors"
                        >
                          Ver
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      ) : (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
