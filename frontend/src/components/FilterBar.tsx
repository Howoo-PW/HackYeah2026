import type { SegmentFilter } from '../api/client'
import { METRICS, SCORE_COLORS } from '../lib/dimensions'
import type { Metric } from '../lib/dimensions'

type Props = {
  dimension: Metric
  onDimension: (d: Metric) => void
  filter: SegmentFilter
  onFilter: (f: SegmentFilter) => void
}

const ICONS: Record<Metric, string> = {
  overall: '⭐',
  surface: '🛣️',
  views: '🌅',
  safety: '🛡️',
  traffic: '🚦',
  parking: '🅿️',
}

/** Left sidebar: dimension picker (what the map is colored by), legend, min-score filter and rated-only toggle. */
export default function FilterBar({ dimension, onDimension, filter, onFilter }: Props) {
  const current = METRICS.find((d) => d.id === dimension)!
  const minScore = filter.minScore ?? 1

  return (
    <section className="pointer-events-auto w-full overflow-hidden rounded-2xl bg-white/95 shadow-xl ring-1 ring-black/5 backdrop-blur">
      <header className="bg-gradient-to-r from-gray-900 to-gray-700 px-4 py-3 text-white">
        <h1 className="text-base font-bold leading-tight">Rate My Road</h1>
        <p className="text-xs text-gray-300">Oceny dróg</p>
      </header>

      <div className="p-3">
        <h2 className="px-1 text-[11px] font-semibold uppercase tracking-wider text-gray-400">Filtruj według</h2>
        <div className="mt-1.5 grid grid-cols-1 gap-1" role="tablist" aria-label="Wymiar oceny">
          {METRICS.map((d) => {
            const active = d.id === dimension
            return (
              <button
                key={d.id}
                role="tab"
                aria-selected={active}
                onClick={() => onDimension(d.id)}
                className={`flex items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium transition ${
                  active ? 'bg-gray-900 text-white shadow' : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                <span className="text-lg leading-none" aria-hidden>
                  {ICONS[d.id]}
                </span>
                {d.label}
              </button>
            )
          })}
        </div>

        <div className="mt-4 rounded-xl bg-gray-50 p-3">
          <div
            className="h-2.5 rounded-full"
            style={{ background: `linear-gradient(to right, ${SCORE_COLORS.join(',')})` }}
            aria-hidden
          />
          <div className="mt-1.5 flex justify-between gap-3 text-[11px] leading-tight text-gray-500">
            <span>1 · {current.low}</span>
            <span className="text-right">{current.high} · 5</span>
          </div>
        </div>

        <h2 className="mt-4 px-1 text-[11px] font-semibold uppercase tracking-wider text-gray-400">Filtry</h2>
        <div className="mt-1.5 space-y-3 px-1 text-sm text-gray-700">
          <div>
            <label className="flex cursor-pointer items-center justify-between">
              <span>Minimalna ocena</span>
              <Switch
                checked={filter.minScore !== null}
                onChange={(on) => onFilter({ ...filter, dimension, minScore: on ? minScore : null })}
                label="Włącz filtr minimalnej oceny"
              />
            </label>
            <div className={`mt-2 flex items-center gap-3 transition ${filter.minScore === null ? 'opacity-40' : ''}`}>
              <input
                type="range"
                min={1}
                max={5}
                step={1}
                value={minScore}
                disabled={filter.minScore === null}
                onChange={(e) => onFilter({ ...filter, dimension, minScore: Number(e.target.value) })}
                aria-label="Minimalna ocena"
                className="h-2 flex-1 cursor-pointer accent-gray-900"
              />
              <span className="w-8 rounded-md bg-gray-900 py-0.5 text-center text-xs font-bold text-white">≥ {minScore}</span>
            </div>
          </div>

          <label className="flex cursor-pointer items-center justify-between">
            <span>Tylko ocenione</span>
            <Switch
              checked={filter.ratedOnly}
              onChange={(on) => onFilter({ ...filter, ratedOnly: on })}
              label="Pokaż tylko ocenione odcinki"
            />
          </label>

          <label className="flex cursor-pointer items-center justify-between">
            <span>Bez przeszkód</span>
            <Switch
              checked={filter.noObstacles}
              onChange={(on) => onFilter({ ...filter, noObstacles: on })}
              label="Ukryj odcinki z przeszkodami"
            />
          </label>
        </div>
      </div>
    </section>
  )
}

function Switch({ checked, onChange, label }: { checked: boolean; onChange: (on: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${checked ? 'bg-gray-900' : 'bg-gray-300'}`}
    >
      <span
        className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-5' : ''
        }`}
      />
    </button>
  )
}
