import React, { type ComponentPropsWithoutRef, type CSSProperties } from 'react'
import { cn } from '@/lib/utils'

export interface ShimmerButtonProps extends ComponentPropsWithoutRef<'button'> {
  shimmerColor?: string
  shimmerSize?: string
  shimmerDuration?: string
  borderRadius?: string
  background?: string
}

export const ShimmerButton = React.forwardRef<HTMLButtonElement, ShimmerButtonProps>(
  (
    {
      shimmerColor = 'rgba(255,255,255,0.5)',
      shimmerSize = '0.04em',
      shimmerDuration = '2.5s',
      borderRadius = '8px',
      background = 'linear-gradient(135deg, hsl(239,84%,55%), hsl(262,83%,50%))',
      className,
      children,
      ...props
    },
    ref,
  ) => {
    return (
      <button
        ref={ref}
        style={
          {
            '--spread': '80deg',
            '--shimmer-color': shimmerColor,
            '--radius': borderRadius,
            '--speed': shimmerDuration,
            '--cut': shimmerSize,
            '--bg': background,
          } as CSSProperties
        }
        className={cn(
          'group relative z-0 flex cursor-pointer items-center justify-center gap-1.5 overflow-hidden',
          'whitespace-nowrap border border-white/10 px-4 py-2 text-sm font-medium text-white',
          '[border-radius:var(--radius)] [background:var(--bg)]',
          'transform-gpu transition-transform duration-200 ease-in-out active:translate-y-px',
          'disabled:pointer-events-none disabled:opacity-50',
          className,
        )}
        {...props}
      >
        {/* Shimmer track */}
        <div
          className="-z-30 blur-[2px] absolute inset-0 overflow-visible"
          style={{ containerType: 'size' } as CSSProperties}
        >
          <div className="animate-shimmer-slide absolute inset-0 h-[100cqh] aspect-square rounded-none">
            <div
              className="animate-spin-around absolute -inset-full w-auto rotate-0"
              style={{
                background: `conic-gradient(from calc(270deg - (var(--spread) * 0.5)), transparent 0, var(--shimmer-color) var(--spread), transparent var(--spread))`,
              }}
            />
          </div>
        </div>

        {children}

        {/* Inner highlight */}
        <div
          className={cn(
            'absolute inset-0 size-full rounded-[inherit]',
            'shadow-[inset_0_-6px_10px_rgba(255,255,255,0.12)]',
            'transition-all duration-300',
            'group-hover:shadow-[inset_0_-6px_10px_rgba(255,255,255,0.22)]',
          )}
        />
        {/* Background cut */}
        <div
          className="absolute -z-20 [border-radius:var(--radius)] [background:var(--bg)]"
          style={{ inset: 'var(--cut)' }}
        />
      </button>
    )
  },
)
ShimmerButton.displayName = 'ShimmerButton'
