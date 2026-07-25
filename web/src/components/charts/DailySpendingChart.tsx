'use client'

import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
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
const fmtARS = (v: number) => new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', minimumFractionDigits: 0 }).format(v)

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload as DayData
  return (
    <div className="bg-card border border-border rounded-lg px-3 py-2 shadow-modal text-sm">
      <p className="font-medium text-foreground mb-0.5">Día {label}</p>
      <p className="text-muted-foreground">Ese día: <span className="font-semibold text-foreground tabular">{fmtARS(d.total_ars)}</span></p>
      <p className="text-muted-foreground">Acumulado: <span className="font-semibold text-primary tabular">{fmtARS(d.acumulado)}</span></p>
    </div>
  )
}

export default function DailySpendingChart({ data }: Props) {
  const conGasto = data.filter(d => d.total_ars > 0)
  const avg = conGasto.length ? conGasto.reduce((s, d) => s + d.total_ars, 0) / conGasto.length : 0

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 12, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
        <XAxis dataKey="dia" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} tickLine={false} axisLine={false} interval={4} />
        <YAxis tickFormatter={formatK} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} tickLine={false} axisLine={false} width={52} />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: 'hsl(var(--muted) / 0.5)' }} />
        {avg > 0 && (
          <ReferenceLine
            y={avg}
            stroke="hsl(var(--muted-foreground))"
            strokeDasharray="4 4"
            label={{ value: `prom ${formatK(avg)}`, position: 'insideTopRight', fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
          />
        )}
        <Bar dataKey="total_ars" radius={[3, 3, 0, 0]} maxBarSize={22}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.total_ars > avg && avg > 0 ? 'hsl(var(--primary))' : 'hsl(var(--primary) / 0.35)'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
