'use client'

import { useEffect, useRef } from 'react'
import { useInView, useMotionValue, useSpring } from 'framer-motion'
import { cn } from '@/lib/utils'

interface NumberTickerProps {
  value: number
  startValue?: number
  direction?: 'up' | 'down'
  delay?: number
  decimalPlaces?: number
  className?: string
  formatFn?: (n: number) => string
}

export function NumberTicker({
  value,
  startValue = 0,
  direction = 'up',
  delay = 0,
  decimalPlaces = 0,
  className,
  formatFn,
}: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const motionValue = useMotionValue(direction === 'down' ? value : startValue)
  const springValue = useSpring(motionValue, { damping: 50, stiffness: 400 })
  const inView = useInView(ref, { once: true, margin: '0px' })

  useEffect(() => {
    if (!inView) return
    const timer = setTimeout(() => {
      motionValue.set(direction === 'down' ? startValue : value)
    }, delay * 1000)
    return () => clearTimeout(timer)
  }, [inView, motionValue, value, startValue, direction, delay])

  useEffect(
    () =>
      springValue.on('change', latest => {
        if (!ref.current) return
        const rounded = Number(latest.toFixed(decimalPlaces))
        ref.current.textContent = formatFn
          ? formatFn(rounded)
          : Intl.NumberFormat('es-AR', {
              minimumFractionDigits: decimalPlaces,
              maximumFractionDigits: decimalPlaces,
            }).format(rounded)
      }),
    [springValue, decimalPlaces, formatFn],
  )

  return (
    <span
      ref={ref}
      className={cn('inline-block tabular-nums', className)}
    />
  )
}
