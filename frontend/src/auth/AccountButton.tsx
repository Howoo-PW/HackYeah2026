import { useEffect, useRef, useState } from 'react'
import type { MyOpinion } from '../api/types'
import MyRoadsList from './MyRoadsList'
import { displayNameOf } from './authContext'
import { useAuth } from './useAuth'

const ICON = { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' } as const

/**
 * Round account button: a person icon to log in, or the user's initial that opens a menu with the user's rated roads
 * (`onOpenSegment` shows one on the map), the "Tylko moje oceny" map filter and logout. Sits in the top-right pill.
 */
export default function AccountButton({
  opinions,
  failed,
  onOpenSegment,
  mineOnly,
  onToggleMine,
}: {
  opinions: MyOpinion[] | null
  failed: boolean
  onOpenSegment: (segmentId: number) => void
  /** Map limited to the user's own roads. */
  mineOnly: boolean
  onToggleMine: () => void
}) {
  const { user, loading, openLogin, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  // Close the menu on a click outside it or on Escape.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (loading) return null

  if (!user) {
    return (
      <button
        onClick={openLogin}
        aria-label="Zaloguj"
        title="Zaloguj"
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gray-900 text-white transition hover:bg-gray-700"
      >
        <svg {...ICON} aria-hidden>
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" />
        </svg>
      </button>
    )
  }

  const name = displayNameOf(user)
  return (
    <div ref={root} className="relative shrink-0">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Konto: ${name}`}
        title={user.email ?? name}
        className={`flex h-10 w-10 items-center justify-center rounded-full bg-gray-900 text-base font-bold uppercase text-white transition hover:bg-gray-700 ${mineOnly ? "ring-2 ring-amber-400 ring-offset-2" : ""}`}
      >
        {name.charAt(0)}
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-12 w-80 max-w-[calc(100vw-1.5rem)] rounded-2xl bg-white p-2 shadow-xl ring-1 ring-black/5">
          <div className="px-3 py-2">
            <p className="truncate text-sm font-semibold text-gray-900">{name}</p>
            {user.email && <p className="truncate text-xs text-gray-600">{user.email}</p>}
          </div>
          <button
            role="menuitemcheckbox"
            aria-checked={mineOnly}
            onClick={onToggleMine}
            className={`mb-1 w-full rounded-full px-4 py-2 text-sm font-medium transition ${
              mineOnly ? 'bg-gray-900 text-white hover:bg-gray-700' : 'bg-gray-100 text-gray-800 hover:bg-gray-200'
            }`}
          >
            Tylko moje oceny
          </button>
          <MyRoadsList
            opinions={opinions}
            failed={failed}
            onOpen={(id) => {
              setOpen(false)
              onOpenSegment(id)
            }}
          />
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false)
              signOut()
            }}
            className="mt-1 flex w-full items-center gap-2 rounded-xl border-t border-gray-100 px-3 py-2 text-left text-sm font-medium text-gray-800 transition hover:bg-gray-100"
          >
            <svg {...ICON} width={18} height={18} aria-hidden>
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
            </svg>
            Wyloguj
          </button>
        </div>
      )}
    </div>
  )
}
