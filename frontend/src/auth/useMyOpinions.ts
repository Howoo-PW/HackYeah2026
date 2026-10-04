import { useEffect, useState } from 'react'
import { fetchMyOpinions, OPINIONS_CHANGED } from '../api/client'
import type { MyOpinion } from '../api/types'

type Loaded = { userId: string; opinions: MyOpinion[] | null; failed: boolean }

/** The signed-in user's own ratings and comments (GET /me/opinions), loaded on login; `opinions` is null while loading or signed out. */
export function useMyOpinions(userId: string | undefined) {
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [version, setVersion] = useState(0)

  // A saved rating or comment refreshes the list.
  useEffect(() => {
    const bump = () => setVersion((v) => v + 1)
    window.addEventListener(OPINIONS_CHANGED, bump)
    return () => window.removeEventListener(OPINIONS_CHANGED, bump)
  }, [])

  useEffect(() => {
    if (!userId) return
    const controller = new AbortController()
    fetchMyOpinions(controller.signal)
      .then((opinions) => setLoaded({ userId, opinions, failed: false }))
      .catch(() => !controller.signal.aborted && setLoaded({ userId, opinions: null, failed: true }))
    return () => controller.abort()
  }, [userId, version])

  // What was loaded for another user (or before signing out) is not shown.
  const current = loaded && loaded.userId === userId ? loaded : null
  return { opinions: current?.opinions ?? null, failed: current?.failed ?? false }
}
