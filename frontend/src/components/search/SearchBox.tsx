import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { searchPlaces, SearchError, suggestPlaces } from '../../api/geocode'
import type { Place } from '../../api/types'

type Props = {
  /** Text shown in the input at start (e.g. the name of an already chosen place). */
  initialText?: string
  placeholder: string
  onPick: (place: Place) => void
  /** Called when the user empties the field with the ✕ button. */
  onClear?: () => void
  autoFocus?: boolean
  /** `bar`: big floating search bar (Google Maps style); `field`: plain bordered input for forms. */
  variant?: 'bar' | 'field'
}

const MIN_CHARS = 2
/** Wait for a pause in typing before asking for suggestions (keeps the public service happy). */
const DEBOUNCE_MS = 250

/**
 * Street / address search with suggestions as you type (like Google Maps): ↑/↓ move through the list,
 * Enter picks the highlighted suggestion or runs a full search, Esc closes the list.
 */
export default function SearchBox({ initialText = '', placeholder, onPick, onClear, autoFocus, variant = 'field' }: Props) {
  const [text, setText] = useState(initialText)
  const [results, setResults] = useState<Place[] | null>(null)
  const [active, setActive] = useState(-1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [focused, setFocused] = useState(false)
  const ctrl = useRef<AbortController | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const listId = useId()

  useEffect(
    () => () => {
      ctrl.current?.abort()
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )

  /** Runs `fetcher` for `q`, dropping the answer if a newer request started meanwhile. */
  const load = async (q: string, fetcher: typeof suggestPlaces, quietErrors: boolean) => {
    ctrl.current?.abort()
    const c = new AbortController()
    ctrl.current = c
    setBusy(true)
    setError(null)
    try {
      const found = await fetcher(q, c.signal)
      setResults(found)
      setActive(-1)
      if (found.length === 0) setError('Nic nie znaleziono w Krakowie. Spróbuj innej nazwy.')
    } catch (err) {
      if (c.signal.aborted) return
      setResults(null)
      if (!quietErrors) setError(err instanceof SearchError ? err.message : 'Nie udało się wyszukać.')
    } finally {
      if (!c.signal.aborted) setBusy(false)
    }
  }

  const onChange = (value: string) => {
    setText(value)
    setError(null)
    if (timer.current) clearTimeout(timer.current)
    ctrl.current?.abort()
    const q = value.trim()
    if (q.length < MIN_CHARS) {
      setResults(null)
      setBusy(false)
      return
    }
    setBusy(true)
    timer.current = setTimeout(() => load(q, suggestPlaces, true), DEBOUNCE_MS)
  }

  const pick = (p: Place) => {
    if (timer.current) clearTimeout(timer.current)
    ctrl.current?.abort()
    setText(p.name)
    setResults(null)
    setError(null)
    setBusy(false)
    onPick(p)
  }

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    if (results && active >= 0) return pick(results[active])
    const q = text.trim()
    if (q.length < MIN_CHARS) {
      setError(`Wpisz co najmniej ${MIN_CHARS} znaki.`)
      return
    }
    if (timer.current) clearTimeout(timer.current)
    load(q, searchPlaces, false)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      setResults(null)
    } else if (e.key === 'ArrowDown' && results?.length) {
      e.preventDefault()
      setActive((i) => (i + 1) % results.length)
    } else if (e.key === 'ArrowUp' && results?.length) {
      e.preventDefault()
      setActive((i) => (i <= 0 ? results.length - 1 : i - 1))
    }
  }

  const clear = () => {
    if (timer.current) clearTimeout(timer.current)
    ctrl.current?.abort()
    setText('')
    setResults(null)
    setError(null)
    setBusy(false)
    onClear?.()
  }

  const bar = variant === 'bar'
  const open = focused && ((results && results.length > 0) || error)

  return (
    <div className={bar ? 'rounded-2xl bg-white shadow-xl ring-1 ring-black/5' : ''}>
      <form
        onSubmit={submit}
        role="search"
        className={`flex items-center gap-2 ${
          bar ? 'px-3 py-1.5' : 'rounded-lg border border-gray-300 bg-white px-2 py-1 focus-within:border-gray-900 focus-within:ring-1 focus-within:ring-gray-900'
        }`}
      >
        <input
          value={text}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={onKeyDown}
          autoFocus={autoFocus}
          placeholder={placeholder}
          aria-label={placeholder}
          role="combobox"
          aria-expanded={Boolean(open)}
          aria-controls={listId}
          aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          aria-autocomplete="list"
          autoComplete="off"
          className={`min-w-0 flex-1 bg-transparent outline-none placeholder:text-gray-500 ${bar ? 'py-2 text-base' : 'py-1 text-sm'}`}
        />
        {text && (
          <button type="button" onClick={clear} aria-label="Wyczyść" className="rounded-full p-1.5 text-gray-600 hover:bg-gray-100">
            ✕
          </button>
        )}
        <button type="submit" aria-label="Szukaj" className="rounded-full p-1.5 text-gray-600 transition hover:bg-gray-100">
          {busy ? <span className="block h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-gray-700" /> : <Magnifier />}
        </button>
      </form>

      {open && (
        <div className={bar ? 'border-t border-gray-100 py-1' : 'mt-1 rounded-lg border border-gray-200 bg-white py-1'}>
          {error && <p className="px-3 py-2 text-sm text-gray-600">{error}</p>}
          {results && results.length > 0 && (
            <ul id={listId} role="listbox" aria-label="Podpowiedzi">
              {results.map((p, i) => (
                <li key={`${p.lat},${p.lon},${i}`} id={`${listId}-${i}`} role="option" aria-selected={i === active}>
                  <button
                    type="button"
                    // keep focus in the input so the list does not close before the click registers
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => pick(p)}
                    onMouseEnter={() => setActive(i)}
                    className={`block w-full px-3 py-2 text-left transition ${i === active ? 'bg-gray-100' : 'hover:bg-gray-50'}`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">{p.name}</span>
                      {p.detail && <span className="block truncate text-xs text-gray-600">{p.detail}</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function Magnifier() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  )
}
