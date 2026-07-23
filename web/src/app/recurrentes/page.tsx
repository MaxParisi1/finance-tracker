import Sidebar from '@/components/Sidebar'
import RecurrentesView from '@/components/RecurrentesView'
import { getRecurrentesConCosto, getCategorias, getFijosDelMes } from '@/lib/queries'

export const dynamic = 'force-dynamic'

export default async function RecurrentesPage() {
  const hoy = new Date()
  const mes = hoy.getMonth() + 1
  const anio = hoy.getFullYear()

  const [{ recurrentes, total_mensual_ars, total_anual_ars, tc_blue, tc_fecha, tc_es_hoy }, categorias, fijos] =
    await Promise.all([
      getRecurrentesConCosto(),
      getCategorias(),
      getFijosDelMes(mes, anio),
    ])

  return (
    <div className="flex min-h-screen">
      <Sidebar pendientes={fijos.pendientes.length} />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-4xl mx-auto">
          <div className="mb-6">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">Fijos</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Pagá tus recurrentes, adjuntá el comprobante y llevá el control del mes
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
            fijos={fijos}
          />
        </div>
      </main>
    </div>
  )
}
