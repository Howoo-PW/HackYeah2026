import { useMemo, useState } from 'react'
import type { SegmentFilter } from './api/client'
import type { Place } from './api/types'
import AccountButton from './auth/AccountButton'
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
  const [filter, setFilter] = useState<SegmentFilter>({ dimension: null, minScore: null, ratedOnly: false, noObstacles: false })
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  // Segments of the street stretch (group) of the selected piece, once the panel has loaded it.
  const [groupIds, setGroupIds] = useState<number[]>([])
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

  const select = (id: number | null) => {
    setSelectedId(id)
    setGroupIds([])
  }

  const changeDimension = (d: Metric) => {
    setDimension(d)
    // The min-score filter always applies to the dimension shown on the map.
    setFilter((f) => (f.minScore === null ? f : { ...f, dimension: d }))
  }

  const showPlace = (p: Place) => {
    setPlace(p)
    setFocus({ place: p })
    select(null)
  }

  const startRoute = (destination?: Place) => {
    plan.clear()
    route.start(destination)
    select(null)
    setRouting(true)
    if (destination) setFocus({ place: destination })
  }

  const leaveRoute = () => {
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
        selectedIds={groupIds.length > 0 ? groupIds : selectedId !== null ? [selectedId] : []}
        onSelect={select}
        focus={focus}
        placeMarker={place}
        routeMode={routing}
        routePoints={{ a: route.draft.a, b: route.draft.b, stops: route.draft.stops }}
        placing={activePoint(route.draft) !== null}
        onRouteClick={route.clickMap}
        onRouteDrag={route.placeFromMap}
        onStatus={setStatus}
      />

      <div className="pointer-events-none absolute left-0 top-0 flex w-[calc(100%-6.5rem)] max-w-md flex-col gap-2 p-3 md:w-full">
        {routing ? (
          <RoutePanel route={route} plan={plan} onBack={leaveRoute} />
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
                onClick={() => setFiltersOpen((o) => !o)}
                aria-expanded={filtersOpen}
                className="rounded-full bg-white px-4 py-2 text-sm font-medium shadow-lg ring-1 ring-black/5 transition hover:bg-gray-50"
              >
                ⚙ Filtry i kolory
              </button>
              <button
                onClick={() => startRoute()}
                className="rounded-full bg-gray-900 px-4 py-2 text-sm font-medium text-white shadow-lg transition hover:bg-gray-700"
              >
                🧭 Trasa
              </button>
            </div>

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

      <div className="pointer-events-auto absolute right-3 top-3 flex items-center gap-3 rounded-full bg-white py-1.5 pl-4 pr-2 shadow-lg ring-1 ring-black/5">
        <span className="hidden text-sm font-bold sm:inline">Rate My Road</span>
        <AccountButton />
      </div>

      {!routing && <Legend metric={dimension} />}
      <BasemapSwitch basemap={basemap} onChange={setBasemap} />

      {!routing && selectedId !== null && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex md:inset-x-auto md:bottom-auto md:right-3 md:top-14">
          <SegmentPanel key={selectedId} segmentId={selectedId} onGroup={setGroupIds} onClose={() => select(null)} />
        </div>
      )}
    </div>
  )
}

function Notice({ children, tone = 'info' }: { children: React.ReactNode; tone?: 'info' | 'warn' | 'error' }) {
  const colors = { info: 'bg-white text-gray-700', warn: 'bg-amber-100 text-amber-900', error: 'bg-red-100 text-red-800' }
  return <div className={`pointer-events-auto self-start rounded-xl px-3 py-1 text-sm shadow ${colors[tone]}`}>{children}</div>
}
