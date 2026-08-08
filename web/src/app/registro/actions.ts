'use server'

import { revalidatePath } from 'next/cache'

import { descargarArchivoDrive } from '@/lib/drive'
import { env } from '@/lib/env'
import { construirEml } from '@/lib/mime'
import { ASUNTO, cuerpo, mesDelPeriodo } from '@/lib/plantillaConsorcio'
import { getSupabaseServer } from '@/lib/supabase'

export type ResultadoBorrador =
  | { ok: true; nombreArchivo: string; emlBase64: string }
  | { ok: false; error: string }

/**
 * Arma el mail al consorcio con el comprobante del mes y lo devuelve como .eml
 * para descargar.
 *
 * No envía ni deja el borrador en ningún servidor: Microsoft ya no acepta
 * autenticación básica por IMAP en cuentas personales, así que el archivo se
 * baja y se abre en Thunderbird (doble click → Editar como nuevo). El efecto
 * lateral bueno es que el sistema no necesita credenciales de correo y, por
 * construcción, no puede mandarle un mail al consorcio por su cuenta.
 *
 * Devuelve el error en vez de lanzarlo: Next oculta los mensajes de excepción
 * en producción, lo que dejaría al usuario sin diagnóstico.
 */
export async function crearBorradorConsorcioAction(
  facturaId: string,
): Promise<ResultadoBorrador> {
  try {
    return { ok: true, ...(await generarEml(facturaId)) }
  } catch (e: any) {
    console.error('[borrador-consorcio] falló', e)
    return { ok: false, error: e?.message ?? 'Error desconocido' }
  }
}

async function generarEml(
  facturaId: string,
): Promise<{ nombreArchivo: string; emlBase64: string }> {
  if (!env.OUTLOOK_EMAIL || !env.CONSORCIO_EMAIL) {
    throw new Error('Faltan OUTLOOK_EMAIL y CONSORCIO_EMAIL en las variables de entorno')
  }

  const supabase = getSupabaseServer()
  const { data: factura, error } = await supabase
    .from('facturas')
    .select('id, vencimiento, archivos_drive(tipo, drive_file_id, drive_file_name, mime_type)')
    .eq('id', facturaId)
    .single()

  if (error || !factura) throw new Error(error?.message ?? 'No encontré la factura')

  const archivos = (factura.archivos_drive ?? []) as {
    tipo: string; drive_file_id: string; drive_file_name: string; mime_type: string | null
  }[]
  const comprobante = archivos.find(a => a.tipo === 'comprobante')

  if (!comprobante) {
    throw new Error('Todavía no hay comprobante archivado para ese mes')
  }

  const vencimiento = String(factura.vencimiento)
  const content = await descargarArchivoDrive(comprobante.drive_file_id)

  const eml = await construirEml({
    de: env.OUTLOOK_EMAIL,
    para: env.CONSORCIO_EMAIL,
    bcc: env.CONSORCIO_BCC,
    asunto: ASUNTO,
    cuerpo: cuerpo(vencimiento),
    adjuntos: [{
      filename: comprobante.drive_file_name,
      content,
      contentType: comprobante.mime_type || 'application/pdf',
    }],
  })

  await supabase
    .from('facturas')
    .update({ borrador_consorcio_at: new Date().toISOString() })
    .eq('id', facturaId)

  revalidatePath('/registro')

  return {
    nombreArchivo: `expensas-${mesDelPeriodo(vencimiento).toLowerCase()}-${vencimiento.slice(0, 4)}.eml`,
    emlBase64: eml.toString('base64'),
  }
}
