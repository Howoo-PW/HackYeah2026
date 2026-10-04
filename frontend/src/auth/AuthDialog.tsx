import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { supabase } from '../lib/supabase'

type Mode = 'login' | 'register'

/** Translates the most common Supabase Auth errors; falls back to the original message. */
function polishError(message: string): string {
  const m = message.toLowerCase()
  if (m.includes('invalid login credentials')) return 'Nieprawidłowy e-mail lub hasło.'
  if (m.includes('email not confirmed')) return 'Potwierdź adres e-mail (link w wiadomości), a potem zaloguj się.'
  if (m.includes('already registered')) return 'Konto z takim adresem e-mail już istnieje.'
  if (m.includes('password should be at least')) return 'Hasło musi mieć co najmniej 6 znaków.'
  if (m.includes('rate limit')) return 'Za dużo prób. Spróbuj ponownie za chwilę.'
  return message
}

/** Modal with e-mail + password login and registration (Supabase Auth). */
export default function AuthDialog({ onClose }: { onClose: () => void }) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!supabase) return
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      if (mode === 'login') {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) setError(polishError(error.message))
        // On success AuthProvider closes the dialog from onAuthStateChange.
      } else {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { display_name: displayName.trim() || email.split('@')[0] } },
        })
        if (error) setError(polishError(error.message))
        else if (!data.session) setInfo('Konto utworzone. Sprawdź skrzynkę i potwierdź adres e-mail, potem się zaloguj.')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nie udało się połączyć z serwerem logowania.')
    } finally {
      setBusy(false)
    }
  }

  const inputClass =
    'mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div role="dialog" aria-modal="true" aria-labelledby="auth-title" className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl">
        <div className="flex items-start justify-between">
          <h2 id="auth-title" className="text-lg font-bold">
            {mode === 'login' ? 'Zaloguj się' : 'Załóż konto'}
          </h2>
          <button onClick={onClose} aria-label="Zamknij" className="rounded-full p-1.5 text-gray-500 hover:bg-gray-100">
            ✕
          </button>
        </div>

        {!supabase ? (
          <p className="mt-4 text-sm text-red-600">
            Logowanie niedostępne: brak VITE_SUPABASE_URL lub VITE_SUPABASE_ANON_KEY w pliku .env.
          </p>
        ) : (
          <form onSubmit={submit} className="mt-4 space-y-3">
            {mode === 'register' && (
              <label className="block text-sm font-medium">
                Nazwa użytkownika
                <input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  maxLength={40}
                  autoComplete="nickname"
                  className={inputClass}
                  placeholder="np. Ania"
                />
              </label>
            )}
            <label className="block text-sm font-medium">
              E-mail
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                className={inputClass}
              />
            </label>
            <label className="block text-sm font-medium">
              Hasło
              <input
                type="password"
                required
                minLength={mode === 'login' ? undefined : 6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                className={inputClass}
              />
            </label>

            {error && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</p>}
            {info && <p className="rounded-lg bg-emerald-50 p-2 text-sm text-emerald-800">{info}</p>}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-gray-900 py-2 text-sm font-semibold text-white transition hover:bg-gray-700 disabled:opacity-50"
            >
              {busy ? 'Chwileczkę…' : mode === 'login' ? 'Zaloguj' : 'Załóż konto'}
            </button>

            <p className="text-center text-sm text-gray-600">
              {mode === 'login' ? 'Nie masz konta?' : 'Masz już konto?'}{' '}
              <button
                type="button"
                onClick={() => {
                  setMode(mode === 'login' ? 'register' : 'login')
                  setError(null)
                  setInfo(null)
                }}
                className="font-semibold text-sky-700 hover:underline"
              >
                {mode === 'login' ? 'Zarejestruj się' : 'Zaloguj się'}
              </button>
            </p>
          </form>
        )}
      </div>
    </div>
  )
}
