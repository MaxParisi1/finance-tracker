import Sidebar from '@/components/Sidebar'
import AgendaView from '@/components/AgendaView'
import { getAgenda, getRecurrentesConCosto, getFijosDelMes } from '@/lib/queries'

export const dynamic = 'force-dynamic'

export default async function AgendaPage() {
  const hoy = new Date()
  const [obligaciones, { recurrentes }, fijos] = await Promise.all([
    getAgenda(),
    getRecurrentesConCosto(),
    getFijosDelMes(hoy.getMonth() + 1, hoy.getFullYear()),
  ])

  return (
    <div className="flex min-h-screen">
      <Sidebar pendientes={fijos.pendientes.length} />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          <div className="mb-6">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">Lo que viene</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Tu flujo de caja de las próximas semanas: fijos y cuotas por fecha
            </p>
          </div>

          <AgendaView obligaciones={obligaciones} recurrentes={recurrentes} />
        </div>
      </main>
    </div>
  )
}
