'use client'

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { MEDIO_PAGO_LABELS } from '@/lib/utils'

interface PaymentData {
  medio_pago: string
  total_ars: number
  cantidad: number
}

interface Props {
  data: PaymentData[]
}

const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ef4444', '#6b7280']

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const d: PaymentData = payload[0].payload
  const total = payload[0].payload._total ?? 1
  const pct = Math.round((d.total_ars / total) * 100)
  return (
    <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm text-sm">
      <p className="font-medium text-gray-900">{MEDIO_PAGO_LABELS[d.medio_pago] ?? d.medio_pago}</p>
      <p className="text-gray-700 font-semibold mt-1">
        {new Intl.NumberFormat('es-AR', {
          style: 'currency',
          currency: 'ARS',
          minimumFractionDigits: 0,
        }).format(d.total_ars)}
      </p>
      <p className="text-gray-400 text-xs">{pct}% del total · {d.cantidad} gastos</p>
    </div>
  )
}

export default function PaymentMethodChart({ data }: Props) {
  const total = data.reduce((sum, d) => sum + d.total_ars, 0)
  const dataConTotal = data.map(d => ({ ...d, _total: total }))

  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={dataConTotal}
          cx="50%"
          cy="45%"
          innerRadius={65}
          outerRadius={95}
          paddingAngle={3}
          dataKey="total_ars"
        >
          {dataConTotal.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend
          formatter={(_, entry: any) =>
            MEDIO_PAGO_LABELS[entry.payload.medio_pago] ?? entry.payload.medio_pago
          }
          wrapperStyle={{ fontSize: 11, color: '#6b7280' }}
          iconSize={10}
          iconType="circle"
        />
      </PieChart>
    </ResponsiveContainer>
  )
}
