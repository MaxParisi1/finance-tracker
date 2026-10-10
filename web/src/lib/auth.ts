import { cookies } from 'next/headers'

/**
 * Corta una server action si quien la llama no tiene sesión.
 *
 * El middleware protege las páginas, pero deja pasar /login, y una server
 * action se puede invocar con un POST a cualquier ruta. Sin este chequeo
 * alcanzaba con conocer el id de la acción para escribir en la base sin haber
 * entrado. Toda action exportada tiene que empezar llamando a esto.
 */
export function exigirSesion(): void {
  const password = process.env.DASHBOARD_PASSWORD
  // Mismo criterio que el middleware: sin contraseña configurada, acceso libre.
  if (!password) return
  if (cookies().get('auth')?.value !== password) {
    throw new Error('Tu sesión venció. Volvé a entrar.')
  }
}
