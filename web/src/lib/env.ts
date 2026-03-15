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
} as const
