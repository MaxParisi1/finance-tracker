import Sidebar from '@/components/Sidebar'
import GastosFilter from '@/components/GastosFilter'
import GastosTableView from '@/components/GastosTableView'
import GlobalSearchInput from '@/components/GlobalSearchInput'
import { getGastosMes, searchGastos, getCategorias } from '@/lib/queries'
import { formatARS, monthLabel } from '@/lib/utils'

export const dynamic = 'force-dynamic'

export default async function GastosPage({
  searchParams,
}: {
  searchParams: { mes?: string; anio?: string; q?: string }
}) {
  const hoy = new Date()
  const q = searchParams.q?.trim() ?? ''
  const isSearching = q.length > 0

  const mes = searchParams.mes ? parseInt(searchParams.mes) : hoy.getMonth() + 1
  const anio = searchParams.anio ? parseInt(searchParams.anio) : hoy.getFullYear()

  const [gastos, categorias] = await Promise.all([
    isSearching ? searchGastos(q) : getGastosMes(mes, anio),
    getCategorias(),
  ])

  const totalARS = gastos.reduce((sum, g) => sum + (g.monto_ars ?? 0), 0)

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          {/* Header */}
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Gastos</h1>
              <p className="text-gray-500 text-sm mt-1">
                {isSearching
                  ? `Resultados para "${q}" · ${gastos.length} registros · ${formatARS(totalARS)}`
                  : `${monthLabel(mes, anio)} · ${gastos.length} registros · ${formatARS(totalARS)}`}
              </p>
            </div>
            <div className="flex items-center gap-3 flex-wrap justify-end">
              <GlobalSearchInput defaultValue={q} />
              {!isSearching && <GastosFilter mes={mes} anio={anio} />}
            </div>
          </div>

          {/* Tabla con search, filtros y export CSV */}
          <GastosTableView gastos={gastos} categorias={categorias.map(c => c.nombre)} />
        </div>
      </main>
    </div>
  )
}
