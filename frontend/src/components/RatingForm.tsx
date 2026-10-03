import { useState } from 'react'
import { ApiRequestError, postRating } from '../api/client'
import type { Dimension, Rating, TimeOfDay } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { DIMENSIONS } from '../lib/dimensions'

const TIMES: { id: TimeOfDay | 'auto'; label: string }[] = [
  { id: 'auto', label: 'Teraz (automatycznie)' },
  { id: 'morning', label: 'Rano (6–10)' },
  { id: 'day', label: 'W ciągu dnia (10–16)' },
  { id: 'evening', label: 'Wieczorem (16–22)' },
  { id: 'night', label: 'W nocy (22–6)' },
]

type Values = Record<Dimension, number | null>

function emptyValues(existing: Rating | null): Values {
  return {
    surface: existing?.surface ?? null,
    views: existing?.views ?? null,
    safety: existing?.safety ?? null,
    traffic: existing?.traffic ?? null,
    parking: existing?.parking ?? null,
  }
}

type Props = {
  segmentId: number
  /** The user's current rating of this segment, if any (a new one the same day replaces it). */
  existing: Rating | null
  onSaved: (rating: Rating) => void
}

/** Collapsible "rate this road" card: 1–5 stars per dimension (each optional, at least one required). */
export default function RatingForm({ segmentId, existing, onSaved }: Props) {
  const { user, openLogin, configured } = useAuth()
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState<Values>(() => emptyValues(existing))
  const [time, setTime] = useState<TimeOfDay | 'auto'>('auto')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const filled = Object.values(values).some((v) => v !== null)

  if (!user) {
    return (
      <button
        onClick={openLogin}
        disabled={!configured}
        className="mt-4 w-full rounded-xl border border-dashed border-gray-300 py-2.5 text-sm font-medium text-gray-700 transition hover:border-gray-900 hover:bg-gray-50 disabled:opacity-50"
      >
        ★ Zaloguj się, aby ocenić tę drogę
      </button>
    )
  }

  if (!open) {
    return (
      <button
        onClick={() => {
          setValues(emptyValues(existing))
          setSaved(false)
          setOpen(true)
        }}
        className="mt-4 w-full rounded-xl bg-gray-900 py-2.5 text-sm font-semibold text-white transition hover:bg-gray-700"
      >
        {existing ? '✎ Zmień swoją ocenę' : '★ Oceń tę drogę'}
      </button>
    )
  }

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const rating = await postRating(segmentId, { ...values, ...(time === 'auto' ? {} : { time_of_day: time }) })
      onSaved(rating)
      setSaved(true)
      setOpen(false)
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) openLogin()
      setError(err instanceof Error ? err.message : 'Nie udało się zapisać oceny.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mt-4 rounded-xl border border-gray-200 p-3">
      <h3 className="text-sm font-semibold">Twoja ocena</h3>
      <ul className="mt-2 space-y-2">
        {DIMENSIONS.map((d) => (
          <li key={d.id} className="flex items-center justify-between gap-2 text-sm">
            <span>{d.label}</span>
            <StarPicker
              label={d.label}
              value={values[d.id]}
              onChange={(v) => setValues((cur) => ({ ...cur, [d.id]: v }))}
            />
          </li>
        ))}
      </ul>
      <p className="mt-1 text-[11px] text-gray-400">5 = najlepiej (przy obciążeniu: 5 = płynnie, bez problemów). Kliknij gwiazdkę ponownie, żeby wyczyścić.</p>

      <label className="mt-3 block text-sm">
        <span className="text-gray-600">Pora dnia</span>
        <select
          value={time}
          onChange={(e) => setTime(e.target.value as TimeOfDay | 'auto')}
          className="mt-1 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
        >
          {TIMES.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </label>

      {error && <p className="mt-2 rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</p>}

      <div className="mt-3 flex gap-2">
        <button
          onClick={submit}
          disabled={!filled || busy}
          className="flex-1 rounded-lg bg-gray-900 py-2 text-sm font-semibold text-white transition hover:bg-gray-700 disabled:opacity-40"
        >
          {busy ? 'Zapisuję…' : 'Zapisz ocenę'}
        </button>
        <button onClick={() => setOpen(false)} className="rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-100">
          Anuluj
        </button>
      </div>
      {saved && <span className="sr-only">Zapisano</span>}
    </section>
  )
}

/** 1–5 clickable stars; clicking the selected value clears it (rating a dimension is optional). */
function StarPicker({ label, value, onChange }: { label: string; value: number | null; onChange: (v: number | null) => void }) {
  const [hover, setHover] = useState<number | null>(null)
  const shown = hover ?? value ?? 0
  return (
    <span className="flex" role="radiogroup" aria-label={`Ocena: ${label}`} onMouseLeave={() => setHover(null)}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} z 5`}
          onMouseEnter={() => setHover(n)}
          onClick={() => onChange(value === n ? null : n)}
          className={`px-0.5 text-2xl leading-none transition ${n <= shown ? 'text-amber-400' : 'text-gray-300'}`}
        >
          ★
        </button>
      ))}
    </span>
  )
}
