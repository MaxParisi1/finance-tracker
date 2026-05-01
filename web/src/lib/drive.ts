import { google } from 'googleapis'
import { Readable } from 'stream'

const MONTH_NAMES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]

function normalizarComercio(nombre: string): string {
  const sinAcentos = nombre.normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
  let norm = sinAcentos.toLowerCase().trim()
  norm = norm.replace(/[\s.]+/g, '_')
  norm = norm.replace(/[^a-z0-9_\-]/g, '')
  return norm
}

function normalizarCarpeta(nombre: string): string {
  const limpio = nombre.trim().replace(/[^\w\s.\-áéíóúÁÉÍÓÚñÑ]/g, '')
  return limpio
    .split(' ')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ')
    || 'Otros'
}

function getExtension(mimeType: string): string {
  const map: Record<string, string> = {
    'application/pdf': 'pdf',
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/heic': 'heic',
  }
  return map[mimeType] ?? 'pdf'
}

function buildDriveClient() {
  const refreshToken = process.env.DRIVE_REFRESH_TOKEN
  const clientId = process.env.DRIVE_CLIENT_ID
  const clientSecret = process.env.DRIVE_CLIENT_SECRET

  if (!refreshToken || !clientId || !clientSecret) {
    throw new Error(
      'Faltan variables de entorno de Google Drive: DRIVE_REFRESH_TOKEN, DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET',
    )
  }

  const auth = new google.auth.OAuth2(clientId, clientSecret)
  auth.setCredentials({ refresh_token: refreshToken })
  return google.drive({ version: 'v3', auth })
}

async function findFolder(
  drive: ReturnType<typeof google.drive>,
  name: string,
  parentId: string,
): Promise<string | null> {
  const escapedName = name.replace(/'/g, "\\'")
  const res = await drive.files.list({
    q: `name='${escapedName}' and '${parentId}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false`,
    fields: 'files(id)',
    spaces: 'drive',
  })
  return res.data.files?.[0]?.id ?? null
}

async function getOrCreateFolder(
  drive: ReturnType<typeof google.drive>,
  name: string,
  parentId: string,
): Promise<string> {
  const existing = await findFolder(drive, name, parentId)
  if (existing) return existing

  const res = await drive.files.create({
    requestBody: {
      name,
      mimeType: 'application/vnd.google-apps.folder',
      parents: [parentId],
    },
    fields: 'id',
  })
  return res.data.id!
}

export interface UploadResult {
  driveFileId: string
  driveFileName: string
  driveWebViewLink: string
  driveFolderPath: string
}

export async function subirArchivoDrive(params: {
  fileBuffer: Buffer
  mimeType: string
  comercio: string
  fecha: string
  tipo: string
  nombreArchivo?: string
}): Promise<UploadResult> {
  const rootFolderId = process.env.GOOGLE_DRIVE_ROOT_FOLDER_ID
  if (!rootFolderId) throw new Error('Falta GOOGLE_DRIVE_ROOT_FOLDER_ID')

  const drive = buildDriveClient()

  const fechaDate = new Date(params.fecha + 'T00:00:00')
  const anio = fechaDate.getFullYear()
  const mes = fechaDate.getMonth() + 1
  const mesStr = `${String(mes).padStart(2, '0')} - ${MONTH_NAMES[mes - 1]}`

  // Crear estructura de carpetas: Root/{Comercio}/{Año}/{MM - Mes}
  const carpetaComercio = normalizarCarpeta(params.comercio)
  const comercioId = await getOrCreateFolder(drive, carpetaComercio, rootFolderId)
  const anioId = await getOrCreateFolder(drive, String(anio), comercioId)
  const mesId = await getOrCreateFolder(drive, mesStr, anioId)
  const folderPath = `${carpetaComercio}/${anio}/${mesStr}`

  const ext = getExtension(params.mimeType)
  let fileName: string
  if (params.nombreArchivo) {
    const nombre = params.nombreArchivo.trim()
    fileName = nombre.includes('.') ? nombre : `${nombre}.${ext}`
  } else {
    const comercioNorm = normalizarComercio(params.comercio)
    fileName = `${params.fecha}_${comercioNorm}_${params.tipo.toLowerCase()}.${ext}`
  }

  // Subir archivo
  const stream = Readable.from(params.fileBuffer)
  const res = await drive.files.create({
    requestBody: {
      name: fileName,
      parents: [mesId],
    },
    media: {
      mimeType: params.mimeType,
      body: stream,
    },
    fields: 'id, webViewLink, name',
  })

  const fileId = res.data.id!
  const webViewLink = res.data.webViewLink ?? `https://drive.google.com/file/d/${fileId}/view`

  return {
    driveFileId: fileId,
    driveFileName: res.data.name ?? fileName,
    driveWebViewLink: webViewLink,
    driveFolderPath: folderPath,
  }
}
