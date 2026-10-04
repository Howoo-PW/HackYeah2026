import { useEffect, useMemo, useState } from 'react'
import { fetchSegmentDetail, fetchStreetIds } from './api/client'
import type { SegmentFilter } from './api/client'
import type { AssistantPoint, AssistantResponse, AssistantStreet, Place } from './api/types'
import { useAuth } from './auth/useAuth'
import { useMyOpinions } from './auth/useMyOpinions'
import AccountButton from './auth/AccountButton'
import AssistantPanel from './components/AssistantPanel'
import FilterBar from './components/FilterBar'
import BasemapSwitch from './components/BasemapSwitch'
import Legend from './components/Legend'
import MapView from './components/MapView'
import type { Basemap } from './components/MapView'
import PlaceCard from './components/PlaceCard'
import RoutePanel from './components/RoutePanel'
import SearchBox from './components/SearchBox'
import SegmentPanel from './components/SegmentPanel'
import type { Metric } from './lib/dimensions'
import { activePoint, useRouteDraft } from './routing/useRouteDraft'
import { useRoutePlan } from './routing/useRoutePlan'

type Status = { mock: boolean; error: string | null; zoomedOut: boolean; loading: boolean }

/**
 * Main screen, Google Maps style: full-screen map, search bar top-left (street search -> place card
 * -> "Trasa" opens the route panel), filters on demand, segment details on the right.
 */
