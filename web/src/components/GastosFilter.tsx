'use client'

import { useRouter } from 'next/navigation'
import { MONTH_NAMES_CAP } from '@/lib/utils'
import { cn } from '@/lib/utils'

interface GastosFilterProps {
  mes: number
  anio: number
  basePath?: string
}

const selectClass = cn(
  'h-9 rounded-lg border border-input bg-background px-3 text-sm',
  'ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  'transition-colors text-foreground cursor-pointer'
)

export default function GastosFilter({ mes, anio, basePath = '/gastos' }: GastosFilterProps) {
  const router = useRouter()

  const currentYear = new Date().getFullYear()
  const years = [currentYear - 1, currentYear, currentYear + 1]

  function handleChange(newMes: number, newAnio: number) {
    router.push(`${basePath}?mes=${newMes}&anio=${newAnio}`)
  }

  return (
    <div className="flex items-center gap-2">
      <select
        value={mes}
        onChange={e => handleChange(Number(e.target.value), anio)}
        className={selectClass}
      >
        {MONTH_NAMES_CAP.map((name, i) => (
          <option key={i + 1} value={i + 1}>
            {name}
          </option>
        ))}
      </select>

      <select
        value={anio}
        onChange={e => handleChange(mes, Number(e.target.value))}
        className={selectClass}
      >
        {years.map(y => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>
    </div>
  )
}
