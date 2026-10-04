import { useMemo } from 'react'
import type { MyOpinion } from '../api/types'
import { DIMENSIONS, scoreColor } from '../lib/dimensions'
import { Stars } from './OpinionCard'

type Road = { segmentId: number; name: string | null; date: string; rating: MyOpinion | null; comment: MyOpinion | null }

/** One entry per road the user has rated or commented on: the latest rating and the latest comment together, newest road first. */
function groupByRoad(opinions: MyOpinion[]): Road[] {
  const roads = new Map<number, Road>()
  for (const o of opinions) {
    // Opinions arrive newest first, so the first of each kind per road is the latest.
    const road = roads.get(o.segment_id) ?? { segmentId: o.segment_id, name: o.segment_name, date: o.created_at, rating: null, comment: null }
    if (o.kind === 'rating' && !road.rating) road.rating = o
    if (o.kind === 'comment' && !road.comment) road.comment = o
    roads.set(o.segment_id, road)
  }
  return [...roads.values()]
}

/** Mean of the rating's filled dimensions; null when there are none. */
function average(r: MyOpinion): number | null {
  const vals = DIMENSIONS.map((d) => r[d.id]).filter((v): v is number => v !== null)
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
}

/** The user's rated roads with rating and comment, newest first (shown in the account menu); a click opens the road. */
export default function MyRoadsList({
  opinions,
  failed,
  onOpen,
}: {
  opinions: MyOpinion[] | null
  failed: boolean
  onOpen: (segmentId: number) => void
}) {
  const roads = useMemo(() => groupByRoad(opinions ?? []), [opinions])
  return (
    <div>
      <h2 className="border-t border-gray-100 px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-gray-700">
        Twoje oceny ({roads.length})
      </h2>
      <div className="max-h-72 overflow-y-auto">
        {failed ? (
          <p className="px-3 py-2 text-sm text-gray-600">Nie udało się pobrać opinii.</p>
        ) : opinions === null ? (
          <p className="px-3 py-2 text-sm text-gray-600">Ładowanie…</p>
        ) : roads.length === 0 ? (
          <p className="px-3 py-2 text-sm text-gray-600">Nie masz jeszcze opinii.</p>
        ) : (
          <ul>
            {roads.map((road) => (
              <li key={road.segmentId}>
                <RoadRow road={road} onOpen={() => onOpen(road.segmentId)} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/** One rated road: name, date, overall stars and scores per dimension, then the user's comment. */
function RoadRow({ road, onOpen }: { road: Road; onOpen: () => void }) {
  const { rating, comment } = road
  return (
    <button onClick={onOpen} className="block w-full rounded-xl px-3 py-2 text-left transition hover:bg-gray-100">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-semibold text-gray-900">{road.name ?? `Odcinek #${road.segmentId}`}</span>
        <span className="shrink-0 text-xs text-gray-600">{new Date(road.date).toLocaleDateString('pl-PL')}</span>
      </div>
      {rating && (
        <>
          <Stars value={average(rating)} size="text-sm" />
          <div className="mt-1 flex flex-wrap gap-1">
            {DIMENSIONS.filter((d) => rating[d.id] !== null).map((d) => (
              <span key={d.id} className="rounded-md px-1.5 py-0.5 text-xs font-medium text-gray-900" style={{ background: scoreColor(rating[d.id]) }}>
                {d.label} {rating[d.id]}
              </span>
            ))}
          </div>
        </>
      )}
      {comment && (
        <p className="mt-1 line-clamp-2 text-sm text-gray-700">
          {comment.text}
          {comment.status === 'hidden' && <span className="ml-1 text-xs text-red-700">(ukryty)</span>}
        </p>
      )}
    </button>
  )
}
