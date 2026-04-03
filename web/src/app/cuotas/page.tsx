import Sidebar from '@/components/Sidebar'
import PlanesCuotaView from '@/components/PlanesCuotaView'
import { getPlanesCuota, getCategorias } from '@/lib/queries'

export const dynamic = 'force-dynamic'

export default async function CuotasPage() {
  const [planes, categorias] = await Promise.all([
    getPlanesCuota(),
    getCategorias(),
  ])

  const activos = planes.filter(p => p.activo).length
  const comprometidoMensual = planes
    .filter(p => p.activo && p.tipo === 'fijo' && p.monto_cuota != null && p.moneda === 'ARS')
    .reduce((sum, p) => sum + (p.monto_cuota ?? 0), 0)

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-3xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-foreground">Planes de cuotas</h1>
            <p className="text-muted-foreground text-sm mt-1">
              {activos} plan{activos !== 1 ? 'es' : ''} activo{activos !== 1 ? 's' : ''}
              {comprometidoMensual > 0 && (
                <span>
                  {' · '}
                  {new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(comprometidoMensual)} fijos/mes
                </span>
              )}
            </p>
          </div>

          <PlanesCuotaView
            planes={planes}
            categorias={categorias.map(c => c.nombre)}
          />
        </div>
      </main>
    </div>
  )
}
