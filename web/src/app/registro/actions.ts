'use server'

import { revalidatePath } from 'next/cache'

import { descargarArchivoDrive } from '@/lib/drive'
import { borradorConsorcioConfigurado, env } from '@/lib/env'
import { crearBorrador } from '@/lib/outlook'
import { ASUNTO, cuerpo } from '@/lib/plantillaConsorcio'
import { getSupabaseServer } from '@/lib/supabase'

export type ResultadoBorrador =
  | { ok: true; carpeta: string }
  | { ok: false; error: string }

/**
 * Deja en Borradores de Outlook el mail al consorcio con el comprobante del mes.
 *
 * No envía nada: el usuario lo revisa y lo manda desde su cliente. Por eso se
 * registra `borrador_consorcio_at` como "generado", no como "enviado".
 *
 * Devuelve el error en vez de lanzarlo: Next oculta los mensajes de excepción
 * en producción ("digest property..."), lo que deja al usuario sin saber qué
 * pasó. Devolviéndolo, el detalle llega al toast.
 */
export async function crearBorradorConsorcioAction(
  facturaId: string,
): Promise<ResultadoBorrador> {
  try {
    return { ok: true, ...(await generarBorrador(facturaId)) }
  } catch (e: any) {
    console.error('[borrador-consorcio] falló', e)
    return { ok: false, error: e?.message ?? 'Error desconocido' }
  }
}

async function generarBorrador(facturaId: string): Promise<{ carpeta: string }> {
  if (!borradorConsorcioConfigurado()) {
    throw new Error(
      'Falta configurar OUTLOOK_EMAIL, OUTLOOK_APP_PASSWORD y CONSORCIO_EMAIL',
    )
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

  const content = await descargarArchivoDrive(comprobante.drive_file_id)

  const { carpeta } = await crearBorrador({
    para: env.CONSORCIO_EMAIL!,
    bcc: env.CONSORCIO_BCC,
    asunto: ASUNTO,
    cuerpo: cuerpo(String(factura.vencimiento)),
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
  return { carpeta }
}
