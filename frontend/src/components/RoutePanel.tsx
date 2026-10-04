import { useEffect, useRef, useState } from 'react'
import type { Dimension, Place, RouteProfile, RouteResult } from '../api/types'
import { ROUTE_DIMENSIONS, scoreColor } from '../lib/dimensions'
import { activePoint, buildRouteRequest, getPoint, MAX_STOPS } from '../routing/useRouteDraft'
import type { PointKey, RouteDraftApi } from '../routing/useRouteDraft'
import type { RoutePlanApi } from '../routing/useRoutePlan'
import SearchBox from './SearchBox'

const PROFILES: { id: RouteProfile; label: string }[] = [
  { id: 'driving-car', label: 'Auto'},
  { id: 'cycling-regular', label: 'Rower'},
  { id: 'foot-walking', label: 'Pieszo'},
]

/** Three slider positions and the contract weight (0–3) each one stands for. */
const LEVELS = [
  { text: 'Nieważne', weight: 0 },
  { text: 'Ważne', weight: 2 },
  { text: 'Bardzo ważne', weight: 3 },
] as const

/** Slider position for a weight; weight 1 (not offered here) shows as the middle step. */
const positionOf = (weight: number) => (weight === 0 ? 0 : weight >= 3 ? 2 : 1)

type Props = { route: RouteDraftApi; plan: RoutePlanApi; onBack: () => void }

/**
 * Left panel in route mode (opened with "Trasa" on a place card): start, optional stops and destination
 * (searched by street name or picked on the map), travel profile and optional requirements for road quality.
 * "Wyznacz trasę" asks the backend (POST /route) and lists the alternatives; the selected one is drawn on the map.
 */
export default function RoutePanel({ route, plan, onBack }: Props) {
  const { draft, error } = route
  const request = buildRouteRequest(draft)
  const active = activePoint(draft)

  return (
    <section className="pointer-events-auto max-h-[calc(100dvh-1.5rem)] w-full overflow-y-auto rounded-2xl bg-white shadow-xl ring-1 ring-black/5">
      <header className="flex items-center gap-2 border-b border-gray-100 px-3 py-2.5">
        <button onClick={onBack} aria-label="Wróć do mapy" className="rounded-full p-1.5 text-lg text-gray-700 hover:bg-gray-100">
          ←
        </button>
        <h1 className="text-base font-bold">Wyznacz trasę</h1>
      </header>

      <div className="p-3">
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
              onClick={() => route.setProfile(p.id)}
              className={`rounded-xl py-2.5 text-sm font-medium transition ${
                draft.profile === p.id ? 'bg-gray-900 text-white shadow' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <SectionTitle className="mt-4">Wymagania</SectionTitle>
        <ul className="mt-1.5 space-y-3">
          {ROUTE_DIMENSIONS.map((d) => (
            <li key={d.id}>
              <RequirementSlider
                label={d.label}
                hint={`unikaj: ${d.low}`}
                value={draft.weights[d.id]}
                onChange={(v) => route.setWeight(d.id as Dimension, v)}
              />
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] text-gray-600">Wszystko na „Nieważne” oznacza po prostu najszybszą trasę.</p>

        <button
          onClick={plan.run}
          disabled={request === null || plan.status === 'loading'}
          title={request === null ? 'Ustaw punkt początkowy i cel' : undefined}
          className="mt-4 w-full rounded-xl bg-gray-900 py-2.5 text-sm font-semibold text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {plan.status === 'loading' ? 'Szukam trasy…' : 'Wyznacz trasę'}
        </button>

        <RouteResults plan={plan} />
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

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      route.setError('Ta przeglądarka nie udostępnia lokalizacji.')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        route.place(pointKey, { lat: pos.coords.latitude, lon: pos.coords.longitude, name: 'Moja lokalizacja', detail: null, bounds: null })
      },
      () => {
        setLocating(false)
        route.setError('Nie udało się pobrać lokalizacji. Sprawdź zgodę w przeglądarce.')
      },
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  return (
    <div className={`rounded-xl border p-2 transition ${active ? 'border-gray-900 bg-gray-50' : 'border-gray-200'}`}>
      <div className="flex items-start gap-2">
        <span className={`mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white ${color}`}>
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
          {place?.detail && <p className="mt-0.5 truncate px-1 text-xs text-gray-600">{place.detail}</p>}
        </div>
        {onRemove && (
          <button onClick={onRemove} aria-label={`Usuń przystanek ${label}`} className="mt-1 rounded-full px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50">
            Usuń
          </button>
        )}
      </div>
      <div className="mt-2 flex gap-1.5 pl-9 text-xs">
        <button
          onClick={() => route.startPicking(pointKey)}
          className={`rounded-full px-2.5 py-1 font-medium transition ${
            active ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          {active ? '📍 Kliknij na mapie…' : '📍 Wskaż na mapie'}
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
  hint,
  value,
  onChange,
}: {
  label: string
  hint: string
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
      <p className="mt-0.5 text-[11px] text-gray-600">{hint}</p>
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
function RouteResults({ plan }: { plan: RoutePlanApi }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (plan.status === 'done') ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [plan.status])

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
