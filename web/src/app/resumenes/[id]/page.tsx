import { notFound } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import SeccionTabs from '@/components/SeccionTabs'
import ConciliacionView from '@/components/ConciliacionView'
import { getCategorias, getFijosDelMes, getRecurrentes, getResumenTarjeta } from '@/lib/queries'
import { ahoraAR } from '@/lib/fechas'

export const dynamic = 'force-dynamic'

export default async function ResumenPage({ params }: { params: { id: string } }) {
  if (!/^[0-9a-f-]{36}$/i.test(params.id)) notFound()
  const hoy = ahoraAR()
  const [datos, categorias, recurrentes, fijos] = await Promise.all([
    getResumenTarjeta(params.id),
    getCategorias(),
    getRecurrentes(),
    getFijosDelMes(hoy.getMonth() + 1, hoy.getFullYear()),
  ])
  if (!datos) notFound()

  return (
    <div className="flex min-h-screen">
      <Sidebar pendientes={fijos.pendientes.length} />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          <SeccionTabs />
          <ConciliacionView
            resumen={datos.resumen}
            movimientos={datos.movimientos}
            categorias={categorias.map(c => c.nombre)}
            recurrentes={recurrentes
              .filter(r => r.activo)
              .map(r => ({ id: r.id, descripcion: r.descripcion, categoria: r.categoria }))}
          />
        </div>
      </main>
    </div>
  )
}
