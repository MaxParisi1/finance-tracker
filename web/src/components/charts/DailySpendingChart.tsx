'use client'

import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

interface DayData {
  dia: number
  total_ars: number
  acumulado: number
}

interface Props {
  data: DayData[]
}

function formatK(value: number) {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}k`
  return `$${value}`
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const diario = payload.find((p: any) => p.dataKey === 'total_ars')
  const acum = payload.find((p: any) => p.dataKey === 'acumulado')

  return (
    <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm text-sm">
      <p className="font-medium text-gray-700 mb-1">Día {label}</p>
      {diario?.value > 0 && (
        <p className="text-gray-900">
          Ese día:{' '}
          <span className="font-semibold">
            {new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', minimumFractionDigits: 0 }).format(diario.value)}
          </span>
        </p>
      )}
      <p className="text-emerald-600">
        Acumulado:{' '}
        <span className="font-semibold">
          {new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', minimumFractionDigits: 0 }).format(acum?.value ?? 0)}
        </span>
      </p>
    </div>
  )
}

export default function DailySpendingChart({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
        <XAxis
          dataKey="dia"
          tick={{ fontSize: 11, fill: '#6b7280' }}
          tickLine={false}
          axisLine={false}
          interval={4}
        />
        <YAxis
          yAxisId="left"
          tickFormatter={formatK}
          tick={{ fontSize: 11, fill: '#6b7280' }}
          tickLine={false}
          axisLine={false}
          width={55}
        />
        <YAxis
          yAxisId="right"
          orientation="right"
          tickFormatter={formatK}
          tick={{ fontSize: 11, fill: '#6b7280' }}
          tickLine={false}
          axisLine={false}
          width={60}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          formatter={(value) => value === 'total_ars' ? 'Gasto diario' : 'Acumulado'}
          wrapperStyle={{ fontSize: 12, color: '#6b7280' }}
        />
        <Bar yAxisId="left" dataKey="total_ars" fill="#d1fae5" radius={[3, 3, 0, 0]} maxBarSize={20} />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="acumulado"
          stroke="#10b981"
          strokeWidth={2}
          dot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
