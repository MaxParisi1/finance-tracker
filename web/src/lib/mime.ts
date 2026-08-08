import 'server-only'

import MailComposer from 'nodemailer/lib/mail-composer'

/**
 * Arma un mensaje RFC822 completo (headers + cuerpo + adjuntos) para descargar
 * como archivo .eml.
 *
 * No hay envío ni conexión a ningún servidor: el .eml se abre en Thunderbird y
 * el usuario lo manda desde su propia cuenta. Así el sistema no necesita
 * credenciales de correo, y tampoco puede mandarle nada a nadie por su cuenta.
 *
 * Se usa nodemailer y no una plantilla propia porque el cuerpo lleva acentos y
 * un PDF adjunto: el encoding MIME es justo donde uno se equivoca en silencio y
 * el destinatario recibe "M?ximo" o un adjunto ilegible.
 */

export interface Adjunto {
  filename: string
  content: Buffer
  contentType: string
}

export interface MensajeParams {
  de: string
  para: string
  bcc?: string
  asunto: string
  cuerpo: string
  adjuntos: Adjunto[]
}

export async function construirEml(p: MensajeParams): Promise<Buffer> {
  const composer = new MailComposer({
    from: p.de,
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
