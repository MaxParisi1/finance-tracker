'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

export async function loginAction(formData: FormData) {
  const password = formData.get('password') as string
  const correctPassword = process.env.DASHBOARD_PASSWORD

  if (!correctPassword || password === correctPassword) {
    cookies().set('auth', password || 'open', {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 60 * 60 * 24 * 30, // 30 días
      path: '/',
    })
    redirect('/dashboard')
  }

  redirect('/login?error=1')
}
