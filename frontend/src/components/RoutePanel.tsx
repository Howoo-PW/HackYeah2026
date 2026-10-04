import { useEffect, useRef, useState } from 'react'
import type { Dimension, Place, RouteProfile, RouteResult } from '../api/types'
import { ROUTE_DIMENSIONS, scoreColor } from '../lib/dimensions'
import { locateUser } from '../lib/geolocation'
import { activePoint, buildRouteRequest, getPoint, MAX_STOPS } from '../routing/useRouteDraft'
import type { PointKey, RouteDraftApi } from '../routing/useRouteDraft'
import type { RoutePlanApi } from '../routing/useRoutePlan'
import SearchBox from './SearchBox'

const ICON_PROPS = { width: 28, height: 28, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinejoin: 'round', strokeLinecap: 'round' } as const

/** Travel profiles shown as icon buttons (car, bike, pedestrian); `label` is the tooltip and screen-reader name. */
const PROFILES: { id: RouteProfile; label: string; icon: React.ReactNode }[] = [
  {
    id: 'driving-car',
    label: 'Auto',
    icon: (
      <svg {...ICON_PROPS} aria-hidden>
        <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2" />
        <circle cx="7" cy="17" r="2" />
        <path d="M9 17h6" />
        <circle cx="17" cy="17" r="2" />
      </svg>
    ),
  },
  {
    id: 'cycling-regular',
    label: 'Rower',
    icon: (
      <svg {...ICON_PROPS} aria-hidden>
        <circle cx="18.5" cy="17.5" r="3.5" />
        <circle cx="5.5" cy="17.5" r="3.5" />
        <circle cx="15" cy="5" r="1" />
        <path d="M12 17.5V14l-3-3 4-3 2 3h2" />
      </svg>
    ),
  },
  {
    id: 'foot-walking',
    label: 'Pieszo',
    icon: (
      <svg {...ICON_PROPS} aria-hidden>
        <circle cx="12" cy="5" r="1" />
        <path d="m9 20 3-6 3 6M6 8l6 2 6-2M12 10v4" />
      </svg>
    ),
  },
]

/** Three slider positions and the contract weight (0–3) each one stands for. */
const LEVELS = [
  { text: 'Nieważne', weight: 0 },
  { text: 'Ważne', weight: 2 },
  { text: 'Bardzo ważne', weight: 3 },
] as const

/** Slider position for a weight; weight 1 (not offered here) shows as the middle step. */
const positionOf = (weight: number) => (weight === 0 ? 0 : weight >= 3 ? 2 : 1)

type Props = {
  route: RouteDraftApi
  plan: RoutePlanApi
  /** The assistant's reply when this route came from it; shown above the points. */
  note?: string | null
  onDismissNote?: () => void
  /** Opens the assistant again (with the previous question) when the user is not happy with its route. */
  onAskAgain?: () => void
  onBack: () => void
}

/**
 * Left panel in route mode (opened with "Trasa" on a place card): start, optional stops and destination
 * (searched by street name or picked on the map), travel profile and optional requirements for road quality.
 * "Wyznacz trasę" asks the backend (POST /route) and lists the alternatives; the selected one is drawn on the map.
 */
