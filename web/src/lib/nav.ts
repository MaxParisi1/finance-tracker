import {
  BarChart3, CalendarClock, CreditCard, FileText, LayoutDashboard, type LucideIcon,
} from 'lucide-react'

/**
 * Las cinco secciones de la app. Varias agrupan pantallas que antes eran
 * entradas sueltas del menú (eran nueve); adentro se cambia con pestañas.
 * Las rutas no cambiaron: los links viejos siguen andando.
 */
export interface Seccion {
  label: string
  /** Etiqueta corta para la barra inferior del celular. */
  corto: string
  icon: LucideIcon
  /** La primera pestaña es a donde lleva el menú. */
  tabs: { href: string; label: string }[]
  /** Muestra el contador de fijos sin pagar. */
  badge?: boolean
}

export const SECCIONES: Seccion[] = [
  { label: 'Panel', corto: 'Panel', icon: LayoutDashboard, tabs: [{ href: '/dashboard', label: 'Panel' }] },
  {
    label: 'Pagos', corto: 'Pagos', icon: CalendarClock, badge: true,
    tabs: [
      { href: '/agenda', label: 'Lo que viene' },
      { href: '/recurrentes', label: 'Fijos' },
      { href: '/cuotas', label: 'Cuotas' },
    ],
  },
  { label: 'Gastos', corto: 'Gastos', icon: CreditCard, tabs: [{ href: '/gastos', label: 'Gastos' }] },
  {
    label: 'Documentos', corto: 'Docs', icon: FileText,
    tabs: [
      { href: '/registro', label: 'Registro' },
      { href: '/comprobantes', label: 'Comprobantes' },
    ],
  },
  {
    label: 'Análisis', corto: 'Análisis', icon: BarChart3,
    tabs: [
      { href: '/analytics', label: 'Este mes' },
      { href: '/historico', label: 'Histórico' },
    ],
  },
]

export function seccionDe(pathname: string): Seccion | undefined {
  return SECCIONES.find(s => s.tabs.some(t => pathname.startsWith(t.href)))
}
