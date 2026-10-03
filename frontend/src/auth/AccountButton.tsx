import { displayNameOf } from './authContext'
import { useAuth } from './useAuth'

/** Login button, or the user's name with a logout button. Lives in the header of the left panel. */
export default function AccountButton() {
  const { user, loading, openLogin, signOut } = useAuth()
  if (loading) return null

  if (!user) {
    return (
      <button
        onClick={openLogin}
        className="shrink-0 rounded-full border border-white/40 px-3 py-1 text-xs font-semibold text-white transition hover:bg-white/15"
      >
        Zaloguj
      </button>
    )
  }

  return (
    <div className="flex min-w-0 shrink-0 items-center gap-2 text-xs text-white">
      <span className="max-w-24 truncate font-semibold" title={user.email ?? undefined}>
        {displayNameOf(user)}
      </span>
      <button onClick={signOut} className="rounded-full border border-white/40 px-2.5 py-1 transition hover:bg-white/15">
        Wyloguj
      </button>
    </div>
  )
}
