'use client'

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { TendenciaMes } from '@/lib/types'

interface Props {
  data: TendenciaMes[]
}

function formatK(value: number) {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}k`
  return `$${value}`
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const d: TendenciaMes = payload[0].payload
  return (
    <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm text-sm">
      <p className="font-medium text-gray-900">{d.label}</p>
      <p className="text-emerald-600 font-semibold mt-1">
        {new Intl.NumberFormat('es-AR', {
          style: 'currency',
          currency: 'ARS',
          minimumFractionDigits: 0,
        }).format(d.total_ars)}
      </p>
      <p className="text-gray-400 text-xs">{d.cantidad} gastos</p>
      {d.variacion_pct !== null && (
        <p className={`text-xs mt-1 ${d.variacion_pct > 0 ? 'text-red-500' : 'text-emerald-600'}`}>
          {d.variacion_pct > 0 ? '+' : ''}{d.variacion_pct}% vs mes anterior
        </p>
      )}
    </div>
  )
}

export default function SpendingTrendChart({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 12, fill: '#6b7280' }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tickFormatter={formatK}
          tick={{ fontSize: 11, fill: '#6b7280' }}
          tickLine={false}
          axisLine={false}
          width={55}
        />
        <Tooltip content={<CustomTooltip />} />
        <Line
          type="monotone"
          dataKey="total_ars"
          stroke="#10b981"
          strokeWidth={2.5}
          dot={{ r: 4, fill: '#10b981', strokeWidth: 0 }}
          activeDot={{ r: 6 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
