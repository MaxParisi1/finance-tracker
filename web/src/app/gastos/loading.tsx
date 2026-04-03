import Sidebar from '@/components/Sidebar'
import { Skeleton } from '@/components/ui/skeleton'

export default function GastosLoading() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 overflow-auto">
        <div className="max-w-5xl mx-auto space-y-6">
          <div className="flex items-start justify-between">
            <div className="space-y-2">
              <Skeleton className="h-8 w-32" />
              <Skeleton className="h-4 w-56" />
            </div>
            <Skeleton className="h-9 w-36 rounded-lg" />
          </div>
          <div className="rounded-xl border border-border p-6 space-y-3">
            <div className="flex gap-2 mb-4">
              <Skeleton className="h-9 flex-1 rounded-lg" />
              <Skeleton className="h-9 w-28 rounded-lg" />
            </div>
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 py-2 border-b border-border/50">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 flex-1" />
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-4 w-24" />
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