export default function RoutePanel({ route, plan, note, onDismissNote, onAskAgain, onBack }: Props) {
  const { draft, error } = route
  const request = buildRouteRequest(draft)
  const active = activePoint(draft)

  return (
    <section className="pointer-events-auto max-h-[calc(100dvh-1.5rem)] w-full overflow-y-auto rounded-2xl bg-white shadow-xl ring-1 ring-black/5">
      <header className="flex items-center gap-2 border-b border-gray-100 px-3 py-2.5">
        <button
          onClick={onBack}
          aria-label="Wróć do mapy"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-gray-700 hover:bg-gray-100"
        >
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 className="text-base font-bold">Wyznacz trasę</h1>
      </header>

      <div className="p-3">
        {note && (
          <div className="mb-3 rounded-xl border border-violet-100 bg-violet-50/60 p-3">
            <div className="flex items-start justify-between gap-2">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-violet-900">
                <span className="rounded bg-violet-600 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">AI</span>
                Asystent
              </p>
              {onDismissNote && (
                <button onClick={onDismissNote} aria-label="Ukryj odpowiedź asystenta" className="rounded-full px-1.5 text-gray-500 hover:bg-violet-100">
                  ✕
                </button>
              )}
            </div>
            <p className="mt-1.5 whitespace-pre-line text-sm text-gray-900">{note}</p>
            {onAskAgain && (
              <button onClick={onAskAgain} className="mt-2 rounded-full bg-violet-700 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-violet-800">
                Zapytaj ponownie
              </button>
            )}
          </div>
        )}
        <div className="space-y-1.5">
          <PointRow label="A" placeholder="Wybierz punkt początkowy" color="bg-emerald-600" pointKey="a" route={route} active={active === 'a'} />

          {draft.stops.map((_, i) => (
            <PointRow
              key={i}
              label={String(i + 1)}
              placeholder={`Przystanek ${i + 1}`}
              color="bg-amber-600"
              pointKey={i}
              route={route}
              active={active === i}
              onRemove={() => route.removeStop(i)}
            />
          ))}

          <div className="flex items-center justify-between px-1">
            {draft.stops.length < MAX_STOPS ? (
              <button onClick={route.addStop} className="rounded-full px-2.5 py-1 text-sm font-medium text-sky-700 transition hover:bg-sky-50">
                ＋ Dodaj przystanek
              </button>
            ) : (
              <span className="px-2.5 text-xs text-gray-600">Maksymalnie {MAX_STOPS} przystanki</span>
            )}
            <button
              onClick={route.swap}
              disabled={!draft.a && !draft.b}
              aria-label="Zamień start i cel"
              className="rounded-full px-2.5 py-1 text-sm text-gray-600 transition hover:bg-gray-100 disabled:opacity-30"
            >
              ⇅ Zamień
            </button>
          </div>

          <PointRow label="B" placeholder="Wybierz cel" color="bg-rose-600" pointKey="b" route={route} active={active === 'b'} />
        </div>

        {error && <p className="mt-2 rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</p>}

        <SectionTitle className="mt-4">Jak podróżujesz</SectionTitle>
        <div className="mt-1.5 grid grid-cols-3 gap-1" role="radiogroup" aria-label="Środek transportu">
          {PROFILES.map((p) => (
            <button
              key={p.id}
              role="radio"
              aria-checked={draft.profile === p.id}
              aria-label={p.label}
              title={p.label}
              onClick={() => route.setProfile(p.id)}
              className={`flex items-center justify-center rounded-xl py-2.5 transition ${
                draft.profile === p.id ? 'bg-gray-900 text-white shadow' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {p.icon}
            </button>
          ))}
        </div>

        <SectionTitle className="mt-4">Wymagania</SectionTitle>
        <ul className="mt-1.5 space-y-3">
          {ROUTE_DIMENSIONS.map((d) => (
            <li key={d.id}>
              <RequirementSlider
                label={d.label}
                value={draft.weights[d.id]}
                onChange={(v) => route.setWeight(d.id as Dimension, v)}
              />
            </li>
          ))}
        </ul>

        <button
          onClick={plan.run}
          disabled={request === null || plan.status === 'loading'}
          title={request === null ? 'Ustaw punkt początkowy i cel' : undefined}
          className="mt-4 w-full rounded-xl bg-gray-900 py-2.5 text-sm font-semibold text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {plan.status === 'loading' ? 'Szukam trasy…' : 'Wyznacz trasę'}
        </button>

        <RouteResults plan={plan} scrollToResults={!note} />
      </div>
    </section>
  )
}

function SectionTitle({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <h2 className={`px-1 text-[11px] font-semibold uppercase tracking-wider text-gray-700 ${className}`}>{children}</h2>
}

type RowProps = {
  label: string
  placeholder: string
  color: string
  pointKey: PointKey
  route: RouteDraftApi
  active: boolean
  /** Only stops can be removed; A and B always stay. */
  onRemove?: () => void
}

/** One point (A, a stop or B): street search field plus "pick on map" and "my location". */
function PointRow({ label, placeholder, color, pointKey, route, active, onRemove }: RowProps) {
  const [locating, setLocating] = useState(false)
  const place = getPoint(route.draft, pointKey)

  const useMyLocation = async () => {
    setLocating(true)
    try {
      const { lat, lon } = await locateUser()
      route.place(pointKey, { lat, lon, name: 'Moja lokalizacja', detail: null, bounds: null })
    } catch (err) {
      route.setError(err instanceof Error ? err.message : 'Nie udało się pobrać lokalizacji.')
    } finally {
      setLocating(false)
    }
  }

  return (
    <div className={`rounded-xl border p-2 transition ${active ? 'border-gray-900 bg-gray-50' : 'border-gray-200'}`}>
      <div className="flex items-center gap-2">
        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white ${color}`}>
          {label}
        </span>
        <div className="min-w-0 flex-1">
          {/* Remounted when the place changes, so the text always shows the chosen street. */}
          <SearchBox
            key={place ? `${place.name}|${place.lat}|${place.lon}` : 'empty'}
            initialText={place?.name ?? ''}
            placeholder={placeholder}
            onPick={(p: Place) => route.place(pointKey, p)}
            onClear={() => route.clearPoint(pointKey)}
          />
        </div>
        {onRemove && (
          <button
            onClick={onRemove}
            aria-label={`Usuń przystanek ${label}`}
            title="Usuń"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-red-600 transition hover:bg-red-50"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6" />
            </svg>
          </button>
        )}
      </div>
      {place?.detail && <p className="mt-0.5 truncate pl-9 pr-1 text-xs text-gray-600">{place.detail}</p>}
      <div className="mt-2 flex gap-1.5 pl-9 text-xs">
        <button
          onClick={() => route.startPicking(pointKey)}
          className={`rounded-full px-2.5 py-1 font-medium transition ${
            active ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          {active ? '📍 Kliknij na mapie' : '📍 Wskaż na mapie'}
        </button>
        <button
          onClick={useMyLocation}
          disabled={locating}
          className="rounded-full bg-gray-100 px-2.5 py-1 font-medium text-gray-700 transition hover:bg-gray-200 disabled:opacity-50"
        >
          {locating ? 'Szukam…' : '◎ Moja lokalizacja'}
        </button>
      </div>
    </div>
  )
}

/** Thick snapping slider with three steps (not important / important / very important). */
function RequirementSlider({
  label,
  value,
  onChange,
}: {
  label: string
  /** Contract weight 0–3. */
  value: number
  onChange: (weight: 0 | 1 | 2 | 3) => void
}) {
  const position = positionOf(value)
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className={position === 0 ? 'text-gray-600' : 'font-semibold text-gray-900'}>{LEVELS[position].text}</span>
      </div>
      <input
        type="range"
        min={0}
        max={2}
        step={1}
        value={position}
        onChange={(e) => onChange(LEVELS[Number(e.target.value)].weight)}
        aria-label={`Ważność: ${label}`}
        aria-valuetext={LEVELS[position].text}
        className="req-slider mt-2"
        style={{ '--fill': `${position * 50}%` } as React.CSSProperties}
      />
      <div className="mt-1 flex justify-between text-[11px] text-gray-600" aria-hidden>
        {LEVELS.map((l) => (
          <span key={l.text}>{l.text}</span>
        ))}
      </div>
    </div>
  )
}

function formatDuration(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60))
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

function formatDistance(meters: number): string {
  return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1).replace('.', ',')} km`
}

/** Loading / error / the routes. Picking a card selects the route drawn on the map. */
/** `scrollToResults` is off when the assistant's note is shown, so that the note at the top stays in view. */
function RouteResults({ plan, scrollToResults }: { plan: RoutePlanApi; scrollToResults: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (scrollToResults && plan.status === 'done') ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [plan.status, scrollToResults])

  if (plan.status === 'idle') return null
  if (plan.status === 'loading') return <p className="mt-3 text-sm text-gray-700">Szukam najlepszej trasy…</p>
  if (plan.status === 'error') return <p className="mt-3 rounded-lg bg-red-50 p-2 text-sm text-red-700">{plan.error}</p>

  // rank 1 = best for the chosen requirements, rank 2 = the fastest (only when it is a different route)
  const best = plan.routes.find((r) => r.rank === 1)
  const fastest = plan.routes.find((r) => r.rank === 2)
  const unrated = plan.routes.every((r) => r.coverage === 0)
  return (
    <div ref={ref} className="mt-4">
      <SectionTitle>{plan.routes.length > 1 ? 'Propozycje tras' : 'Trasa'}</SectionTitle>
      <ul className="mt-1.5 space-y-1.5">
        {plan.routes.map((r, i) => (
          <li key={i}>
            <RouteCard
              route={r}
              selected={i === plan.selected}
              label={r.rank === 2 ? 'Najszybsza' : fastest ? 'Najlepsza dla Ciebie' : 'Najszybsza'}
              cost={r === best && fastest ? { seconds: r.duration_s - fastest.duration_s, meters: r.distance_m - fastest.distance_m } : null}
              onSelect={() => plan.select(i)}
            />
          </li>
        ))}
      </ul>
      {unrated && (
        <p className="mt-2 text-xs text-gray-600">
          Na tych trasach nie ma jeszcze ocen użytkowników, więc trasa wynika głównie z typu i jakości dróg w danych.
        </p>
      )}
    </div>
  )
}

function RouteCard({
  route,
  selected,
  label,
  cost,
  onSelect,
}: {
  route: RouteResult
  selected: boolean
  label: string
  /** How much longer/farther this route is than the fastest one (only for the "best for you" route). */
  cost: { seconds: number; meters: number } | null
  onSelect: () => void
}) {
  return (
    <button
      onClick={onSelect}
      aria-pressed={selected}
      className={`w-full rounded-xl border p-3 text-left transition ${selected ? 'border-blue-600 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-lg font-bold">{formatDuration(route.duration_s)}</span>
        <span className="text-sm text-gray-700">{formatDistance(route.distance_m)}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-gray-700">
        <span className="font-semibold text-blue-700">{label}</span>
        {cost && (cost.seconds > 0 || cost.meters > 0) && (
          <span>
            +{formatDuration(Math.max(0, cost.seconds))}, +{formatDistance(Math.max(0, cost.meters))} względem najszybszej
          </span>
        )}
        <span>{route.score !== null ? `★ ${route.score.toFixed(1)}` : 'brak ocen na trasie'}</span>
        {route.score !== null && <span>oceny na {Math.round(route.coverage * 100)}% trasy</span>}
      </div>
      {selected && route.score !== null && (
        <ul className="mt-2 space-y-1.5">
          {ROUTE_DIMENSIONS.map((d) => {
            const v = route.scores[d.id]
            return (
              <li key={d.id} className="text-xs">
                <div className="flex justify-between">
                  <span>{d.label}</span>
                  <span className="font-semibold">{v === null ? '–' : v.toFixed(1)}</span>
                </div>
                <div className="mt-0.5 h-1.5 rounded-full bg-gray-200">
                  <div className="h-1.5 rounded-full" style={{ width: `${v === null ? 0 : (v / 5) * 100}%`, background: scoreColor(v) }} />
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </button>
  )
}
