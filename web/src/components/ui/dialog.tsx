'use client'

import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { cn } from '@/lib/utils'

// Base de todos los modales. Radix se ocupa de lo que antes faltaba: cerrar con
// Escape, atrapar el foco adentro, devolverlo al botón que abrió el modal y
// bloquear el scroll del fondo. Los modales se montan solo cuando están
// abiertos, así que acá siempre va `open`.
export function Modal({
  onClose,
  className,
  children,
}: {
  onClose: () => void
  className?: string
  children: React.ReactNode
}) {
  return (
    <DialogPrimitive.Root open onOpenChange={abierto => { if (!abierto) onClose() }}>
      <DialogPrimitive.Portal>
        {/* El contenido va dentro del overlay: así se centra (o queda abajo en
            mobile) igual que antes, y el clic afuera lo resuelve Radix. */}
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <DialogPrimitive.Content
            aria-describedby={undefined}
            className={cn(
              'bg-card text-card-foreground rounded-t-3xl sm:rounded-2xl shadow-modal border border-border',
              'w-full flex flex-col animate-slide-up sm:animate-fade-in focus:outline-none',
              className,
            )}
          >
            {children}
          </DialogPrimitive.Content>
        </DialogPrimitive.Overlay>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export const ModalTitle = React.forwardRef<
  HTMLHeadingElement,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title ref={ref} className={cn('text-base font-semibold', className)} {...props} />
))
ModalTitle.displayName = 'ModalTitle'
