import { loginAction } from './actions'

export default function LoginPage({
  searchParams,
}: {
  searchParams: { error?: string }
}) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-3xl mb-2">💰</div>
          <h1 className="text-xl font-semibold text-gray-900">Finance Tracker</h1>
          <p className="text-sm text-gray-500 mt-1">Ingresá tu contraseña para continuar</p>
        </div>

        <form action={loginAction} className="space-y-4">
          <input
            type="password"
            name="password"
            placeholder="Contraseña"
            autoFocus
            className="w-full border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
          />

          {searchParams.error && (
            <p className="text-sm text-red-600">Contraseña incorrecta.</p>
          )}

          <button
            type="submit"
            className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-lg px-4 py-2.5 text-sm transition-colors"
          >
            Entrar
          </button>
        </form>
      </div>
    </div>
  )
}
