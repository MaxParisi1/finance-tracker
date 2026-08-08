'use client'

import { useEffect, useState } from 'react'
import { formatMontoAR, parseMontoAR } from '@/lib/montos'

interface Props {
  value: number | string | null | undefined
  onChange: (valor: number | null) => void
  className?: string
  placeholder?: string
  autoFocus?: boolean
  disabled?: boolean
  id?: string
}

/**
 * Input de dinero con convención argentina.
 *
 * Usa type="text" a propósito: type="number" parsea con reglas de EE.UU. y al
 * pegar "67.894,40" desde una factura guarda 67,89 sin que se note.
 * `inputMode="decimal"` mantiene el teclado numérico en el celular.
 *
 * Mientras escribís respeta lo que tipeás; al salir del campo lo reformatea a
 * "67.894,40" para que puedas confirmar de un vistazo que entendió bien.
 */
export default function MontoInput({
  value, onChange, className, placeholder, autoFocus, disabled, id,
}: Props) {
  const [texto, setTexto] = useState(() => formatMontoAR(parseMontoAR(value)))
  const [enfocado, setEnfocado] = useState(false)

  // Sincroniza cuando el valor cambia desde afuera, sin pisar lo que se tipea.
  useEffect(() => {
    if (enfocado) return
    const n = parseMontoAR(value)
    setTexto(n === null ? '' : formatMontoAR(n))
  }, [value, enfocado])

  return (
    <input
      id={id}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      className={className}
      placeholder={placeholder}
      autoFocus={autoFocus}
      disabled={disabled}
      value={texto}
      onFocus={e => {
        setEnfocado(true)
        e.currentTarget.select()
      }}
      onChange={e => {
        setTexto(e.target.value)
        onChange(parseMontoAR(e.target.value))
      }}
      onBlur={() => {
        setEnfocado(false)
        const n = parseMontoAR(texto)
        setTexto(n === null ? '' : formatMontoAR(n))
        onChange(n)
      }}
    />
  )
}
