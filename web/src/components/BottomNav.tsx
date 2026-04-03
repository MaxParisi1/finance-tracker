'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { motion } from 'framer-motion'
import {
  LayoutDashboard,
  CreditCard,
  FileText,
  BarChart3,
  RefreshCw,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { href: '/dashboard',    label: 'Dashboard',   icon: LayoutDashboard, gradient: 'rgba(99,102,241,0.20)' },
  { href: '/gastos',       label: 'Gastos',       icon: CreditCard,     gradient: 'rgba(139,92,246,0.20)' },
  { href: '/comprobantes', label: 'Archivos',     icon: FileText,       gradient: 'rgba(168,85,247,0.20)' },
  { href: '/analytics',   label: 'Analíticas',   icon: BarChart3,      gradient: 'rgba(217,70,239,0.20)' },
  { href: '/recurrentes', label: 'Recurrentes',  icon: RefreshCw,      gradient: 'rgba(236,72,153,0.20)' },
]

export default function BottomNav() {
  const pathname = usePathname()

  if (pathname === '/login') return null

  const activeIndex = NAV_ITEMS.findIndex(item => pathname.startsWith(item.href))

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-40 flex justify-center"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' } as React.CSSProperties}
    >
      <div className="w-full glass-nav border-t-0 border-x-0 rounded-none relative flex items-stretch">
        {/* Animated active glow indicator */}
        {activeIndex >= 0 && (
          <motion.div
            className="absolute top-1 h-0.5 rounded-full bg-gradient-to-r from-indigo-400 to-violet-400"
            style={{ width: `${100 / NAV_ITEMS.length}%` }}
            animate={{ left: `${(activeIndex * 100) / NAV_ITEMS.length}%` }}
            transition={{ type: 'spring', stiffness: 400, damping: 35 }}
          />
        )}

        {NAV_ITEMS.map((item, index) => {
          const active = pathname.startsWith(item.href)
          const Icon = item.icon
          return (
            <Link
              key={item.href}
              href={item.href}
              className="flex-1 flex flex-col items-center pt-3 pb-2 gap-1 relative overflow-hidden group"
            >
              {/* Per-item glow on active */}
              {active && (
                <motion.div
                  layoutId="nav-glow"
                  className="absolute inset-0 pointer-events-none"
                  style={{
                    background: `radial-gradient(ellipse at center top, ${item.gradient} 0%, transparent 70%)`,
                  }}
                  transition={{ type: 'spring', stiffness: 400, damping: 35 }}
                />
              )}

              <motion.div
                animate={{ scale: active ? 1.15 : 1 }}
                whileTap={!active ? { rotateX: 180, transition: { duration: 0.25 } } : {}}
                transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                style={{ perspective: 400, transformStyle: 'preserve-3d' }}
              >
                <Icon
                  className={cn(
                    'w-5 h-5 transition-colors duration-200',
                    active
                      ? 'text-indigo-400'
                      : 'text-muted-foreground group-active:text-foreground'
                  )}
                  strokeWidth={active ? 2.2 : 1.8}
                />
              </motion.div>

              <span
                className={cn(
                  'text-[10px] leading-none font-medium transition-colors duration-200',
                  active ? 'text-indigo-400' : 'text-muted-foreground'
                )}
              >
                {item.label}
              </span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
