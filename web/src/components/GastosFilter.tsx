'use client'

import { useRouter } from 'next/navigation'
import { MONTH_NAMES_CAP } from '@/lib/utils'

interface GastosFilterProps {
  mes: number
  anio: number
}

export default function GastosFilter({ mes, anio }: GastosFilterProps) {
  const router = useRouter()

  const currentYear = new Date().getFullYear()
  const years = [currentYear - 1, currentYear, currentYear + 1]

  function handleChange(newMes: number, newAnio: number) {
    router.push(`/gastos?mes=${newMes}&anio=${newAnio}`)
  }

  return (
    <div className="flex items-center gap-3">
      <select
        value={mes}
        onChange={e => handleChange(Number(e.target.value), anio)}
        className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
        className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
