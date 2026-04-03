import { type CSSProperties } from 'react'
import { cn } from '@/lib/utils'

interface BorderBeamProps {
  className?: string
  size?: number
  duration?: number
  delay?: number
  colorFrom?: string
  colorTo?: string
  borderWidth?: number
}

export function BorderBeam({
  className,
  size = 60,
  duration = 5,
  delay = 0,
  colorFrom = '#6366f1',
  colorTo = '#8b5cf6',
  borderWidth = 1.5,
}: BorderBeamProps) {
  return (
    <div
      className={cn(
        'pointer-events-none absolute inset-0 rounded-[inherit]',
        '[border:var(--beam-border-width)_solid_transparent]',
        '[mask-clip:padding-box,border-box] [mask-composite:intersect]',
        '[mask-image:linear-gradient(transparent,transparent),linear-gradient(#000,#000)]',
        className,
      )}
      style={
        {
          '--beam-border-width': `${borderWidth}px`,
          '--beam-size': `${size}px`,
          '--beam-duration': `${duration}s`,
          '--beam-delay': `${delay}s`,
          '--beam-from': colorFrom,
          '--beam-to': colorTo,
        } as CSSProperties
      }
    >
      <div
        className="absolute aspect-square animate-border-beam"
        style={
          {
            width: 'var(--beam-size)',
            offsetPath: 'rect(0 auto auto 0 round 12px)',
            background: `linear-gradient(to left, var(--beam-from), var(--beam-to), transparent)`,
            animationDuration: 'var(--beam-duration)',
            animationDelay: 'calc(-1 * var(--beam-delay))',
          } as CSSProperties
        }
      />
    </div>
  )
}
