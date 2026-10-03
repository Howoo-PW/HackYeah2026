import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiRequestError, postComment } from '../api/client'
import type { Opinion } from '../api/types'
import { displayNameOf } from '../auth/authContext'
import { useAuth } from '../auth/useAuth'

const MAX_LENGTH = 1000 // contract: comment text 1–1000 characters

/** "Add your opinion" box above the opinions list. Asks to log in when needed. */
export default function CommentForm({ segmentId, onPosted }: { segmentId: number; onPosted: (o: Opinion) => void }) {
  const { user, openLogin, configured } = useAuth()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!user) {
    return (
      <button
        onClick={openLogin}
        disabled={!configured}
        className="mt-3 w-full rounded-xl border border-dashed border-gray-300 py-2 text-sm font-medium text-gray-700 transition hover:border-gray-900 hover:bg-gray-50 disabled:opacity-50"
      >
        Zaloguj się, aby dodać opinię
      </button>
    )
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const trimmed = text.trim()
    if (!trimmed) return
    setBusy(true)
    setError(null)
    try {
      const created = await postComment(segmentId, trimmed, { id: user.id, display_name: displayNameOf(user) })
      onPosted(created)
      setText('')
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) openLogin()
      setError(err instanceof Error ? err.message : 'Nie udało się dodać opinii.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="mt-3">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={MAX_LENGTH}
        rows={3}
        placeholder="Napisz, jak się tędy jeździ lub chodzi…"
        aria-label="Twoja opinia"
        className="w-full resize-y rounded-xl border border-gray-300 p-2.5 text-sm outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900"
      />
      {error && <p className="mt-1 rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <div className="mt-1 flex items-center justify-between">
        <span className="text-xs text-gray-400">
          {text.length}/{MAX_LENGTH}
        </span>
        <button
          type="submit"
          disabled={busy || !text.trim()}
          className="rounded-lg bg-gray-900 px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-gray-700 disabled:opacity-40"
        >
          {busy ? 'Wysyłam…' : 'Opublikuj'}
        </button>
      </div>
    </form>
  )
}
