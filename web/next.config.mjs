/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',

  // nodemailer usa APIs de Node (streams, requires dinámicos) que se rompen si
  // Next lo mete en el bundle del servidor. Marcarlo como externo hace que se
  // cargue con require() en runtime.
  experimental: {
    serverComponentsExternalPackages: ['nodemailer'],
  },
}

export default nextConfig
