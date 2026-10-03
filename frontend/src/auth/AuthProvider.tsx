import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { User } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'
import AuthDialog from './AuthDialog'
import { AuthContext } from './authContext'
import type { AuthState } from './authContext'

/** Keeps the Supabase session in React state and owns the login/register dialog. */
export default function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(supabase !== null)
  const [dialogOpen, setDialogOpen] = useState(false)

  useEffect(() => {
    if (!supabase) return
    supabase.auth.getSession().then(({ data }) => {
      setUser(data.session?.user ?? null)
      setLoading(false)
    })
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null)
      if (session) setDialogOpen(false)
    })
    return () => data.subscription.unsubscribe()
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      configured: supabase !== null,
      openLogin: () => setDialogOpen(true),
      signOut: async () => {
        await supabase?.auth.signOut()
      },
    }),
    [user, loading],
  )

  return (
    <AuthContext.Provider value={value}>
      {children}
      {dialogOpen && <AuthDialog onClose={() => setDialogOpen(false)} />}
    </AuthContext.Provider>
  )
}
