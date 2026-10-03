import { createContext } from 'react'
import type { User } from '@supabase/supabase-js'

export type AuthState = {
  user: User | null
  /** True until the stored session has been read. */
  loading: boolean
  /** False when Supabase env vars are missing: login is unavailable. */
  configured: boolean
  openLogin: () => void
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthState>({
  user: null,
  loading: false,
  configured: false,
  openLogin: () => {},
  signOut: async () => {},
})

/** Name shown in the UI: chosen display name, else the part of the e-mail before "@". */
export function displayNameOf(user: User): string {
  const name = user.user_metadata?.display_name
  if (typeof name === 'string' && name.trim()) return name.trim()
  return user.email?.split('@')[0] ?? 'Użytkownik'
}
