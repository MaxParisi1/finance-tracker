'use client'

import Link from 'next/link'
import { FileText, Receipt, CircleDashed, Clock } from 'lucide-react'
import type { Registro, CeldaRegistro } from '@/lib/queries'
import { cn } from '@/lib/utils'

const MESES_CORTOS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                      'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

function fmt(n: number) {
  return n.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** Una celda: dos puntitos (factura / comprobante) sobre el estado de pago. */
function Celda({ celda }: { celda: CeldaRegistro | undefined }) {
  if (!celda) {
    return (
      <td className="px-2 py-2 text-center">
        <span className="inline-block w-2 h-2 rounded-full bg-muted" title="Sin factura registrada" />
      </td>
    )
  }

  const completa = celda.estado === 'pagada' && celda.con_factura && celda.con_comprobante
  const faltan = [
    !celda.con_factura && 'la factura',
    !celda.con_comprobante && 'el comprobante',
    celda.estado !== 'pagada' && 'el pago',
  ].filter(Boolean)

  const titulo =
    `$${fmt(celda.monto)} · vence ${celda.vencimiento}` +
    (faltan.length ? ` · falta ${faltan.join(' y ')}` : ' · completo')

  const Punto = ({ ok, link, label }: { ok: boolean; link: string | null; label: string }) => {
    const clase = cn(
      'inline-flex items-center justify-center w-4 h-4 rounded-[3px] transition-colors',
      ok ? 'text-success' : 'text-muted-foreground/35',
    )
    const icono = label === 'factura'
      ? <FileText className="w-3.5 h-3.5" />
      : <Receipt className="w-3.5 h-3.5" />
    return ok && link
      ? <a href={link} target="_blank" rel="noreferrer" className={cn(clase, 'hover:text-primary')}>{icono}</a>
      : <span className={clase}>{icono}</span>
  }

  return (
    <td className="px-2 py-2">
      <div
        title={titulo}
        className={cn(
          'flex items-center justify-center gap-0.5 rounded-md py-1 px-1.5 border',
          completa
            ? 'border-success/30 bg-success/5'
            : celda.estado === 'pagada'
            ? 'border-warning/30 bg-warning/5'
            : 'border-border bg-muted/30',
        )}
      >
        <Punto ok={celda.con_factura} link={celda.link_factura} label="factura" />
        <Punto ok={celda.con_comprobante} link={celda.link_comprobante} label="comprobante" />
        {celda.estado !== 'pagada' && (
          <Clock className="w-3 h-3 text-warning ml-0.5" aria-label="impaga" />
        )}
      </div>
    </td>
  )
}

export default function RegistroView({ registro }: { registro: Registro }) {
  const { meses, filas, celdas_completas, total_celdas, pct_completo } = registro
  const huecos = total_celdas - celdas_completas

  return (
    <div className="space-y-5">
      {/* Resumen */}
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <div>
            <p className="text-2xl font-semibold tabular-nums">{pct_completo}%</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {celdas_completas} de {total_celdas} con factura, pago y comprobante
            </p>
          </div>
          {huecos > 0 && (
            <p className="text-sm text-warning">
              {huecos} {huecos === 1 ? 'período incompleto' : 'períodos incompletos'}
            </p>
          )}
        </div>
        <div className="mt-3 h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-success transition-all duration-500"
            style={{ width: `${pct_completo}%` }}
          />
        </div>
      </div>

      {/* Grilla */}
      <div className="rounded-xl border border-border bg-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left font-medium text-muted-foreground px-4 py-2.5 sticky left-0 bg-card">
                Servicio
              </th>
              {meses.map(m => (
                <th key={m} className="font-medium text-muted-foreground px-2 py-2.5 text-center text-xs">
                  {MESES_CORTOS[Number(m.slice(5, 7)) - 1]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map(fila => (
              <tr key={fila.servicio_id} className="border-b border-border/50 last:border-0">
                <td className="px-4 py-2 font-medium sticky left-0 bg-card whitespace-nowrap">
                  {fila.nombre}
                  <span className="ml-2 text-xs font-normal text-muted-foreground tabular-nums">
                    {fila.completas}/{fila.esperadas}
                  </span>
                </td>
                {meses.map(m => <Celda key={m} celda={fila.celdas[m]} />)}
              </tr>
            ))}
          </tbody>
        </table>

        {filas.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-muted-foreground">
            No hay servicios configurados.
          </p>
        )}
      </div>

      {/* Referencias */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground px-1">
        <span className="flex items-center gap-1.5">
          <FileText className="w-3.5 h-3.5 text-success" /> factura archivada
        </span>
        <span className="flex items-center gap-1.5">
          <Receipt className="w-3.5 h-3.5 text-success" /> comprobante archivado
        </span>
        <span className="flex items-center gap-1.5">
          <Clock className="w-3 h-3 text-warning" /> impaga
        </span>
        <span className="flex items-center gap-1.5">
          <CircleDashed className="w-3.5 h-3.5" /> sin factura ese mes
        </span>
        <span className="text-muted-foreground/70">Los íconos en verde abren el PDF en Drive.</span>
      </div>
    </div>
  )
}
