import { displayNameOf } from './authContext'
import { useAuth } from './useAuth'

/** Login button, or the user's name with a logout button. Sits in the top-right pill. */
export default function AccountButton() {
  const { user, loading, openLogin, signOut } = useAuth()
  if (loading) return null

  if (!user) {
    return (
      <button
        onClick={openLogin}
        className="shrink-0 rounded-full bg-gray-900 px-3 py-1 text-xs font-semibold text-white transition hover:bg-gray-700"
      >
        Zaloguj
      </button>
    )
  }

  return (
    <div className="flex min-w-0 shrink-0 items-center gap-2 text-xs text-gray-800">
      <span className="max-w-24 truncate font-semibold" title={user.email ?? undefined}>
        {displayNameOf(user)}
      </span>
      <button onClick={signOut} className="rounded-full border border-gray-300 px-2.5 py-1 transition hover:bg-gray-100">
        Wyloguj
      </button>
    </div>
  )
}
