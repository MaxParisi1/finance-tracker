'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

interface MerchantData {
  nombre: string
  total_ars: number
  cantidad: number
}

interface Props {
  data: MerchantData[]
}

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const d: MerchantData = payload[0].payload
  return (
    <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm text-sm">
      <p className="font-medium text-gray-900 max-w-[200px] truncate">{d.nombre}</p>
      <p className="text-gray-700 font-semibold mt-1">
        {new Intl.NumberFormat('es-AR', {
          style: 'currency',
          currency: 'ARS',
          minimumFractionDigits: 0,
        }).format(d.total_ars)}
      </p>
      <p className="text-gray-400 text-xs">{d.cantidad} {d.cantidad === 1 ? 'gasto' : 'gastos'}</p>
    </div>
  )
}

export default function TopMerchantsChart({ data }: Props) {
  const truncated = data.map(d => ({
    ...d,
    label: d.nombre.length > 22 ? d.nombre.slice(0, 22) + '…' : d.nombre,
  }))

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart
        data={truncated}
        layout="vertical"
        margin={{ top: 0, right: 20, left: 0, bottom: 0 }}
      >
        <XAxis
          type="number"
          tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
          tick={{ fontSize: 11, fill: '#6b7280' }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          type="category"
          dataKey="label"
          width={150}
          tick={{ fontSize: 11, fill: '#374151' }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip content={<CustomTooltip />} />
        <Bar dataKey="total_ars" fill="#6366f1" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
