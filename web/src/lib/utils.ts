import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const MONTH_NAMES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]

export const MONTH_NAMES_CAP = MONTH_NAMES.map(
  m => m.charAt(0).toUpperCase() + m.slice(1),
)

export const MEDIO_PAGO_LABELS: Record<string, string> = {
  credito_ars: 'Crédito ARS',
  credito_usd: 'Crédito USD',
  debito: 'Débito',
  efectivo_ars: 'Efectivo ARS',
  efectivo_usd: 'Efectivo USD',
  transferencia: 'Transferencia',
}

export function formatARS(amount: number): string {
  return new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

export function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split('-')
  return `${day}/${month}/${year}`
}

export function monthLabel(mes: number, anio: number): string {
  return `${MONTH_NAMES_CAP[mes - 1]} ${anio}`
}
