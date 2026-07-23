import type { Metadata, Viewport } from 'next'
import { Inter, Fraunces } from 'next/font/google'
import './globals.css'
import ChatPanel from '@/components/ChatPanel'
import BottomNav from '@/components/BottomNav'
import { ThemeProvider } from '@/components/ThemeProvider'
import { Toaster } from 'sonner'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

// Serif editorial para números héroe y titulares — usada con moderación
const fraunces = Fraunces({
  subsets: ['latin'],
  variable: '--font-serif',
  display: 'swap',
  weight: ['400', '500', '600'],
})

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
    <html lang="es" className={`${inter.variable} ${fraunces.variable}`} suppressHydrationWarning>
      <head>
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
      </head>
      <body
        className="antialiased"
        style={{ paddingTop: 'env(safe-area-inset-top, 0px)' } as React.CSSProperties}
      >
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          {children}
          <ChatPanel />
          <BottomNav />
          <Toaster richColors position="top-right" />
        </ThemeProvider>
      </body>
    </html>
  )
}
