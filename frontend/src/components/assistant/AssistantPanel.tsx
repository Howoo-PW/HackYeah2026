import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { ApiRequestError, askAssistant } from '../../api/client'
import type { AssistantResponse, AssistantStreet } from '../../api/types'

const EXAMPLES = [
  'Rowerem z Rynku Głównego na Wawel, ładne widoki',
  'Najlepsza nawierzchnia na Podgórzu',
  'Pokaż Lokum Salsa',
]

type Props = {
  /** Text to start with (e.g. the previous question when the user asks again). */
  initialQuery?: string
  /** Called with the typed question each time one is sent, so it can be offered again later. */
  onQuery?: (query: string) => void
  /** Called with every answer so the app can show the route, the place or the streets on the map. */
  onResult: (result: AssistantResponse) => void
  /** Opens one of the streets the assistant found (its details and the map). */
  onOpenStreet: (street: AssistantStreet) => void
  onClose: () => void
}

function errorText(err: unknown): string {
  if (err instanceof ApiRequestError) {
    if (err.status === 429) return 'Za dużo pytań naraz. Poczekaj chwilę i spróbuj ponownie.'
    if (err.status === 502) return 'Asystent AI jest chwilowo niedostępny. Spróbuj za moment.'
    if (err.status === 422) return 'Opis jest za krótki lub za długi (3 do 500 znaków).'
    return err.message
  }
  return 'Nie udało się zapytać asystenta.'
}

/**
 * "Asystent AI": describe a route or a place in your own words. The answer is built from the ratings, comments and
 * obstacles in the database; a route opens in the route planner, a place on the map, streets as numbered pins.
 */
export default function AssistantPanel({ initialQuery = '', onQuery, onResult, onOpenStreet, onClose }: Props) {
  const [query, setQuery] = useState(initialQuery)
  const [result, setResult] = useState<AssistantResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const ctrl = useRef<AbortController | null>(null)

  useEffect(() => () => ctrl.current?.abort(), [])

  const ask = async (text: string) => {
    const q = text.trim()
    if (q.length < 3 || busy) return
    onQuery?.(q)
    ctrl.current?.abort()
    const c = new AbortController()
    ctrl.current = c
    setBusy(true)
    setError(null)
    try {
      const res = await askAssistant(q, c.signal)
      if (c.signal.aborted) return
      setResult(res)
      onResult(res)
    } catch (err) {
      if (!c.signal.aborted) setError(errorText(err))
    } finally {
      if (!c.signal.aborted) setBusy(false)
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      ask(query)
    }
  }

  return (
    <section className="pointer-events-auto max-h-[calc(100dvh-9rem)] w-full overflow-y-auto rounded-2xl bg-white shadow-xl ring-1 ring-black/5">
      <header className="flex items-center justify-between border-b border-gray-100 px-4 py-2.5">
        <h1 className="flex items-center gap-2 text-base font-bold">
          <span className="rounded bg-violet-600 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">AI</span>
          Asystent
        </h1>
        <button onClick={onClose} aria-label="Zamknij asystenta" className="rounded-full p-1.5 text-gray-500 hover:bg-gray-100">
          ✕
        </button>
      </header>

      <div className="p-3">
        <label className="block text-sm font-medium text-gray-800" htmlFor="assistant-query">
          Opisz trasę lub miejsce
        </label>
        <textarea
          id="assistant-query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          maxLength={500}
          rows={3}
          placeholder="np. Spokojna trasa rowerowa z Dietla na Nową Hutę, bez dziur"
          className="mt-1.5 w-full resize-none rounded-xl border border-gray-300 p-2.5 text-sm outline-none placeholder:text-gray-500 focus:border-gray-900 focus:ring-1 focus:ring-gray-900"
        />
        <button
          onClick={() => ask(query)}
          disabled={busy || query.trim().length < 3}
          className="mt-2 w-full rounded-xl bg-violet-700 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? 'Analizuję opis…' : 'Zapytaj'}
        </button>

        {!result && !busy && (
          <div className="mt-3">
            <p className="px-1 text-[11px] font-semibold uppercase tracking-wider text-gray-700">Na przykład</p>
            <ul className="mt-1.5 space-y-1.5">
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button
                    onClick={() => {
                      setQuery(example)
                      ask(example)
                    }}
                    className="w-full rounded-lg bg-gray-100 px-3 py-2 text-left text-sm text-gray-800 transition hover:bg-gray-200"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {busy && (
          <p className="mt-3 flex items-center gap-2 text-sm text-gray-700" role="status">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-violet-700" aria-hidden />
            Rozumiem opis, wyznaczam trasę i sprawdzam opinie. To potrwa kilka sekund.
          </p>
        )}

        {error && <p className="mt-3 rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</p>}

        {result && !busy && <Answer result={result} onOpenStreet={onOpenStreet} />}
      </div>
    </section>
  )
}

function Answer({ result, onOpenStreet }: { result: AssistantResponse; onOpenStreet: (s: AssistantStreet) => void }) {
  const found = result.intent !== 'clarify'
  return (
    <div className={`mt-3 rounded-xl p-3 ${found ? 'border border-violet-100 bg-violet-50/60' : 'bg-gray-50'}`}>
      {found && result.interpretation && <p className="text-xs text-gray-600">Rozumiem: {result.interpretation}</p>}
      <p className="mt-1 whitespace-pre-line text-sm text-gray-900">{result.answer}</p>

      {result.intent === 'route' && <p className="mt-2 text-xs text-gray-600">Trasa jest w planerze: możesz zmienić punkty i wymagania.</p>}
      {result.intent === 'place' && <p className="mt-2 text-xs text-gray-600">Miejsce zaznaczone na mapie.</p>}

      {result.streets.length > 0 && (
        <ol className="mt-2 space-y-1.5">
          {result.streets.map((street, i) => (
            <li key={street.group_id}>
              <button
                onClick={() => onOpenStreet(street)}
                className="flex w-full items-center gap-2 rounded-lg bg-white px-2.5 py-2 text-left text-sm shadow-sm ring-1 ring-black/5 transition hover:bg-gray-50"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-violet-700 text-xs font-bold text-white">{i + 1}</span>
                <span className="min-w-0 flex-1 truncate font-medium">{street.name}</span>
                <span className="shrink-0 text-xs text-gray-600">{Math.round(street.length_m)} m</span>
              </button>
            </li>
          ))}
        </ol>
      )}

      {found && result.model && <p className="mt-2 text-[11px] text-gray-500">Odpowiedź wygenerowana automatycznie na podstawie ocen i komentarzy ({result.model}).</p>}
    </div>
  )
}
