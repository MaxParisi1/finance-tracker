import { loginAction } from './actions'
import { TrendingUp } from 'lucide-react'

export default function LoginPage({
  searchParams,
}: {
  searchParams: { error?: string }
}) {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      {/* Gradient blobs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-gradient-to-br from-indigo-500/20 to-violet-500/20 blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 rounded-full bg-gradient-to-tr from-violet-500/15 to-purple-500/15 blur-3xl" />
      </div>

      <div className="relative w-full max-w-sm">
        <div className="bg-card text-card-foreground rounded-2xl shadow-modal border border-border p-8">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="inline-flex w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 items-center justify-center mb-4 shadow-glow-sm">
              <TrendingUp className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-xl font-semibold text-foreground">Finance Tracker</h1>
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
              className="w-full h-10 gradient-primary text-white font-medium rounded-lg text-sm transition-opacity hover:opacity-90 shadow-glow-sm"
            >
              Entrar
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
