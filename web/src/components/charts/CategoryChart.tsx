'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

interface CategoryData {
  categoria: string
  total_ars: number
  cantidad: number
  color?: string
}

interface Props {
  data: CategoryData[]
}

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const d: CategoryData = payload[0].payload
  return (
    <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm text-sm">
      <p className="font-medium text-gray-900">{d.categoria}</p>
      <p className="text-gray-700 font-semibold mt-1">
        {new Intl.NumberFormat('es-AR', {
          style: 'currency',
          currency: 'ARS',
          minimumFractionDigits: 0,
        }).format(d.total_ars)}
      </p>
      <p className="text-gray-400 text-xs">{d.cantidad} gastos</p>
    </div>
  )
}

export default function CategoryChart({ data }: Props) {
  const sorted = [...data].sort((a, b) => b.total_ars - a.total_ars).slice(0, 10)

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart
        data={sorted}
        layout="vertical"
        margin={{ top: 0, right: 20, left: 0, bottom: 0 }}
      >
        <XAxis
          type="number"
          tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
          tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          type="category"
          dataKey="categoria"
          width={140}
          tick={{ fontSize: 12, fill: 'hsl(var(--foreground))' }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip content={<CustomTooltip />} />
        <Bar dataKey="total_ars" radius={[0, 4, 4, 0]}>
          {sorted.map((entry, i) => (
            <Cell key={i} fill={entry.color ?? '#4f46e5'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
