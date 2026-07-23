import { loginAction } from './actions'
import { TrendingUp } from 'lucide-react'

export default function LoginPage({
  searchParams,
}: {
  searchParams: { error?: string }
}) {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      {/* Halo sutil de acento */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/3 w-[38rem] h-[38rem] rounded-full bg-primary/8 blur-3xl" />
      </div>

      <div className="relative w-full max-w-sm">
        <div className="bg-card text-card-foreground rounded-2xl shadow-modal border border-border p-8">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="inline-flex w-12 h-12 rounded-xl bg-primary items-center justify-center mb-4">
              <TrendingUp className="w-6 h-6 text-primary-foreground" />
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground">Finance Tracker</h1>
            <p className="text-sm text-muted-foreground mt-1">Ingresá tu contraseña para continuar</p>
          </div>

          <form action={loginAction} className="space-y-4">
            <input
              type="password"
              name="password"
              placeholder="Contraseña"
              autoFocus
              className="w-full h-10 rounded-lg border border-input bg-background px-4 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors"
            />

            {searchParams.error && (
              <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">
                Contraseña incorrecta.
              </p>
            )}

            <button
              type="submit"
              className="w-full h-10 bg-primary text-primary-foreground font-medium rounded-lg text-sm transition-opacity hover:opacity-90"
            >
              Entrar
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
