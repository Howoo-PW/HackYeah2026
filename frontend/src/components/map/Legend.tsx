import { METRICS, SCORE_COLORS } from '../../lib/dimensions'
import type { Metric } from '../../lib/dimensions'

/** Small always-visible color legend for the metric the map is colored by (bottom-left, desktop). */
export default function Legend({ metric }: { metric: Metric }) {
  const m = METRICS.find((x) => x.id === metric)!
  return (
    <div className="pointer-events-none absolute bottom-6 left-3 hidden w-56 rounded-xl bg-white/90 p-2.5 shadow-lg backdrop-blur md:block">
      <p className="text-xs font-semibold text-gray-700">{m.label}</p>
      <div className="mt-1 h-2 rounded-full" style={{ background: `linear-gradient(to right, ${SCORE_COLORS.join(',')})` }} />
      <div className="mt-1 flex justify-between gap-2 text-[10px] leading-tight text-gray-600">
        <span>{m.low}</span>
        <span className="text-right">{m.high}</span>
      </div>
    </div>
  )
}
