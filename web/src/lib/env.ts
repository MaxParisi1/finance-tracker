/**
 * Valida que todas las variables de entorno requeridas estén presentes.
 * Se importa en los módulos de servidor para fallar rápido en lugar de
 * generar errores crípticos en el primer request.
 *
 * Uso: import '@/lib/env'
 */

const REQUIRED_VARS = [
  'SUPABASE_URL',
  'SUPABASE_SERVICE_ROLE_KEY',
  'GOOGLE_API_KEY',
] as const

const missing = REQUIRED_VARS.filter(v => !process.env[v])

if (missing.length > 0) {
  throw new Error(
    `[env] Faltan variables de entorno obligatorias: ${missing.join(', ')}\n` +
    `Verificá tu archivo .env.local`,
  )
}

export const env = {
  SUPABASE_URL: process.env.SUPABASE_URL!,
  SUPABASE_SERVICE_ROLE_KEY: process.env.SUPABASE_SERVICE_ROLE_KEY!,
  GOOGLE_API_KEY: process.env.GOOGLE_API_KEY!,
  DASHBOARD_PASSWORD: process.env.DASHBOARD_PASSWORD,

  // Borrador de expensas al consorcio. Opcionales a propósito: si faltan, el
  // botón queda deshabilitado con un mensaje, pero el resto del sitio anda.
  // Una integración sin configurar no puede tirar abajo la app entera.
  OUTLOOK_EMAIL: process.env.OUTLOOK_EMAIL,
  OUTLOOK_APP_PASSWORD: process.env.OUTLOOK_APP_PASSWORD,
  OUTLOOK_IMAP_HOST: process.env.OUTLOOK_IMAP_HOST ?? 'outlook.office365.com',
  CONSORCIO_EMAIL: process.env.CONSORCIO_EMAIL,
  CONSORCIO_BCC: process.env.CONSORCIO_BCC,
} as const

/** True si están todas las variables para poder generar el borrador. */
export function borradorConsorcioConfigurado(): boolean {
  return Boolean(
    env.OUTLOOK_EMAIL && env.OUTLOOK_APP_PASSWORD && env.CONSORCIO_EMAIL,
  )
}
