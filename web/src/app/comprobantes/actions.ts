'use server'

import { revalidatePath } from 'next/cache'
import { getSupabaseServer } from '@/lib/supabase'
import { subirArchivoDrive } from '@/lib/drive'

export async function subirYVincularArchivoAction(formData: FormData) {
  const file = formData.get('file') as File | null
  const gastoId = formData.get('gastoId') as string
  const comercio = (formData.get('comercio') as string) || 'Sin comercio'
  const fecha = formData.get('fecha') as string
  const tipo = formData.get('tipo') as string
  const categoria = (formData.get('categoria') as string) || null
  const nombreArchivo = (formData.get('nombreArchivo') as string) || undefined

  if (!file || !gastoId || !fecha || !tipo) {
    throw new Error('Faltan campos requeridos')
  }

  const bytes = await file.arrayBuffer()
  const buffer = Buffer.from(bytes)

  const { driveFileId, driveFileName, driveWebViewLink, driveFolderPath } =
    await subirArchivoDrive({
      fileBuffer: buffer,
      mimeType: file.type || 'application/pdf',
      comercio,
      fecha,
      tipo,
      nombreArchivo,
    })

  const supabase = getSupabaseServer()
  const { error } = await supabase.from('archivos_drive').insert({
    gasto_id: gastoId,
    tipo,
    comercio: comercio.trim() || null,
    fecha,
    categoria: categoria || null,
    monto: null,
    moneda: null,
    drive_file_id: driveFileId,
    drive_file_name: driveFileName,
    drive_web_view_link: driveWebViewLink,
    drive_folder_path: driveFolderPath,
    mime_type: file.type || 'application/pdf',
  })

  if (error) throw new Error(error.message)

  revalidatePath('/gastos')
  revalidatePath('/comprobantes')
  revalidatePath('/dashboard')
}

export async function vincularArchivoExistenteAction(archivoId: string, gastoId: string) {
  const supabase = getSupabaseServer()
  const { error } = await supabase
    .from('archivos_drive')
    .update({ gasto_id: gastoId })
    .eq('id', archivoId)
  if (error) throw new Error(error.message)
  revalidatePath('/gastos')
  revalidatePath('/comprobantes')
}
