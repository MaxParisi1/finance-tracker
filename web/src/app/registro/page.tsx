import Sidebar from '@/components/Sidebar'
import RegistroView from '@/components/RegistroView'
import { getRegistro, getFijosDelMes } from '@/lib/queries'

export const dynamic = 'force-dynamic'

export default async function RegistroPage({
  searchParams,
}: {
  searchParams: { anio?: string }
}) {
  const hoy = new Date()
  const anioParam = Number(searchParams.anio)
  const anio = anioParam >= 2020 && anioParam <= 2100 ? anioParam : hoy.getFullYear()

  const [registro, fijos] = await Promise.all([
    getRegistro(anio),
    getFijosDelMes(hoy.getMonth() + 1, hoy.getFullYear()),
  ])

  return (
    <div className="flex min-h-screen">
      <Sidebar pendientes={fijos.pendientes.length} />

      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 md:pb-8 overflow-auto">
        <div className="max-w-5xl mx-auto">
          <div className="mb-6 flex items-end justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">Registro</h1>
              <p className="text-muted-foreground text-sm mt-1">
                Qué facturas y comprobantes están archivados, y cuáles faltan
              </p>
            </div>
            <div className="flex gap-1">
              {[anio - 1, anio, anio + 1]
                .filter(a => a <= hoy.getFullYear())
                .map(a => (
                  <a
                    key={a}
                    href={`/registro?anio=${a}`}
                    className={
                      'px-3 py-1.5 rounded-lg text-sm border transition-colors ' +
                      (a === anio
                        ? 'border-primary bg-primary/10 text-primary font-medium'
                        : 'border-border text-muted-foreground hover:text-foreground')
                    }
                  >
                    {a}
                  </a>
                ))}
            </div>
          </div>

          <RegistroView registro={registro} />
        </div>
      </main>
    </div>
  )
}
