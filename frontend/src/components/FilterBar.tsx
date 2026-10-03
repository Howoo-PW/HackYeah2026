import type { Dimension } from '../api/types'
import type { SegmentFilter } from '../api/client'
import { DIMENSIONS, SCORE_COLORS } from '../lib/dimensions'

type Props = {
  dimension: Dimension
  onDimension: (d: Dimension) => void
  filter: SegmentFilter
  onFilter: (f: SegmentFilter) => void
}

/** Dimension chips (what the map is colored by), min-score filter and rated-only toggle, plus legend. */
export default function FilterBar({ dimension, onDimension, filter, onFilter }: Props) {
  const current = DIMENSIONS.find((d) => d.id === dimension)!
  const minScore = filter.minScore ?? 1

  return (
    <div className="pointer-events-auto w-full max-w-xl rounded-2xl bg-white/95 p-3 shadow-lg backdrop-blur">
      <div className="flex gap-1.5 overflow-x-auto pb-1" role="tablist" aria-label="Wymiar oceny">
        {DIMENSIONS.map((d) => (
          <button
            key={d.id}
            role="tab"
            aria-selected={d.id === dimension}
            onClick={() => onDimension(d.id)}
            className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-medium transition ${
              d.id === dimension ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {d.label}
          </button>
        ))}
      </div>

      <div className="mt-2 flex items-center gap-2 text-xs text-gray-600">
        <span className="shrink-0">{current.low}</span>
        <div
          className="h-2 flex-1 rounded-full"
          style={{ background: `linear-gradient(to right, ${SCORE_COLORS.join(',')})` }}
          aria-hidden
        />
        <span className="shrink-0">{current.high}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={filter.minScore !== null}
            onChange={(e) => onFilter({ ...filter, dimension, minScore: e.target.checked ? minScore : null })}
          />
          <span>Ocena od</span>
          <input
            type="range"
            min={1}
            max={5}
            step={1}
            value={minScore}
            disabled={filter.minScore === null}
            onChange={(e) => onFilter({ ...filter, dimension, minScore: Number(e.target.value) })}
            aria-label="Minimalna ocena"
          />
          <span className="w-4 font-semibold">{minScore}</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={filter.ratedOnly}
            onChange={(e) => onFilter({ ...filter, ratedOnly: e.target.checked })}
          />
          <span>Tylko ocenione</span>
        </label>
      </div>
    </div>
  )
}
