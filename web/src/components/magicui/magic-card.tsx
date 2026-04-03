'use client'

import React, { useCallback, useRef, useState } from 'react'
import { motion, useMotionTemplate, useMotionValue } from 'framer-motion'
import { cn } from '@/lib/utils'

interface MagicCardProps extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode
  className?: string
  gradientSize?: number
  gradientColor?: string
  gradientFrom?: string
  gradientTo?: string
}

export function MagicCard({
  children,
  className,
  gradientSize = 220,
  gradientColor = 'rgba(99,102,241,0.10)',
  gradientFrom = '#6366f1',
  gradientTo = '#8b5cf6',
  ...props
}: MagicCardProps) {
  const mouseX = useMotionValue(-400)
  const mouseY = useMotionValue(-400)
  const [hovered, setHovered] = useState(false)

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect()
      mouseX.set(e.clientX - rect.left)
      mouseY.set(e.clientY - rect.top)
    },
    [mouseX, mouseY],
  )

  const borderBackground = useMotionTemplate`
    linear-gradient(hsl(var(--card)) 0 0) padding-box,
    radial-gradient(${gradientSize}px circle at ${mouseX}px ${mouseY}px,
      ${gradientFrom},
      ${gradientTo},
      hsl(var(--border)) 100%
    ) border-box
  `

  const spotlight = useMotionTemplate`
    radial-gradient(${gradientSize}px circle at ${mouseX}px ${mouseY}px,
      ${gradientColor},
      transparent 100%
    )
  `

  return (
    <motion.div
      className={cn(
        'group relative overflow-hidden rounded-xl border border-transparent bg-card',
        className,
      )}
      style={hovered ? { background: borderBackground as any } : undefined}
      onPointerMove={handlePointerMove}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => {
        setHovered(false)
        mouseX.set(-400)
        mouseY.set(-400)
      }}
      {...(props as any)}
    >
      {/* Spotlight overlay */}
      {hovered && (
        <motion.div
          className="pointer-events-none absolute inset-0 z-10 rounded-[inherit]"
          style={{ background: spotlight as any }}
        />
      )}
      <div className="relative z-20">{children}</div>
    </motion.div>
  )
}
