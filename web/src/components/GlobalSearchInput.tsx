'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

interface Props {
  defaultValue?: string
}

export default function GlobalSearchInput({ defaultValue = '' }: Props) {
  const router = useRouter()
  const [value, setValue] = useState(defaultValue)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const q = value.trim()
    if (q) {
      router.push(`/gastos?q=${encodeURIComponent(q)}`)
    } else {
      router.push('/gastos')
    }
  }

  function handleClear() {
    setValue('')
    router.push('/gastos')
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <div className="relative">
        <input
          type="text"
          value={value}
          onChange={e => setValue(e.target.value)}
          placeholder="Buscar en todos los gastos..."
          className="border border-gray-300 rounded-lg pl-8 pr-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500 w-64"
        />
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fillRule="evenodd" d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z" clipRule="evenodd" />
        </svg>
      </div>
      {defaultValue && (
        <button
          type="button"
          onClick={handleClear}
          className="text-sm text-gray-400 hover:text-gray-600 px-2"
        >
          ✕ Limpiar
        </button>
      )}
    </form>
  )
}
