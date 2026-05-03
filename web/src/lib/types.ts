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
  recurrente_id?: string | null
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
  no_materializar: boolean
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

export interface Presupuesto {
  id: string
  categoria: string
  mes: number
  anio: number
  monto_limite: number
}

export interface TendenciaMes {
  mes: number
  anio: number
  label: string
  total_ars: number
  cantidad: number
  variacion_pct: number | null
}

export interface PlanCuota {
  id: string
  descripcion: string
  comercio: string | null
  categoria: string | null
  medio_pago: string
  monto_cuota: number | null
  moneda: string
  cuotas_total: number
  cuota_actual: number
  dia_del_mes: number
  proximo_vencimiento: string
  tipo: 'fijo' | 'variable'
  activo: boolean
  created_at: string
}

export interface ArchivoDrive {
  id: string
  gasto_id: string | null
  tipo: string
  comercio: string | null
  fecha: string
  categoria: string | null
  monto: number | null
  moneda: string | null
  drive_file_id: string
  drive_file_name: string
  drive_web_view_link: string | null
  drive_folder_path: string | null
  mime_type: string | null
  created_at: string
}
