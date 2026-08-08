/**
 * Plantilla del mail de comprobante de expensas al consorcio.
 *
 * Reproduce el que venís mandando desde Thunderbird. Lo único variable es el
 * mes; el asunto no lo lleva, así que no se toca.
 *
 * Regla del mes: las expensas se pagan al mes siguiente del período — en agosto
 * se paga julio. El mes sale del VENCIMIENTO de la factura menos uno, no de la
 * fecha de hoy: así el texto queda bien aunque generes el borrador tarde o
 * adelantado.
 */

const MESES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]

export const ASUNTO =
  'Comprobante de Pago de Expensas - Departamento 3D Cons.Prop. Gallo 1636/58'

/** Mes del período liquidado a partir del vencimiento ('2026-08-10' → 'Julio'). */
export function mesDelPeriodo(vencimiento: string): string {
  const m = /^(\d{4})-(\d{2})-\d{2}/.exec(vencimiento)
  if (!m) throw new Error(`Vencimiento inválido: ${vencimiento}`)
  // El mes del período es el anterior al del vencimiento; enero cae a diciembre.
  const indiceVto = Number(m[2]) - 1
  return MESES[(indiceVto + 11) % 12]
}

/** Saludo según la hora en que se genera el borrador. Es editable antes de enviar. */
export function saludo(hora: number): string {
  if (hora < 13) return 'Buenos días'
  if (hora < 20) return 'Buenas tardes'
  return 'Buenas noches'
}

export function cuerpo(vencimiento: string, ahora = new Date()): string {
  return [
    `${saludo(ahora.getHours())},`,
    '',
    'Les adjunto comprobante de pago correspondiente a las expensas del mes',
    `de ${mesDelPeriodo(vencimiento)} del Consorcio Gallo 1636/58.`,
    '',
    'Saludos cordiales,',
    'Máximo Parisi',
    'Departamento: 3D',
    'Unidad Funcional: 255',
    '',
  ].join('\n')
}
