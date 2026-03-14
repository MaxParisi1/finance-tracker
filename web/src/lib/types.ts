export interface Gasto {
  id: string
  fecha: string
  descripcion: string
  monto_original: number
  moneda: 'ARS' | 'USD'
  monto_ars: number
  tipo_cambio: number
  tipo_cambio_tipo: string
  categoria: string
  subcategoria?: string
  medio_pago: string
  cuotas: number
  cuota_actual: number
  es_recurrente: boolean
  comercio?: string
  notas?: string
  fuente: string
  created_at: string
}

export interface GastoRecurrente {
  id: string
  descripcion: string
  monto_original: number
  moneda: string
  categoria: string
  medio_pago: string
  frecuencia: string
  dia_del_mes: number
  activo: boolean
  proximo_vencimiento: string
  created_at: string
}

export interface Categoria {
  nombre: string
  descripcion?: string
  color: string
  icono: string
}

export interface MensualResumen {
  mes: number
  anio: number
  total_ars: number
  cantidad: number
  por_categoria: { categoria: string; total_ars: number; cantidad: number; color?: string }[]
}

export interface TendenciaMes {
  mes: number
  anio: number
  label: string
  total_ars: number
  cantidad: number
  variacion_pct: number | null
}
