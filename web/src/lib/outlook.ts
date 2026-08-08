import 'server-only'

import { ImapFlow } from 'imapflow'
import MailComposer from 'nodemailer/lib/mail-composer'

import { env } from '@/lib/env'

/**
 * Deja un borrador en la carpeta Borradores de Outlook, vía IMAP APPEND.
 *
 * Deliberadamente NO envía: solo crea borradores. Aunque haya un bug, el
 * sistema no puede mandarle un mail al consorcio por su cuenta — la
 * confirmación humana queda donde importa, que es un destinatario externo.
 *
 * El borrador aparece en Thunderbird y en Outlook web, con el Bcc incluido
 * (Thunderbird lo respeta al enviar).
 */

export interface Adjunto {
  filename: string
  content: Buffer
  contentType: string
}

export interface BorradorParams {
  para: string
  bcc?: string
  asunto: string
  cuerpo: string
  adjuntos: Adjunto[]
}

/** Arma el mensaje RFC822 completo, con encoding correcto para acentos. */
export async function construirMime(p: BorradorParams, remitente: string): Promise<Buffer> {
  const composer = new MailComposer({
    from: remitente,
    to: p.para,
    bcc: p.bcc || undefined,
    subject: p.asunto,
    text: p.cuerpo,
    attachments: p.adjuntos.map(a => ({
      filename: a.filename,
      content: a.content,
      contentType: a.contentType,
    })),
  })
  return await composer.compile().build()
}

/**
 * Busca la carpeta de borradores por su flag de uso especial `\Drafts`.
 * No se busca por nombre porque depende del idioma de la cuenta: en una cuenta
 * en español se llama "Borradores", no "Drafts".
 */
async function rutaDeBorradores(cliente: ImapFlow): Promise<string> {
  const carpetas = await cliente.list()
  const especial = carpetas.find(c => c.specialUse === '\\Drafts')
  if (especial) return especial.path

  const porNombre = carpetas.find(c => /^(drafts|borradores)$/i.test(c.name))
  if (porNombre) return porNombre.path

  throw new Error(
    `No encontré la carpeta de borradores. Carpetas disponibles: ${carpetas.map(c => c.path).join(', ')}`,
  )
}

export async function crearBorrador(p: BorradorParams): Promise<{ carpeta: string }> {
  const usuario = env.OUTLOOK_EMAIL
  const pass = env.OUTLOOK_APP_PASSWORD
  if (!usuario || !pass) {
    throw new Error('Faltan OUTLOOK_EMAIL / OUTLOOK_APP_PASSWORD')
  }

  const raw = await construirMime(p, usuario)

  const cliente = new ImapFlow({
    host: env.OUTLOOK_IMAP_HOST,
    port: 993,
    secure: true,
    auth: { user: usuario, pass },
    logger: false,
  })

  await cliente.connect()
  try {
    const carpeta = await rutaDeBorradores(cliente)
    // \Seen para que no aparezca como no leído; \Draft para que el cliente lo
    // abra en modo edición en vez de solo lectura.
    await cliente.append(carpeta, raw, ['\\Draft', '\\Seen'])
    return { carpeta }
  } finally {
    await cliente.logout().catch(() => cliente.close())
  }
}
