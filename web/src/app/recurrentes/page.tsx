import Sidebar from '@/components/Sidebar'
import RecurrentesView from '@/components/RecurrentesView'
import { getRecurrentesConCosto, getCategorias } from '@/lib/queries'

export const dynamic = 'force-dynamic'

export default async function RecurrentesPage() {
  const [{ recurrentes, total_mensual_ars, total_anual_ars, tc_blue, tc_fecha, tc_es_hoy }, categorias] = await Promise.all([
    getRecurrentesConCosto(),
    getCategorias(),
  ])

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-gray-900">Gastos recurrentes</h1>
            <p className="text-gray-500 text-sm mt-1">
              Suscripciones, servicios y pagos periódicos · hacé click en uno para editarlo
            </p>
          </div>

          <RecurrentesView
            recurrentes={recurrentes}
            total_mensual_ars={total_mensual_ars}
            total_anual_ars={total_anual_ars}
            tc_blue={tc_blue}
            tc_fecha={tc_fecha}
            tc_es_hoy={tc_es_hoy}
            categorias={categorias.map(c => c.nombre)}
          />
        </div>
      </main>
    </div>
  )
}
