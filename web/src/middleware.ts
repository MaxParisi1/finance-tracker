import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const password = process.env.DASHBOARD_PASSWORD

  // Sin contraseña configurada → acceso libre (útil en dev)
  if (!password) return NextResponse.next()

  const { pathname } = request.nextUrl

  // Permitir login y archivos estáticos
  if (pathname.startsWith('/login') || pathname.startsWith('/_next') || pathname === '/favicon.ico') {
    return NextResponse.next()
  }

  const authCookie = request.cookies.get('auth')
  if (authCookie?.value === password) return NextResponse.next()

  return NextResponse.redirect(new URL('/login', request.url))
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
