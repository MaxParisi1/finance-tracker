/**
 * Parseo y formato de montos en convención argentina.
 *
 * El problema que resuelve: `<input type="number">` interpreta el valor con
 * reglas de EE.UU., así que al pegar "67.894,40" desde una factura toma el
 * punto de miles como decimal y guarda 67,89. El error es silencioso — el campo
 * muestra algo plausible — y contamina el histórico.
 *
 * Reglas (pensadas para lo que una persona pega o tipea, no para PDFs):
 *   "67.894,40"  → 67894.40   coma decimal, puntos de miles
 *   "67.894"     → 67894      un punto con 3 dígitos detrás es separador de miles
 *   "1.234.567"  → 1234567    varios puntos, todos de miles
 *   "67,5"       → 67.5       coma decimal
 *   "67.5"       → 67.5       un punto sin 3 dígitos detrás es decimal
 *   "$ 1.500,00" → 1500       se descarta el símbolo
 */

/** Convierte un texto en número, o null si no representa un monto válido. */
export function parseMontoAR(texto: string | number | null | undefined): number | null {
  if (typeof texto === 'number') return Number.isFinite(texto) ? texto : null
  if (texto == null) return null

  const limpio = String(texto).trim().replace(/[^\d.,-]/g, '')
  if (!limpio || !/\d/.test(limpio)) return null

  const negativo = limpio.startsWith('-')
  const cuerpo = limpio.replace(/-/g, '')

  let normalizado: string

  if (cuerpo.includes(',')) {
    // La coma manda: es el decimal. Todo punto es separador de miles.
    const i = cuerpo.lastIndexOf(',')
    const entero = cuerpo.slice(0, i).replace(/\./g, '') || '0'
    const decimales = cuerpo.slice(i + 1).replace(/\D/g, '')
    normalizado = `${entero}.${decimales || '0'}`
  } else if (cuerpo.includes('.')) {
    const partes = cuerpo.split('.')
    const ultima = partes[partes.length - 1]
    // Varios puntos, o uno seguido de exactamente 3 dígitos → separador de miles.
    // Con menos de 3 dígitos detrás no puede ser miles, así que es un decimal.
    const esMiles = partes.length > 2 || ultima.length === 3
    normalizado = esMiles ? partes.join('') : `${partes.slice(0, -1).join('')}.${ultima}`
  } else {
    normalizado = cuerpo
  }

  const n = parseFloat(normalizado)
  if (!Number.isFinite(n)) return null
  return negativo ? -n : n
}

/** Formatea un número con separadores argentinos: 67894.4 → "67.894,40". */
export function formatMontoAR(valor: number | null | undefined, decimales = 2): string {
  if (valor == null || !Number.isFinite(valor)) return ''
  return valor.toLocaleString('es-AR', {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  })
}
