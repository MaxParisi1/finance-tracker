interface SummaryCardProps {
  title: string
  value: string
  subtitle?: string
  trend?: number | null  // porcentaje de cambio
  icon?: string
}

export default function SummaryCard({ title, value, subtitle, trend, icon }: SummaryCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-start justify-between">
        <p className="text-sm text-gray-500 font-medium">{title}</p>
        {icon && <span className="text-xl">{icon}</span>}
      </div>

      <p className="text-2xl font-bold text-gray-900 mt-2">{value}</p>

      <div className="mt-2 flex items-center gap-2">
        {trend !== null && trend !== undefined && (
          <span
            className={`text-xs font-medium px-1.5 py-0.5 rounded ${
              trend > 0
                ? 'bg-red-50 text-red-600'
                : trend < 0
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-gray-100 text-gray-500'
            }`}
          >
            {trend > 0 ? '+' : ''}{trend}%
          </span>
        )}
        {subtitle && <p className="text-xs text-gray-400">{subtitle}</p>}
      </div>
    </div>
  )
}
