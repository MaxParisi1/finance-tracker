import Sidebar from '@/components/Sidebar'
import ComprobantesView from '@/components/ComprobantesView'
import GastosFilter from '@/components/GastosFilter'
import { getArchivosDrive, getCategorias } from '@/lib/queries'
import { monthLabel } from '@/lib/utils'

export const dynamic = 'force-dynamic'

export default async function ComprobantesPage({
  searchParams,
}: {
  searchParams: { mes?: string; anio?: string }
}) {
  const hoy = new Date()
  const mes = searchParams.mes ? parseInt(searchParams.mes) : hoy.getMonth() + 1
  const anio = searchParams.anio ? parseInt(searchParams.anio) : hoy.getFullYear()

  const [archivos, categorias] = await Promise.all([
    getArchivosDrive({ mes, anio }),
    getCategorias(),
  ])

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          {/* Header */}
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-foreground">Comprobantes</h1>
              <p className="text-muted-foreground text-sm mt-1">
                {monthLabel(mes, anio)} · {archivos.length} archivos en Drive
              </p>
            </div>
            <GastosFilter mes={mes} anio={anio} />
          </div>

          <ComprobantesView
            archivos={archivos}
            categorias={['Servicios', 'Salud', 'Impuestos', 'Otros', ...categorias.map(c => c.nombre)].filter(
              (v, i, arr) => arr.indexOf(v) === i,
            )}
          />
        </div>
      </main>
    </div>
  )
}
