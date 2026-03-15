import type { Metadata, Viewport } from 'next'
import './globals.css'
import ChatPanel from '@/components/ChatPanel'
import BottomNav from '@/components/BottomNav'

export const metadata: Metadata = {
  title: 'Finance Tracker',
  description: 'Dashboard de finanzas personales',
  manifest: '/manifest.json',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'Finance',
  },
  formatDetection: {
    telephone: false,
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <head>
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
      </head>
      <body className="bg-gray-50 text-gray-900 antialiased">
        {children}
        <ChatPanel />
        <BottomNav />
      </body>
    </html>
  )
}
