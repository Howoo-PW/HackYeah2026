import { useState } from 'react'
import type { SegmentFilter } from './api/client'
import type { Dimension } from './api/types'
import FilterBar from './components/FilterBar'
import MapView from './components/MapView'
import SegmentPanel from './components/SegmentPanel'

type Status = { mock: boolean; error: string | null; zoomedOut: boolean; loading: boolean }

/** Main screen: full-screen map with filter bar on top and segment details panel. */
export default function App() {
  const [dimension, setDimension] = useState<Dimension>('surface')
  const [filter, setFilter] = useState<SegmentFilter>({ dimension: null, minScore: null, ratedOnly: false })
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [status, setStatus] = useState<Status>({ mock: false, error: null, zoomedOut: false, loading: false })

  const changeDimension = (d: Dimension) => {
    setDimension(d)
    // The min-score filter always applies to the dimension shown on the map.
    setFilter((f) => (f.minScore === null ? f : { ...f, dimension: d }))
  }

  return (
    <div className="relative h-dvh w-screen overflow-hidden">
      <MapView
        dimension={dimension}
        filter={filter}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onStatus={setStatus}
      />

      <div className="pointer-events-none absolute inset-x-0 top-0 flex flex-col items-center gap-2 p-3">
        <FilterBar dimension={dimension} onDimension={changeDimension} filter={filter} onFilter={setFilter} />
        {status.zoomedOut && <Notice>Przybliż mapę, żeby zobaczyć odcinki.</Notice>}
        {status.error && <Notice tone="error">{status.error}</Notice>}
        {status.mock && <Notice tone="warn">Backend niedostępny — dane przykładowe.</Notice>}
      </div>

      {selectedId !== null && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex md:inset-x-auto md:bottom-auto md:left-4 md:top-40">
          <SegmentPanel key={selectedId} segmentId={selectedId} onClose={() => setSelectedId(null)} />
        </div>
      )}
    </div>
  )
}

function Notice({ children, tone = 'info' }: { children: React.ReactNode; tone?: 'info' | 'warn' | 'error' }) {
  const colors = { info: 'bg-white text-gray-700', warn: 'bg-amber-100 text-amber-900', error: 'bg-red-100 text-red-800' }
  return <div className={`pointer-events-auto rounded-full px-3 py-1 text-sm shadow ${colors[tone]}`}>{children}</div>
}
