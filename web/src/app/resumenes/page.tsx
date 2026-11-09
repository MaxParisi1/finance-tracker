import Link from 'next/link'
import Sidebar from '@/components/Sidebar'
import SeccionTabs from '@/components/SeccionTabs'
import SubirResumen from '@/components/SubirResumen'
import { getFijosDelMes, getResumenesTarjeta, type ResumenTarjeta } from '@/lib/queries'
import { ahoraAR } from '@/lib/fechas'
import { formatDate } from '@/lib/utils'

export const dynamic = 'force-dynamic'

function nombreTarjeta(r: ResumenTarjeta): string {
  if (!r.tarjeta) return r.nombre_archivo ?? 'Resumen'
  return `${r.tarjeta.nombre ?? r.tarjeta.red ?? 'Tarjeta'} ${r.tarjeta.sufijo}`
}

function EstadoChip({ estado }: { estado: ResumenTarjeta['estado'] }) {
  const estilos = {
    pendiente: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
    procesado: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    error: 'bg-red-500/10 text-red-600 dark:text-red-400',
  }
  const texto = { pendiente: 'Procesando', procesado: 'Listo', error: 'No se pudo leer' }
  return <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${estilos[estado]}`}>{texto[estado]}</span>
}

export default async function ResumenesPage() {
  const hoy = ahoraAR()
  const [resumenes, fijos] = await Promise.all([
    getResumenesTarjeta(),
    getFijosDelMes(hoy.getMonth() + 1, hoy.getFullYear()),
  ])

  return (
    <div className="flex min-h-screen">
      <Sidebar pendientes={fijos.pendientes.length} />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          <SeccionTabs />
          <div className="mb-6">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">Resúmenes de tarjeta</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Subí el resumen del mes y revisá qué cobró la tarjeta que no quedó registrado
            </p>
          </div>

          <SubirResumen />

          <div className="mt-8 rounded-xl border border-border divide-y divide-border">
            {resumenes.length === 0 && (
              <p className="p-6 text-sm text-muted-foreground">Todavía no subiste ningún resumen.</p>
            )}
            {resumenes.map(r => (
              <Link
                key={r.id}
                href={`/resumenes/${r.id}`}
                className="flex items-center justify-between gap-4 p-4 hover:bg-muted/40 transition-colors"
              >
                <div className="min-w-0">
                  <p className="font-medium text-foreground truncate">{nombreTarjeta(r)}</p>
                  <p className="text-sm text-muted-foreground">
                    {r.cierre ? `Cierre ${formatDate(r.cierre)}` : r.nombre_archivo}
                  </p>
                </div>
                <EstadoChip estado={r.estado} />
              </Link>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
