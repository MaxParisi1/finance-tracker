'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import { Plus, MoreHorizontal, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { SECCIONES } from '@/lib/nav'
import { EVENTO_NUEVO_GASTO } from '@/components/NuevoGastoModal'

// En el celular entran cuatro lugares más el "+": lo de todos los días queda a
// mano y el resto va en "Más".
const PRIMARY = SECCIONES.filter(s => ['Panel', 'Pagos', 'Gastos'].includes(s.label))
const MORE = SECCIONES.filter(s => !PRIMARY.includes(s))

export default function BottomNav() {
  const pathname = usePathname()
  const [moreOpen, setMoreOpen] = useState(false)

  if (pathname === '/login') return null

  const activa = (s: (typeof SECCIONES)[number]) => s.tabs.some(t => pathname.startsWith(t.href))
  const moreActive = MORE.some(activa)

  return (
    <>
      {/* Sheet "Más" */}
      {moreOpen && (
        <div className="md:hidden fixed inset-0 z-40" onClick={() => setMoreOpen(false)}>
          <div className="absolute inset-0 bg-foreground/20 backdrop-blur-sm" />
          <div
            className="absolute left-2 right-2 rounded-2xl glass-nav p-2 shadow-modal"
            style={{ bottom: 'calc(env(safe-area-inset-bottom, 0px) + 5rem)' }}
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-3 py-2">
              <span className="text-sm font-semibold text-foreground">Más secciones</span>
              <button onClick={() => setMoreOpen(false)} className="p-1 text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {MORE.map(item => {
                const Icon = item.icon
                const active = activa(item)
                return (
                  <Link
                    key={item.label}
                    href={item.tabs[0].href}
                    onClick={() => setMoreOpen(false)}
                    className={cn(
                      'flex items-center gap-3 px-3 py-3 rounded-xl text-sm font-medium transition-colors',
                      active ? 'bg-secondary text-primary' : 'text-foreground hover:bg-muted',
                    )}
                  >
                    <Icon className="w-[18px] h-[18px]" />
                    {item.label}
                  </Link>
                )
              })}
            </div>
          </div>
        </div>
      )}

      <nav
        className="md:hidden fixed bottom-0 left-0 right-0 z-40"
        style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
      >
        <div className="glass-nav border-x-0 border-b-0 flex items-stretch px-1">
          {PRIMARY.slice(0, 2).map(item => {
            const Icon = item.icon
            const active = activa(item)
            return (
              <Link
                key={item.label}
                href={item.tabs[0].href}
                className="flex-1 flex flex-col items-center pt-2.5 pb-2 gap-1"
              >
                <Icon
                  className={cn('w-5 h-5 transition-colors', active ? 'text-primary' : 'text-muted-foreground')}
                  strokeWidth={active ? 2.2 : 1.8}
                />
                <span className={cn('text-[10px] leading-none font-medium', active ? 'text-primary' : 'text-muted-foreground')}>
                  {item.corto}
                </span>
              </Link>
            )
          })}

          {/* FAB — registrar gasto */}
          <div className="flex-1 flex justify-center">
            <button
              onClick={() => window.dispatchEvent(new Event(EVENTO_NUEVO_GASTO))}
              aria-label="Registrar gasto"
              className="-mt-5 w-12 h-12 rounded-full bg-primary text-primary-foreground grid place-items-center shadow-card-hover active:scale-95 transition-transform"
            >
              <Plus className="w-6 h-6" strokeWidth={2.4} />
            </button>
          </div>

          {PRIMARY.slice(2).map(item => {
            const Icon = item.icon
            const active = activa(item)
            return (
              <Link
                key={item.label}
                href={item.tabs[0].href}
                className="flex-1 flex flex-col items-center pt-2.5 pb-2 gap-1"
              >
                <Icon
                  className={cn('w-5 h-5 transition-colors', active ? 'text-primary' : 'text-muted-foreground')}
                  strokeWidth={active ? 2.2 : 1.8}
                />
                <span className={cn('text-[10px] leading-none font-medium', active ? 'text-primary' : 'text-muted-foreground')}>
                  {item.corto}
                </span>
              </Link>
            )
          })}


          <button
            onClick={() => setMoreOpen(o => !o)}
            className="flex-1 flex flex-col items-center pt-2.5 pb-2 gap-1"
          >
            <MoreHorizontal className={cn('w-5 h-5 transition-colors', moreActive || moreOpen ? 'text-primary' : 'text-muted-foreground')} />
            <span className={cn('text-[10px] leading-none font-medium', moreActive || moreOpen ? 'text-primary' : 'text-muted-foreground')}>
              Más
            </span>
          </button>
        </div>
      </nav>
    </>
  )
}
