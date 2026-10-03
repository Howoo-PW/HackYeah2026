import { useEffect, useState } from 'react'
import { fetchSegmentDetail } from '../api/client'
import type { SegmentDetail } from '../api/types'
import { DIMENSIONS, scoreColor } from '../lib/dimensions'

type Props = { segmentId: number; onClose: () => void }

/** Remount with `key={segmentId}` so state resets per segment. Bottom sheet on mobile, side card on desktop: scores, OSM info and obstacles for one segment. */
export default function SegmentPanel({ segmentId, onClose }: Props) {
  const [detail, setDetail] = useState<SegmentDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchSegmentDetail(segmentId, ctrl.signal)
      .then(setDetail)
      .catch((err: Error) => {
        if (!ctrl.signal.aborted) setError(err.message)
      })
    return () => ctrl.abort()
  }, [segmentId])

  return (
    <aside className="pointer-events-auto max-h-[55vh] w-full overflow-y-auto rounded-t-2xl bg-white p-4 shadow-2xl md:max-h-none md:w-96 md:rounded-2xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold leading-tight">{detail?.name ?? (error ? 'Błąd' : 'Ładowanie…')}</h2>
          {detail && (
            <p className="text-sm text-gray-500">
              {detail.highway} · {Math.round(detail.length_m)} m · ocen: {detail.ratings_count}
            </p>
          )}
        </div>
        <button onClick={onClose} aria-label="Zamknij panel" className="rounded-full p-1.5 text-gray-500 hover:bg-gray-100">
          ✕
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {detail && (
        <>
          <ul className="mt-4 space-y-2.5">
            {DIMENSIONS.map((d) => {
              const v = detail.scores[d.id]
              return (
                <li key={d.id}>
                  <div className="flex justify-between text-sm">
                    <span>{d.label}</span>
                    <span className="font-semibold">{v === null ? 'brak ocen' : v.toFixed(1)}</span>
                  </div>
                  <div className="mt-1 h-2 rounded-full bg-gray-100">
                    <div
                      className="h-2 rounded-full"
                      style={{ width: `${v === null ? 0 : (v / 5) * 100}%`, background: scoreColor(v) }}
                    />
                  </div>
                </li>
              )
            })}
          </ul>

          <dl className="mt-4 grid grid-cols-2 gap-x-3 gap-y-1 text-sm text-gray-600">
            <dt>Nawierzchnia (OSM)</dt>
            <dd>{detail.surface_osm ?? 'brak danych'}</dd>
            <dt>Limit prędkości</dt>
            <dd>{detail.maxspeed ? `${detail.maxspeed} km/h` : 'brak danych'}</dd>
            <dt>Oświetlenie</dt>
            <dd>{detail.lit === null ? 'brak danych' : detail.lit ? 'tak' : 'nie'}</dd>
          </dl>

          {detail.active_obstacles_count > 0 && (
            <p className="mt-3 rounded-lg bg-amber-50 p-2 text-sm text-amber-800">
              Aktywne przeszkody: {detail.active_obstacles_count}
            </p>
          )}
        </>
      )}
    </aside>
  )
}
