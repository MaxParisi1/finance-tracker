import Sidebar from '@/components/Sidebar'
import GastosFilter from '@/components/GastosFilter'
import PresupuestosView from '@/components/PresupuestosView'
import { getPresupuestosConGasto, getCategorias } from '@/lib/queries'
import { monthLabel } from '@/lib/utils'

export const dynamic = 'force-dynamic'

export default async function PresupuestosPage({
  searchParams,
}: {
  searchParams: { mes?: string; anio?: string }
}) {
  const hoy = new Date()
  const mes = searchParams.mes ? parseInt(searchParams.mes) : hoy.getMonth() + 1
  const anio = searchParams.anio ? parseInt(searchParams.anio) : hoy.getFullYear()

  const [presupuestos, categorias] = await Promise.all([
    getPresupuestosConGasto(mes, anio),
    getCategorias(),
  ])

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-start justify-between mb-8">
            <div>
              <h1 className="text-2xl font-bold text-foreground">Presupuestos</h1>
              <p className="text-muted-foreground text-sm mt-1">
                {monthLabel(mes, anio)} · límites de gasto por categoría
              </p>
            </div>
            <GastosFilter mes={mes} anio={anio} />
          </div>

          <PresupuestosView
            presupuestos={presupuestos}
            categorias={categorias.map(c => c.nombre)}
            mes={mes}
            anio={anio}
          />
        </div>
      </main>
    </div>
  )
}
