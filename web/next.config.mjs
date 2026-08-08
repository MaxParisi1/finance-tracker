/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',

  // imapflow y nodemailer usan APIs de Node (sockets TLS, streams, requires
  // dinámicos) que se rompen si Next las mete en el bundle del servidor.
  // Marcarlas como externas hace que se carguen con require() en runtime.
  experimental: {
    serverComponentsExternalPackages: ['imapflow', 'nodemailer'],
  },
}

export default nextConfig
