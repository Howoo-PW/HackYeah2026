import { useEffect, useState } from 'react'
import { fetchMyOpinions, OPINIONS_CHANGED } from '../api/client'
import type { MyOpinion } from '../api/types'
import { supabase } from '../lib/supabase'

/** The signed-in user's own ratings and comments (GET /me/opinions), loaded on login; `opinions` is null while loading or signed out. */
export function useMyOpinions(userId: string | undefined) {
  const [opinions, setOpinions] = useState<MyOpinion[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [version, setVersion] = useState(0)

  // A saved rating or comment refreshes the list.
  useEffect(() => {
    const bump = () => setVersion((v) => v + 1)
    window.addEventListener(OPINIONS_CHANGED, bump)
    return () => window.removeEventListener(OPINIONS_CHANGED, bump)
  }, [])

  useEffect(() => {
    setFailed(false)
    if (!supabase || !userId) {
      setOpinions(null)
      return
    }
    const controller = new AbortController()
    supabase.auth
      .getSession()
      .then(({ data }) => {
        if (!data.session) throw new Error('no session')
        return fetchMyOpinions(data.session.access_token, controller.signal)
      })
      .then(setOpinions)
      .catch(() => !controller.signal.aborted && setFailed(true))
    return () => controller.abort()
  }, [userId, version])

  return { opinions, failed }
}
