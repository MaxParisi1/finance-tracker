import '@/lib/env'
import { NextRequest, NextResponse } from 'next/server'
import { cookies } from 'next/headers'
import {
  GoogleGenerativeAI,
  FunctionDeclaration,
  SchemaType,
  type Content,
} from '@google/generative-ai'
import {
  getResumenMes,
  getGastosMes,
  getGastosRecientes,
  getTendencia,
  getTopComercios,
  getCategorias,
  getLatestTipoCambio,
  getRecurrentesConCosto,
} from '@/lib/queries'
import { getSupabaseServer } from '@/lib/supabase'

// ──────────────────────────────────────────────
// Rate limiting (protege la cuota de Gemini)
// ──────────────────────────────────────────────

const rateLimitMap = new Map<string, { count: number; resetAt: number }>()
const RATE_LIMIT_WINDOW_MS = 60_000 // 1 minuto
const RATE_LIMIT_MAX = 30            // 30 requests por minuto

function checkRateLimit(ip: string): boolean {
  const now = Date.now()
  const entry = rateLimitMap.get(ip)
  if (!entry || now > entry.resetAt) {
    rateLimitMap.set(ip, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS })
    return true
  }
  if (entry.count >= RATE_LIMIT_MAX) return false
  entry.count++
  return true
}

// ──────────────────────────────────────────────
// Auth check
// ──────────────────────────────────────────────

function isAuthorized(): boolean {
  const password = process.env.DASHBOARD_PASSWORD
  if (!password) return true
  const authCookie = cookies().get('auth')
  return authCookie?.value === password
}

// ──────────────────────────────────────────────
// Herramientas disponibles
// ──────────────────────────────────────────────

const TOOL_DECLARATIONS: FunctionDeclaration[] = [
  {
    name: 'resumen_mensual',
    description: 'Devuelve el total gastado en un mes agrupado por categoría.',
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        mes:  { type: SchemaType.INTEGER, description: 'Número de mes (1-12)' },
        anio: { type: SchemaType.INTEGER, description: 'Año de 4 dígitos' },
      },
      required: ['mes', 'anio'],
    },
  },
  {
    name: 'consultar_gastos',
    description: 'Consulta gastos con filtros opcionales: mes, anio, categoria.',
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        filtros: { type: SchemaType.OBJECT, description: 'Filtros opcionales' },
      },
    },
  },
  {
    name: 'tendencia_gastos',
    description: 'Evolución del gasto total en los últimos N meses con variación porcentual.',
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        meses: { type: SchemaType.INTEGER, description: 'Cantidad de meses (default: 6)' },
      },
    },
  },
  {
    name: 'comparar_meses',
    description: 'Compara totales y categorías entre dos meses.',
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        mes1:  { type: SchemaType.INTEGER },
        anio1: { type: SchemaType.INTEGER },
        mes2:  { type: SchemaType.INTEGER },
        anio2: { type: SchemaType.INTEGER },
      },
      required: ['mes1', 'anio1', 'mes2', 'anio2'],
    },
  },
  {
    name: 'top_comercios',
    description: 'Ranking de comercios/lugares con mayor gasto en un período.',
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        mes:    { type: SchemaType.INTEGER },
        anio:   { type: SchemaType.INTEGER },
        limite: { type: SchemaType.INTEGER },
      },
    },
  },
  {
    name: 'obtener_tipo_cambio',
    description: 'Consulta el tipo de cambio actual (blue, oficial, mep) desde bluelytics.com.ar.',
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        tipo: { type: SchemaType.STRING, description: '"blue", "oficial" o "mep". Default: blue.' },
      },
    },
  },
  {
    name: 'gastos_recurrentes',
    description: 'Devuelve suscripciones y gastos fijos activos con su costo mensual.',
    parameters: { type: SchemaType.OBJECT, properties: {} },
  },
  {
    name: 'obtener_categorias',
    description: 'Lista de categorías disponibles en la base de datos.',
    parameters: { type: SchemaType.OBJECT, properties: {} },
  },
  {
    name: 'guardar_gasto',
    description:
      'Guarda un gasto en la base de datos. ' +
      'SIEMPRE mostrar un resumen y pedir confirmación explícita antes de llamar esta función.',
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        descripcion: { type: SchemaType.STRING },
        monto:       { type: SchemaType.NUMBER },
        moneda:      { type: SchemaType.STRING, description: '"ARS" o "USD"' },
        categoria:   { type: SchemaType.STRING },
        medio_pago:  {
          type: SchemaType.STRING,
          description: 'credito_ars | credito_usd | debito | efectivo_ars | efectivo_usd | transferencia',
        },
        fecha:  { type: SchemaType.STRING, description: 'Formato YYYY-MM-DD. Si no se especifica, usar hoy.' },
        notas:  { type: SchemaType.STRING },
        cuotas: { type: SchemaType.INTEGER },
      },
      required: ['descripcion', 'monto', 'moneda', 'categoria', 'medio_pago'],
    },
  },
]

