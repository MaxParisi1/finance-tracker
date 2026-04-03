'use client'

import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { CardContent } from '@/components/ui/card'
import { MagicCard } from '@/components/magicui/magic-card'
import { NumberTicker } from '@/components/magicui/number-ticker'

type FormatType = 'ars' | 'usd' | 'count'

function applyFormat(n: number, format: FormatType): string {
  if (format === 'ars') {
    return new Intl.NumberFormat('es-AR', {
      style: 'currency',
      currency: 'ARS',
      maximumFractionDigits: 0,
    }).format(n)
  }
  if (format === 'usd') return `USD ${n.toLocaleString('es-AR')}`
  return String(n)
}

function MiniSparkline({ data }: { data: number[] }) {
  if (data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const w = 64, h = 24
  const points = data
    .map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`)
    .join(' ')
  return (
    <svg width={w} height={h} className="opacity-60" aria-hidden>
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-primary"
      />
    </svg>
  )
}

interface AnimatedSummaryCardProps {
  title: string
  value: string
  numericValue?: number
  format?: FormatType
  subtitle?: string
  trend?: number | null
  icon?: string
  sparklineData?: number[]
}

export default function AnimatedSummaryCard({
  title,
  value,
  numericValue,
  format,
  subtitle,
  trend,
  icon,
  sparklineData,
}: AnimatedSummaryCardProps) {
  const isUp   = trend != null && trend > 0
  const isDown = trend != null && trend < 0
  const isFlat = trend != null && trend === 0

  return (
    <MagicCard className="relative overflow-hidden transition-shadow duration-200 hover:shadow-card-hover">
      {/* Accent top line */}
      <div className="absolute top-0 left-0 right-0 h-0.5 gradient-primary opacity-60 z-30" />

      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium text-muted-foreground leading-none">{title}</p>
          <div className="flex items-center gap-2 flex-shrink-0">
            {sparklineData && sparklineData.length >= 2 && (
              <MiniSparkline data={sparklineData} />
            )}
            {icon && <span className="text-base opacity-70">{icon}</span>}
          </div>
        </div>

        <p className="text-2xl font-bold tracking-tight mt-3 text-foreground">
          {numericValue !== undefined && format ? (
            <NumberTicker
              value={numericValue}
              formatFn={n => applyFormat(n, format)}
              className="text-foreground"
            />
          ) : (
            <span className="tabular">{value}</span>
          )}
        </p>

        <div className="mt-2.5 flex items-center gap-2 min-h-[20px]">
          {trend != null && (
            <span className={cn(
              'inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-full',
              isUp   && 'bg-destructive/10 text-destructive',
              isDown && 'bg-success/10 text-success',
              isFlat && 'bg-muted text-muted-foreground',
            )}>
              {isUp   && <ArrowUpRight className="w-3 h-3" />}
              {isDown && <ArrowDownRight className="w-3 h-3" />}
              {isFlat && <Minus className="w-3 h-3" />}
              {trend > 0 ? '+' : ''}{trend}%
            </span>
          )}
          {subtitle && (
            <p className="text-xs text-muted-foreground truncate">{subtitle}</p>
          )}
        </div>
      </CardContent>
    </MagicCard>
  )
}
