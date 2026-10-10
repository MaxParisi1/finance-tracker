'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { seccionDe } from '@/lib/nav'
import { cn } from '@/lib/utils'

/** Pestañas para moverse entre las pantallas de una misma sección. */
export default function SeccionTabs() {
  const pathname = usePathname()
  const seccion = seccionDe(pathname)
  if (!seccion || seccion.tabs.length < 2) return null

  return (
    <nav aria-label={seccion.label} className="mb-5 flex gap-1 border-b border-border overflow-x-auto">
      {seccion.tabs.map(tab => {
        const active = pathname.startsWith(tab.href)
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? 'page' : undefined}
            className={cn(
              '-mb-px px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 transition-colors',
              active
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {tab.label}
          </Link>
        )
      })}
    </nav>
  )
}