// ──────────────────────────────────────────────
// Ejecutores de funciones
// ──────────────────────────────────────────────

async function ejecutarFuncion(nombre: string, args: Record<string, any>): Promise<string> {
  try {
    let resultado: unknown

    switch (nombre) {
      case 'resumen_mensual': {
        resultado = await getResumenMes(args.mes, args.anio)
        break
      }

      case 'consultar_gastos': {
        const f = args.filtros ?? {}
        let gastos
        if (f.mes && f.anio) {
          gastos = await getGastosMes(parseInt(f.mes), parseInt(f.anio))
        } else {
          gastos = await getGastosRecientes(30)
        }
        if (f.categoria) gastos = gastos.filter((g: any) => g.categoria === f.categoria)
        const total_ars = gastos.reduce((s: number, g: any) => s + (g.monto_ars ?? 0), 0)
        resultado = { cantidad: gastos.length, total_ars: Math.round(total_ars), gastos: gastos.slice(0, 20) }
        break
      }

      case 'tendencia_gastos': {
        resultado = await getTendencia(args.meses ?? 6)
        break
      }

      case 'comparar_meses': {
        const [r1, r2] = await Promise.all([
          getResumenMes(args.mes1, args.anio1),
          getResumenMes(args.mes2, args.anio2),
        ])
        const diff = r2.total_ars - r1.total_ars
        const pct = r1.total_ars > 0 ? Math.round((diff / r1.total_ars) * 1000) / 10 : null
        resultado = { mes1: r1, mes2: r2, diferencia_ars: diff, variacion_pct: pct }
        break
      }

      case 'top_comercios': {
        const hoy = new Date()
        resultado = await getTopComercios(
          args.mes ?? hoy.getMonth() + 1,
          args.anio ?? hoy.getFullYear(),
          args.limite ?? 10,
        )
        break
      }

      case 'obtener_tipo_cambio': {
        const tipo = args.tipo ?? 'blue'
        const res = await fetch('https://api.bluelytics.com.ar/v2/latest', {
          next: { revalidate: 300 },
        })
        const data = await res.json()
        const mapa: Record<string, any> = { blue: data.blue, oficial: data.oficial, mep: data.blue_euro }
        const tc = mapa[tipo] ?? data.blue
        resultado = {
          tipo,
          compra: tc.value_buy,
          venta: tc.value_sell,
          promedio: Math.round((tc.value_buy + tc.value_sell) / 2),
        }
        break
      }

      case 'gastos_recurrentes': {
        const { recurrentes, total_mensual_ars, total_anual_ars } = await getRecurrentesConCosto()
        resultado = { recurrentes, total_mensual_ars, total_anual_ars }
        break
      }

      case 'obtener_categorias': {
        resultado = await getCategorias()
        break
      }

      case 'guardar_gasto': {
        const supabase = getSupabaseServer()
        const { descripcion, monto, moneda, categoria, medio_pago, fecha, notas, cuotas } = args
        const monedaUpper = (moneda ?? 'ARS').toUpperCase()

        let monto_ars = monto
        let tipo_cambio = 1.0
        let tipo_cambio_tipo = 'n/a'

        if (monedaUpper === 'USD') {
          const tc = await getLatestTipoCambio('blue')
          if (tc) {
            monto_ars = monto * tc
            tipo_cambio = tc
            tipo_cambio_tipo = 'blue'
          }
        }

        const { data, error } = await supabase
          .from('gastos')
          .insert({
            descripcion,
            monto_original: monto,
            moneda: monedaUpper,
            monto_ars: Math.round(monto_ars),
            tipo_cambio,
            tipo_cambio_tipo,
            categoria,
            medio_pago,
            fecha: fecha ?? new Date().toISOString().split('T')[0],
            notas: notas ?? null,
            cuotas: cuotas ?? 1,
            cuota_actual: 1,
            fuente: 'web_manual',
          })
          .select()
          .single()

        if (error) throw new Error(error.message)

        // Auto-expandir cuotas 2..N
        if (cuotas && cuotas > 1) {
          let fechaCuota = (fecha ?? new Date().toISOString().split('T')[0]) as string
          for (let n = 2; n <= cuotas; n++) {
            fechaCuota = addOneMonth(fechaCuota)
            await supabase.from('gastos').insert({
              ...{
                descripcion,
                monto_original: monto,
                moneda: monedaUpper,
                monto_ars: Math.round(monto_ars),
                tipo_cambio,
                tipo_cambio_tipo,
                categoria,
                medio_pago,
                notas: notas ?? null,
                fuente: 'web_manual',
                cuotas,
                cuota_actual: 1,
              },
              fecha: fechaCuota,
              cuota_actual: n,
            })
          }
        }

        resultado = { guardado: true, id: data.id, monto_ars: Math.round(monto_ars), cuotas: cuotas ?? 1 }
        break
      }

      default:
        resultado = { error: `Función desconocida: ${nombre}` }
    }

    return JSON.stringify(resultado, null, 2)
  } catch (e: any) {
    return JSON.stringify({ error: e.message ?? 'Error desconocido' })
  }
}

