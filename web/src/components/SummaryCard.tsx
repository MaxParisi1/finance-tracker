'use client'

import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'

interface SummaryCardProps {
  title: string
  value: string
  subtitle?: string
  trend?: number | null
  icon?: string
}

export default function SummaryCard({ title, value, subtitle, trend, icon }: SummaryCardProps) {
  const isUp   = trend !== null && trend !== undefined && trend > 0
  const isDown = trend !== null && trend !== undefined && trend < 0
  const isFlat = trend !== null && trend !== undefined && trend === 0

  return (
    <Card className="relative overflow-hidden transition-shadow duration-200 hover:shadow-card-hover">
      {/* Subtle gradient accent top border */}
      <div className="absolute top-0 left-0 right-0 h-0.5 gradient-primary opacity-60" />

      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium text-muted-foreground leading-none">{title}</p>
          {icon && (
            <span className="text-base flex-shrink-0 opacity-70">{icon}</span>
          )}
        </div>

        <p className={cn(
          'text-2xl font-bold tracking-tight mt-3 tabular',
          'text-foreground'
        )}>
          {value}
        </p>

        <div className="mt-2.5 flex items-center gap-2 min-h-[20px]">
          {trend !== null && trend !== undefined && (
            <span
              className={cn(
                'inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-full',
                isUp   && 'bg-destructive/10 text-destructive',
                isDown && 'bg-success/10 text-success',
                isFlat && 'bg-muted text-muted-foreground'
              )}
            >
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
    </Card>
  )
}
