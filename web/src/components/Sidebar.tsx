'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState, useEffect } from 'react'
import { useTheme } from 'next-themes'
import {
  LayoutDashboard,
  CreditCard,
  FileText,
  BarChart3,
  RefreshCw,
  ChevronLeft,
  Sun,
  Moon,
  Layers,
  History,
  Plus,
  CalendarClock,
  ClipboardCheck,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { href: '/dashboard',    label: 'Panel',        icon: LayoutDashboard },
  { href: '/agenda',       label: 'Lo que viene', icon: CalendarClock },
  { href: '/recurrentes',  label: 'Fijos',        icon: RefreshCw, badge: true },
  { href: '/cuotas',       label: 'Cuotas',       icon: Layers },
  { href: '/gastos',       label: 'Gastos',       icon: CreditCard },
  { href: '/comprobantes', label: 'Comprobantes', icon: FileText },
  { href: '/registro',     label: 'Registro',     icon: ClipboardCheck },
  { href: '/analytics',    label: 'Analíticas',   icon: BarChart3 },
  { href: '/historico',    label: 'Histórico',    icon: History },
]

export default function Sidebar({ pendientes }: { pendientes?: number }) {
  const pathname = usePathname()
  const [collapsed, setCollapsed] = useState(false)
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  return (
    <aside
      className={cn(
        'hidden md:flex flex-col min-h-screen sticky top-0 self-start transition-[width] duration-300 ease-in-out',
        'bg-card border-r border-border',
        collapsed ? 'w-[76px]' : 'w-60',
      )}
    >
      {/* Logo */}
      <div className={cn('flex items-center h-16 border-b border-border', collapsed ? 'justify-center px-4' : 'gap-3 px-5')}>
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground font-serif text-lg leading-none">₣</div>
        {!collapsed && (
          <div className="min-w-0">
            <p className="text-sm font-semibold tracking-tight text-foreground leading-tight">Finanzas</p>
            <p className="text-[11px] text-muted-foreground leading-tight">datos en vivo</p>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV_ITEMS.map(item => {
          const active = pathname.startsWith(item.href)
          const Icon = item.icon
          const showBadge = item.badge && pendientes && pendientes > 0
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                'group relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium transition-colors',
                collapsed && 'justify-center',
                active
                  ? 'bg-secondary text-primary'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
            >
              <Icon className="flex-shrink-0 w-[18px] h-[18px]" strokeWidth={active ? 2.2 : 1.8} />
              {!collapsed && <span className="truncate">{item.label}</span>}
              {showBadge && (
                <span className={cn(
                  'ml-auto text-[11px] font-bold rounded-full bg-destructive/12 text-destructive tabular',
                  collapsed
                    ? 'absolute -top-0.5 -right-0.5 w-4 h-4 grid place-items-center'
                    : 'px-2 py-0.5',
                )}>
                  {pendientes}
                </span>
              )}
            </Link>
          )
        })}
      </nav>

      {/* Registrar gasto → abre el asistente */}
      <div className="px-3 pb-2">
        <button
          onClick={() => window.dispatchEvent(new Event('open-chat'))}
          title="Registrar gasto"
          className={cn(
            'w-full flex items-center justify-center gap-2 rounded-lg bg-primary text-primary-foreground font-medium text-[13.5px] py-2.5 transition-opacity hover:opacity-90',
          )}
        >
          <Plus className="w-4 h-4" strokeWidth={2.4} />
          {!collapsed && <span>Registrar gasto</span>}
        </button>
      </div>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-border space-y-1">
        {mounted && (
          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className={cn(
              'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-[13.5px] font-medium transition-colors',
              'text-muted-foreground hover:bg-muted hover:text-foreground',
              collapsed && 'justify-center',
            )}
            title={theme === 'dark' ? 'Modo claro' : 'Modo oscuro'}
          >
            {theme === 'dark' ? <Sun className="w-[18px] h-[18px]" /> : <Moon className="w-[18px] h-[18px]" />}
            {!collapsed && <span>Modo {theme === 'dark' ? 'claro' : 'oscuro'}</span>}
          </button>
        )}
        <div className={cn(collapsed ? 'flex justify-center' : 'flex items-center justify-between')}>
          {!collapsed && <p className="text-[11px] text-muted-foreground px-2">Datos en tiempo real</p>}
          <button
            onClick={() => setCollapsed(c => !c)}
            className="flex-shrink-0 p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title={collapsed ? 'Expandir' : 'Colapsar'}
          >
            <ChevronLeft className={cn('w-4 h-4 transition-transform duration-300', collapsed && 'rotate-180')} />
          </button>
        </div>
      </div>
    </aside>
  )
}
