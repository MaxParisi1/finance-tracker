'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV_ITEMS = [
  { href: '/dashboard', label: 'Dashboard', icon: '🏠' },
  { href: '/gastos', label: 'Gastos', icon: '💳' },
  { href: '/analytics', label: 'Analíticas', icon: '📊' },
  { href: '/recurrentes', label: 'Recurrentes', icon: '🔁' },
  { href: '/presupuestos', label: 'Presupuestos', icon: '🎯' },
]

export default function BottomNav() {
  const pathname = usePathname()

  if (pathname === '/login') return null

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800 flex z-40"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' } as React.CSSProperties}
    >
      {NAV_ITEMS.map(item => {
        const active = pathname.startsWith(item.href)
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex-1 flex flex-col items-center pt-2 pb-3 gap-0.5 transition-colors ${
              active ? 'text-emerald-400' : 'text-gray-500 active:text-gray-300'
            }`}
          >
            <span className="text-xl leading-none">{item.icon}</span>
            <span className="text-[9px] leading-none font-medium tracking-tight">{item.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}
