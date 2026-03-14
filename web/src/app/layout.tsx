import type { Metadata } from 'next'
import './globals.css'
import ChatPanel from '@/components/ChatPanel'

export const metadata: Metadata = {
  title: 'Finance Tracker',
  description: 'Dashboard de finanzas personales',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="bg-gray-50 text-gray-900 antialiased">
        {children}
        <ChatPanel />
      </body>
    </html>
  )
}
