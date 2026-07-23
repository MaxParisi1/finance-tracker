import Sidebar from '@/components/Sidebar'
import { Skeleton } from '@/components/ui/skeleton'

export default function DashboardLoading() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 px-4 md:px-8 pt-6 pb-safe-24 md:py-8 overflow-auto">
        <div className="max-w-5xl mx-auto space-y-6">
          {/* Header */}
          <div className="space-y-2">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-4 w-64" />
          </div>
          {/* Hero + categorías */}
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
            <div className="lg:col-span-3 rounded-xl border border-border p-6 flex items-center gap-6">
              <Skeleton className="h-[108px] w-[108px] rounded-full" />
              <div className="space-y-3 flex-1">
                <Skeleton className="h-10 w-48" />
                <Skeleton className="h-4 w-56" />
              </div>
            </div>
            <div className="lg:col-span-2 rounded-xl border border-border p-6 space-y-3">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-4 w-full" />)}
            </div>
          </div>
          {/* Table skeleton */}
          <div className="rounded-xl border border-border p-6 space-y-4">
            <Skeleton className="h-5 w-40" />
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 flex-1" />
                <Skeleton className="h-4 w-24" />
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