export default function App() {
  const [basemap, setBasemap] = useState<Basemap>(() => (new URLSearchParams(window.location.search).get('basemap') === 'satellite' ? 'satellite' : 'map'))
  const [dimension, setDimension] = useState<Metric>('overall')
  const [filter, setFilter] = useState<SegmentFilter>({ dimension: null, minScore: null, noObstacles: false })
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [assistantOpen, setAssistantOpen] = useState(false)
  /** Streets found by the assistant (numbered pins, highlighted when zoomed in) and its reply for a route it opened. */
  const [aiStreets, setAiStreets] = useState<AssistantStreet[]>([])
  const [assistantNote, setAssistantNote] = useState<string | null>(null)
  /** "Tylko moje oceny": limits the map to the signed-in user's own roads (and their fragments). */
  const [mineOnly, setMineOnly] = useState(false)
  const { user } = useAuth()
  const { opinions, failed } = useMyOpinions(user?.id)
  const only = useMemo(
    () =>
      mineOnly && opinions
        ? {
            segmentIds: new Set(opinions.map((o) => o.segment_id)),
            groupIds: new Set(opinions.flatMap((o) => (o.group_id === null ? [] : [o.group_id]))),
          }
        : null,
    [mineOnly, opinions],
  )
  const [selectedId, setSelectedId] = useState<number | null>(null)
  // Segments of the street stretch (group) of the selected piece, once the panel has loaded it.
  const [groupIds, setGroupIds] = useState<number[]>([])
  // The whole street of the clicked piece (same name, joined end to end); the group above is only a stretch of it plus side streets.
  const [street, setStreet] = useState<{ forId: number; ids: number[] } | null>(null)
  const [status, setStatus] = useState<Status>({ mock: false, error: null, zoomedOut: false, loading: false })
  const [place, setPlace] = useState<Place | null>(null)
  const [focus, setFocus] = useState<{ place: Place } | null>(null)
  const [routing, setRouting] = useState(false)
  const route = useRouteDraft()
  const plan = useRoutePlan(route.draft)
  const drawnRoutes = useMemo(
    () => plan.routes.map((r, i) => ({ coordinates: r.geometry.coordinates, selected: i === plan.selected })),
    [plan.routes, plan.selected],
  )

  useEffect(() => {
    if (selectedId === null) return
    const ctrl = new AbortController()
    fetchStreetIds(selectedId, ctrl.signal).then((ids) => ids && !ctrl.signal.aborted && setStreet({ forId: selectedId, ids }))
    return () => ctrl.abort()
  }, [selectedId])

  const select = (id: number | null) => {
    setSelectedId(id)
    setGroupIds([])
  }

  /** Opens one of the user's own rated roads: shows it on the map and opens its panel. */
  const openRatedSegment = async (id: number) => {
    select(id)
    try {
      const d = await fetchSegmentDetail(id)
      const xs = d.geometry.coordinates.map((c) => c[0])
      const ys = d.geometry.coordinates.map((c) => c[1])
      const [w, e, s, n] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
      setFocus({ place: { lat: (s + n) / 2, lon: (w + e) / 2, name: d.name ?? '', detail: null, bounds: [w, s, e, n] } })
    } catch {
      // The panel is already open; only the map move is skipped.
    }
  }

  const changeDimension = (d: Metric) => {
    setDimension(d)
    // The min-score filter always applies to the dimension shown on the map.
    setFilter((f) => (f.minScore === null ? f : { ...f, dimension: d }))
  }

  const showPlace = (p: Place) => {
    setAiStreets([])
    setPlace(p)
    setFocus({ place: p })
    select(null)
  }

  const startRoute = (destination?: Place) => {
    setAssistantNote(null)
    plan.clear()
    route.start(destination)
    select(null)
    setRouting(true)
    if (destination) setFocus({ place: destination })
  }

  /** Shows what the assistant found: a route in the planner, a place on the map, or numbered streets. */
  const applyAssistant = (res: AssistantResponse) => {
    const asPlace = (p: AssistantPoint): Place => ({ lat: p.lat, lon: p.lon, name: p.name, detail: null, bounds: null })
    setAiStreets([])
    if (res.intent === 'route' && res.route) {
      const r = res.route
      const draft = route.load({ a: asPlace(r.from), b: asPlace(r.to), stops: r.via.map(asPlace), profile: r.profile, weights: r.weights })
      plan.adopt(draft, r.routes)
      select(null)
      setPlace(null)
      setAssistantNote(res.answer)
      setAssistantOpen(false)
      setRouting(true)
    } else if (res.intent === 'place' && res.place) {
      showPlace({ ...asPlace(res.place), kind: 'place', segmentId: res.place.segment_id ?? undefined })
    } else if (res.intent === 'streets' && res.streets.length > 0) {
      setPlace(null)
      select(null)
      setAiStreets(res.streets)
      const lons = res.streets.map((st) => st.location.lon)
      const lats = res.streets.map((st) => st.location.lat)
      const [w, e, so, n] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)]
      const pad = 0.003
      setFocus({ place: { lat: (so + n) / 2, lon: (w + e) / 2, name: '', detail: null, bounds: [w - pad, so - pad, e + pad, n + pad] } })
    }
  }

  /** Opens one of the assistant's streets: its panel, centred on the map. */
  const openAiStreet = (street: AssistantStreet) => {
    if (street.segment_ids.length > 0) select(street.segment_ids[0])
    setFocus({ place: { lat: street.location.lat, lon: street.location.lon, name: street.name, detail: null, bounds: null } })
  }

  const leaveRoute = () => {
    setAssistantNote(null)
    plan.clear()
    route.reset()
    setRouting(false)
  }

  return (
    <div className="relative h-dvh w-screen overflow-hidden">
      <MapView
        routes={drawnRoutes}
        basemap={basemap}
        dimension={dimension}
        filter={filter}
        only={only}
        selectedIds={
          street && street.forId === selectedId
            ? street.ids
            : groupIds.length > 0
              ? groupIds
              : selectedId !== null
                ? [selectedId]
                : aiStreets.flatMap((st) => st.segment_ids)
        }
        primaryId={selectedId}
        onSelect={select}
        focus={focus}
        placeMarker={place}
        pins={aiStreets.map((st, i) => ({ lat: st.location.lat, lon: st.location.lon, label: String(i + 1) }))}
        routeMode={routing}
        routePoints={{ a: route.draft.a, b: route.draft.b, stops: route.draft.stops }}
        placing={activePoint(route.draft) !== null}
        onRouteClick={route.clickMap}
        onRouteDrag={route.placeFromMap}
        onStatus={setStatus}
      />

      <div className="pointer-events-none absolute left-0 top-0 flex w-[calc(100%-6.5rem)] max-w-md flex-col gap-2 p-3 md:w-full">
        {routing ? (
          <RoutePanel route={route} plan={plan} note={assistantNote} onDismissNote={() => setAssistantNote(null)} onBack={leaveRoute} />
        ) : (
          <>
            <div className="pointer-events-auto">
              <SearchBox
                variant="bar"
                placeholder="Szukaj ulicy lub adresu w Krakowie"
                onPick={showPlace}
                onClear={() => setPlace(null)}
              />
            </div>

            {place && (
              <PlaceCard
                place={place}
                onRoute={() => startRoute(place)}
                onShowRatings={select}
                onClose={() => setPlace(null)}
              />
            )}

            <div className="pointer-events-auto flex gap-2">
              <button
                onClick={() => {
                  setFiltersOpen((o) => !o)
                  setAssistantOpen(false)
                }}
                aria-expanded={filtersOpen}
                className="flex-1 rounded-full bg-white px-4 py-2 text-sm font-medium shadow-lg ring-1 ring-black/5 transition hover:bg-gray-50"
              >
                Oceny
              </button>
              <button
                onClick={() => startRoute()}
                className="flex-1 rounded-full bg-gray-900 px-4 py-2 text-sm font-medium text-white shadow-lg transition hover:bg-gray-700"
              >
                Trasa
              </button>
              <button
                onClick={() => {
                  setAssistantOpen((o) => !o)
                  setFiltersOpen(false)
                }}
                aria-expanded={assistantOpen}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-full bg-violet-700 px-4 py-2 text-sm font-medium text-white shadow-lg transition hover:bg-violet-800"
              >
                Asystent
                <span className="rounded bg-white/25 px-1 text-[10px] font-bold uppercase">AI</span>
              </button>
            </div>

            {assistantOpen && <AssistantPanel onResult={applyAssistant} onOpenStreet={openAiStreet} onClose={() => setAssistantOpen(false)} />}

            {filtersOpen && (
              <FilterBar
                dimension={dimension}
                onDimension={changeDimension}
                filter={filter}
                onFilter={setFilter}
                onClose={() => setFiltersOpen(false)}
              />
            )}

            {status.zoomedOut && <Notice>Przybliż mapę, żeby zobaczyć odcinki.</Notice>}
            {status.error && <Notice tone="error">{status.error}</Notice>}
            {status.mock && <Notice tone="warn">Backend niedostępny — dane przykładowe.</Notice>}
          </>
        )}
      </div>

      <div className="pointer-events-auto absolute right-3 top-3 z-30 flex items-center gap-3 rounded-full bg-white py-2 pl-5 pr-2 shadow-lg ring-1 ring-black/5">
        <Logo />
        <AccountButton opinions={opinions} failed={failed} onOpenSegment={openRatedSegment} mineOnly={mineOnly} onToggleMine={() => setMineOnly((m) => !m)} />
      </div>

      {!routing && <Legend metric={dimension} />}
      <BasemapSwitch basemap={basemap} onChange={setBasemap} />

      {!routing && selectedId !== null && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex pr-16 md:inset-x-auto md:bottom-auto md:right-16 md:top-20 md:pr-0">
          <SegmentPanel key={selectedId} segmentId={selectedId} onGroup={setGroupIds} onClose={() => select(null)} />
        </div>
      )}
    </div>
  )
}

/** "Rate My" with "Road" on asphalt (dark navy, yellow dashed center line drawn over the letters), as on the cover. */
function Logo() {
  return (
    <span className="hidden items-center gap-1.5 text-xl font-extrabold uppercase tracking-tight text-gray-900 sm:inline-flex">
      Rate My
      <span className="relative rounded-md bg-indigo-950 px-2 py-0.5 text-white">
        <span className="relative">Road</span>
        <span
          aria-hidden
          className="absolute inset-x-0 top-1/2 z-10 h-[3px] -translate-y-1/2"
          style={{ backgroundImage: 'repeating-linear-gradient(to right, #fbbf24 0 8px, transparent 8px 14px)' }}
        />
      </span>
    </span>
  )
}

function Notice({ children, tone = 'info' }: { children: React.ReactNode; tone?: 'info' | 'warn' | 'error' }) {
  const colors = { info: 'bg-white text-gray-700', warn: 'bg-amber-100 text-amber-900', error: 'bg-red-100 text-red-800' }
  return <div className={`pointer-events-auto self-start rounded-xl px-3 py-1 text-sm shadow ${colors[tone]}`}>{children}</div>
}
