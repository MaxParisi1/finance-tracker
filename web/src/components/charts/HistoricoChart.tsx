'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { HistoricoMes } from '@/lib/queries'
import { formatARS } from '@/lib/utils'

interface Props {
  data: HistoricoMes[]
  mesActual?: { mes: number; anio: number }
}

function formatK(value: number) {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}k`
  return `$${value}`
}

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const d: HistoricoMes = payload[0].payload
  return (
    <div className="bg-popover border border-border rounded-lg px-4 py-3 shadow-md text-sm">
      <p className="font-semibold text-foreground">{d.label}</p>
      <p className="text-indigo-500 font-bold mt-1">{formatARS(d.total_ars)}</p>
      <p className="text-muted-foreground text-xs mt-0.5">{d.cantidad} gasto{d.cantidad !== 1 ? 's' : ''}</p>
    </div>
  )
}

export default function HistoricoChart({ data, mesActual }: Props) {
  if (data.length === 0) return null

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: 8, bottom: 4 }} barCategoryGap="30%">
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: '#94a3b8' }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tickFormatter={formatK}
          tick={{ fontSize: 10, fill: '#94a3b8' }}
          tickLine={false}
          axisLine={false}
          width={52}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(99,102,241,0.06)' }} />
        <Bar dataKey="total_ars" radius={[4, 4, 0, 0]}>
          {data.map(d => {
            const isActive =
              mesActual && d.mes === mesActual.mes && d.anio === mesActual.anio
            return (
              <Cell
                key={`${d.anio}-${d.mes}`}
                fill={isActive ? '#818cf8' : '#6366f1'}
                opacity={isActive ? 1 : 0.65}
              />
            )
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
