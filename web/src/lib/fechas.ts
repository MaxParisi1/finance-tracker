/**
 * "Hoy" en hora argentina, para el código que corre en el servidor.
 *
 * Vercel corre en UTC. Con `new Date()` a secas, entre las 21:00 y la medianoche
 * de Buenos Aires el servidor ya está en el día siguiente: el último día del mes
 * el Panel mostraba el mes que todavía no había empezado.
 *
 * Los componentes de cliente no lo necesitan: ahí manda el reloj del navegador.
 */

export const ZONA = 'America/Argentina/Buenos_Aires'

/** Fecha de hoy en Buenos Aires, como YYYY-MM-DD. */
export function hoyISO(instante: Date = new Date()): string {
  // sv-SE formatea como YYYY-MM-DD.
  return instante.toLocaleDateString('sv-SE', { timeZone: ZONA })
}

/**
 * Un Date cuyos campos locales (getFullYear, getMonth, getDate, getHours) son
 * los del reloj de Buenos Aires, sea cual sea la zona del servidor.
 *
 * Sirve para aritmética de calendario. No representa el instante real: para un
 * timestamp (created_at, deleted_at) seguir usando `new Date()`.
 */
export function ahoraAR(instante: Date = new Date()): Date {
  const partes = new Intl.DateTimeFormat('en-CA', {
    timeZone: ZONA,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(instante)
  const n = (tipo: string) => Number(partes.find(p => p.type === tipo)?.value)
  return new Date(n('year'), n('month') - 1, n('day'), n('hour'), n('minute'), n('second'))
}