// ──────────────────────────────────────────────
// Handler
// ──────────────────────────────────────────────

/** Suma exactamente un mes a una fecha YYYY-MM-DD */
function addOneMonth(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  // new Date(y, m, d): month es 0-indexed, así que m == siguiente mes
  return new Date(y, m, d).toISOString().split('T')[0]
}

export async function POST(req: NextRequest) {
  if (!isAuthorized()) {
    return NextResponse.json({ error: 'No autorizado' }, { status: 401 })
  }

  const ip = req.headers.get('x-forwarded-for') ?? req.headers.get('x-real-ip') ?? 'local'
  if (!checkRateLimit(ip)) {
    return NextResponse.json({ error: 'Demasiadas solicitudes. Esperá un momento.' }, { status: 429 })
  }

  const apiKey = process.env.GOOGLE_API_KEY
  if (!apiKey) {
    return NextResponse.json({ error: 'GOOGLE_API_KEY no configurada' }, { status: 500 })
  }

  const { message, history } = await req.json() as {
    message: string
    history: { role: 'user' | 'assistant'; content: string }[]
  }

  // Convertir historial al formato Gemini
  const geminiHistory: Content[] = history.map(m => ({
    role: m.role === 'assistant' ? 'model' : 'user',
    parts: [{ text: m.content }],
  }))

  const hoy = new Date().toLocaleDateString('es-AR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  })

  const systemInstruction = `Sos un asistente financiero personal. Hoy es ${hoy}.

REGLAS:
1. Respondés SIEMPRE en español argentino, de forma concisa y directa.
2. NUNCA guardás un gasto sin mostrar primero un resumen y recibir confirmación explícita.
   Formato: "Voy a guardar: **$MONTO MONEDA** en **DESCRIPCIÓN** (CATEGORÍA) · MEDIO_PAGO · FECHA. ¿Confirmo?"
3. Confirmaciones válidas: "sí", "si", "dale", "ok", "confirmado", "va", "sí dale".
4. Usás el tipo de cambio blue por defecto para conversiones USD → ARS.
5. Las consultas responden con números concretos y formato ARS ($ 1.234.567).
6. Cuando el usuario pide categorías, primero consultás las disponibles en la DB.`

  const genAI = new GoogleGenerativeAI(apiKey)
  const model = genAI.getGenerativeModel({
    model: 'gemini-2.5-flash',
    tools: [{ functionDeclarations: TOOL_DECLARATIONS }],
    systemInstruction,
  })

  const chat = model.startChat({ history: geminiHistory })

  try {
    let response = await chat.sendMessage(message)
    let dataMutated = false

    // Loop de function calling (máximo 5 iteraciones)
    for (let i = 0; i < 5; i++) {
      const calls = response.response.functionCalls()
      if (!calls || calls.length === 0) break

      const functionResponses = await Promise.all(
        calls.map(async fc => {
          const result = await ejecutarFuncion(fc.name, fc.args as Record<string, any>)
          if (fc.name === 'guardar_gasto') {
            try {
              const parsed = JSON.parse(result)
              if (parsed.guardado) dataMutated = true
            } catch {}
          }
          return {
            functionResponse: { name: fc.name, response: { result } },
          }
        }),
      )

      response = await chat.sendMessage(functionResponses)
    }

    const text = response.response.text()
    return NextResponse.json({ response: text, mutated: dataMutated })
  } catch (e: any) {
    console.error('Chat API error:', e)
    return NextResponse.json({ error: e.message ?? 'Error interno' }, { status: 500 })
  }
}
