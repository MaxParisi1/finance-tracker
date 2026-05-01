import Sidebar from '@/components/Sidebar'
import HistoricoView from '@/components/HistoricoView'
import { getGastosHistorico, getCategorias } from '@/lib/queries'

export const dynamic = 'force-dynamic'

function calcRange(rango: string): { desde: string; hasta: string } {
  const hoy = new Date()
  const mesesAtras = rango === '3m' ? 3 : rango === '12m' ? 12 : 6
  const desdeDate = new Date(hoy.getFullYear(), hoy.getMonth() - (mesesAtras - 1), 1)
  const hastaDate = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 1)
  return {
    desde: desdeDate.toISOString().split('T')[0],
    hasta: hastaDate.toISOString().split('T')[0],
  }
}

export default async function HistoricoPage({
  searchParams,
}: {
  searchParams: { rango?: string; busqueda?: string; categoria?: string; medio_pago?: string }
}) {
  const rango = ['3m', '6m', '12m'].includes(searchParams.rango ?? '') ? searchParams.rango! : '6m'
  const busqueda = searchParams.busqueda ?? ''
  const categoria = searchParams.categoria ?? ''
  const medio_pago = searchParams.medio_pago ?? ''

  const { desde, hasta } = calcRange(rango)

  const [{ meses, gastos }, categorias] = await Promise.all([
    getGastosHistorico({
      desde,
      hasta,
      busqueda: busqueda || undefined,
      categoria: categoria || undefined,
      medio_pago: medio_pago || undefined,
    }),
    getCategorias(),
  ])

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-foreground">Histórico</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Evolución de gastos en el tiempo
            </p>
          </div>

          <HistoricoView
            meses={meses}
            gastos={gastos}
            categorias={categorias}
            filtros={{ rango, busqueda, categoria, medio_pago }}
          />
        </div>
      </main>
    </div>
  )
}
