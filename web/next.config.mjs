/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',

  // nodemailer usa APIs de Node (streams, requires dinámicos) que se rompen si
  // Next lo mete en el bundle del servidor. Marcarlo como externo hace que se
  // cargue con require() en runtime.
  experimental: {
    serverComponentsExternalPackages: ['nodemailer'],
    // El default de las server actions es 1 MB; un resumen de tarjeta de varias
    // páginas lo pasa (el de Mastercard de octubre pesa 360 KB, pero los hay
    // más largos).
    serverActions: { bodySizeLimit: '10mb' },
  },
}

export default nextConfig
