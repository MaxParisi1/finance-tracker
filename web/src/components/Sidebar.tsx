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
  TrendingUp,
  ChevronLeft,
  Sun,
  Moon,
  Layers,
  History,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { AnimatedGradientText } from '@/components/magicui/animated-gradient-text'

const NAV_ITEMS = [
  { href: '/dashboard',    label: 'Dashboard',    icon: LayoutDashboard, gradient: 'from-blue-500 to-indigo-600' },
  { href: '/gastos',       label: 'Gastos',        icon: CreditCard,      gradient: 'from-indigo-500 to-violet-600' },
  { href: '/comprobantes', label: 'Comprobantes',  icon: FileText,        gradient: 'from-violet-500 to-purple-600' },
  { href: '/analytics',   label: 'Analíticas',    icon: BarChart3,       gradient: 'from-purple-500 to-pink-600' },
  { href: '/recurrentes', label: 'Recurrentes',   icon: RefreshCw,       gradient: 'from-pink-500 to-rose-600' },
  { href: '/cuotas',      label: 'Cuotas',         icon: Layers,          gradient: 'from-rose-500 to-orange-500' },
  { href: '/historico',  label: 'Histórico',      icon: History,         gradient: 'from-orange-500 to-amber-500' },
]

export default function Sidebar() {
  const pathname = usePathname()
  const [collapsed, setCollapsed] = useState(false)
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  return (
    <aside
      className={cn(
        'hidden md:flex flex-col min-h-screen transition-all duration-300 ease-in-out',
        'bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900',
        'border-r border-slate-700/50',
        collapsed ? 'w-[72px]' : 'w-56'
      )}
    >
      {/* Logo */}
      <div className={cn(
        'flex items-center border-b border-slate-700/50 transition-all duration-300',
        collapsed ? 'justify-center px-4 py-5' : 'gap-3 px-5 py-5'
      )}>
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-glow-sm">
          <TrendingUp className="w-4 h-4 text-white" />
        </div>
        {!collapsed && (
          <AnimatedGradientText
            className="font-semibold text-sm tracking-tight truncate"
            colorFrom="#a5b4fc"
            colorTo="#e879f9"
            speed={0.6}
          >
            Finance Tracker
          </AnimatedGradientText>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map(item => {
          const active = pathname.startsWith(item.href)
          const Icon = item.icon
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                'group relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200',
                collapsed ? 'justify-center' : '',
                active
                  ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg shadow-indigo-500/25'
                  : 'text-slate-400 hover:bg-slate-700/60 hover:text-white'
              )}
            >
              {/* Glow effect on hover */}
              {!active && (
                <span
                  className={cn(
                    'absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300',
                    `bg-gradient-to-r ${item.gradient} opacity-0 group-hover:opacity-10`
                  )}
                />
              )}
              <Icon
                className={cn(
                  'flex-shrink-0 w-[18px] h-[18px] transition-colors',
                  active ? 'text-white' : 'text-slate-400 group-hover:text-white'
                )}
              />
              {!collapsed && (
                <>
                  <span className="truncate">{item.label}</span>
                  {active && (
                    <span className="ml-auto w-1.5 h-1.5 rounded-full bg-white/80" />
                  )}
                </>
              )}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className={cn(
        'px-3 py-4 border-t border-slate-700/50 space-y-2',
      )}>
        {/* Dark mode toggle */}
        {mounted && (
          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className={cn(
              'w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-200',
              'text-slate-400 hover:bg-slate-700/60 hover:text-white',
              collapsed ? 'justify-center' : ''
            )}
            title={theme === 'dark' ? 'Modo claro' : 'Modo oscuro'}
          >
            {theme === 'dark' ? (
              <Sun className="flex-shrink-0 w-[18px] h-[18px]" />
            ) : (
              <Moon className="flex-shrink-0 w-[18px] h-[18px]" />
            )}
            {!collapsed && <span>Modo {theme === 'dark' ? 'claro' : 'oscuro'}</span>}
          </button>
        )}

        {/* Collapse toggle */}
        <div className={cn(collapsed ? 'flex justify-center' : 'flex items-center justify-between')}>
          {!collapsed && (
            <p className="text-xs text-slate-600 px-2">Datos en tiempo real</p>
          )}
          <button
            onClick={() => setCollapsed(c => !c)}
            className="flex-shrink-0 p-1.5 rounded-lg hover:bg-slate-700/60 text-slate-500 hover:text-slate-300 transition-colors"
            title={collapsed ? 'Expandir' : 'Colapsar'}
          >
            <ChevronLeft
              className={cn('w-4 h-4 transition-transform duration-300', collapsed && 'rotate-180')}
            />
          </button>
        </div>
      </div>
    </aside>
  )
}
