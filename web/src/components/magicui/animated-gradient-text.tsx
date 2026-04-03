import type { ComponentPropsWithoutRef, CSSProperties } from 'react'
import { cn } from '@/lib/utils'

interface AnimatedGradientTextProps extends ComponentPropsWithoutRef<'span'> {
  speed?: number
  colorFrom?: string
  colorTo?: string
}

export function AnimatedGradientText({
  children,
  className,
  speed = 1,
  colorFrom = '#6366f1',
  colorTo = '#a855f7',
  ...props
}: AnimatedGradientTextProps) {
  return (
    <span
      style={
        {
          '--bg-size': `${speed * 300}%`,
          backgroundSize: 'var(--bg-size) 100%',
          backgroundImage: `linear-gradient(90deg, ${colorFrom}, ${colorTo}, ${colorFrom})`,
        } as CSSProperties
      }
      className={cn('animate-gradient inline bg-clip-text text-transparent', className)}
      {...props}
    >
      {children}
    </span>
  )
}
