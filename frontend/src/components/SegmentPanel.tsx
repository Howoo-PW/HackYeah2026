import { useEffect, useState } from 'react'
import { fetchComments, fetchSegmentDetail } from '../api/client'
import type { Opinion, Rating, Scores, SegmentDetail, Summary } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { DIMENSIONS, overallScore, scoreColor } from '../lib/dimensions'
import CommentForm from './CommentForm'
import OpinionCard, { Stars } from './OpinionCard'
import RatingForm from './RatingForm'

type Props = { segmentId: number; onClose: () => void }

/**
 * Remount with `key={segmentId}` so state resets per segment.
 * Bottom sheet on mobile, side card on desktop: overall score, per-dimension scores, OSM info,
 * AI summary and opinions for one segment.
 */
export default function SegmentPanel({ segmentId, onClose }: Props) {
  const [detail, setDetail] = useState<SegmentDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [width, setWidth] = useStoredWidth()
  const { user } = useAuth()
  const userId = user?.id
  // The user's rating right after saving, until the backend's `my_rating` catches up (or in mock mode).
  const [saved, setSaved] = useState<{ userId: string | undefined; rating: Rating } | null>(null)
  const savedRating = saved && saved.userId === userId ? saved.rating : null
  const [reload, setReload] = useState(0)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchSegmentDetail(segmentId, ctrl.signal)
      .then(setDetail)
      .catch((err: Error) => {
        if (!ctrl.signal.aborted) setError(err.message)
      })
    return () => ctrl.abort()
  }, [segmentId, userId, reload])

  return (
    <div
      className="pointer-events-auto relative w-full md:w-[var(--panel-w)]"
      style={{ '--panel-w': `${width}px` } as React.CSSProperties}
    >
      <ResizeHandle width={width} onChange={setWidth} />
      <aside className="max-h-[55vh] w-full overflow-y-auto rounded-t-2xl bg-white p-4 shadow-2xl md:max-h-[calc(100dvh-1.5rem)] md:rounded-2xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold leading-tight">{detail?.name ?? (error ? 'Błąd' : 'Ładowanie…')}</h2>
          {detail && (
            <p className="text-sm text-gray-500">
              {detail.highway} · {Math.round(detail.length_m)} m
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
          <OverallScore scores={detail.scores} ratingsCount={detail.ratings_count} />

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

          <RatingForm
            segmentId={segmentId}
            existing={savedRating ?? detail.my_rating}
            onSaved={(r) => {
              setSaved({ userId, rating: r })
              setReload((n) => n + 1)
            }}
          />

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

          <SummarySection summary={detail.summary} />

          <CommentsSection segmentId={segmentId} />
        </>
      )}
      </aside>
    </div>
  )
}

const MIN_WIDTH = 340
const MAX_WIDTH = 900
const DEFAULT_WIDTH = 448
const WIDTH_KEY = 'segmentPanelWidth'

function clampWidth(w: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.min(w, window.innerWidth - 24)))
}

/** Panel width in px, remembered between sessions (storage may be unavailable, so every access is guarded). */
function useStoredWidth(): [number, (w: number) => void] {
  const [width, setWidth] = useState(() => {
    try {
      const saved = Number(localStorage.getItem(WIDTH_KEY))
      return saved ? clampWidth(saved) : DEFAULT_WIDTH
    } catch {
      return DEFAULT_WIDTH
    }
  })
  const update = (w: number) => {
    const next = clampWidth(w)
    setWidth(next)
    try {
      localStorage.setItem(WIDTH_KEY, String(next))
    } catch {
      /* ignore: width just won't persist */
    }
  }
  return [width, update]
}

/** Drag handle on the left edge (desktop only). Panel is anchored right, so dragging left widens it. Arrow keys work too. */
function ResizeHandle({ width, onChange }: { width: number; onChange: (w: number) => void }) {
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    const startX = e.clientX
    const startWidth = width
    const target = e.currentTarget
    target.setPointerCapture(e.pointerId)
    const move = (ev: PointerEvent) => onChange(startWidth + (startX - ev.clientX))
    const up = () => {
      target.removeEventListener('pointermove', move)
      target.removeEventListener('pointerup', up)
    }
    target.addEventListener('pointermove', move)
    target.addEventListener('pointerup', up)
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Zmień szerokość panelu"
      aria-valuenow={width}
      aria-valuemin={MIN_WIDTH}
      aria-valuemax={MAX_WIDTH}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') onChange(width + 24)
        if (e.key === 'ArrowRight') onChange(width - 24)
      }}
      className="group absolute -left-2 top-0 z-10 hidden h-full w-4 cursor-col-resize touch-none items-center justify-center md:flex"
    >
      <span className="h-12 w-1.5 rounded-full bg-gray-300 shadow transition group-hover:bg-gray-500 group-focus-visible:bg-sky-500" />
    </div>
  )
}

/** Headline number with stars, like the rating header on Google Maps. */
function OverallScore({ scores, ratingsCount }: { scores: Scores; ratingsCount: number }) {
  const avg = overallScore(scores)
  return (
    <div className="mt-4 flex items-center gap-4 rounded-xl bg-gray-50 p-3">
      <span className="text-4xl font-bold leading-none">{avg === null ? '–' : avg.toFixed(1)}</span>
      <div>
        <Stars value={avg} />
        <p className="mt-0.5 text-xs text-gray-500">{ratingsCount > 0 ? `${ratingsCount} ocen` : 'Brak ocen'}</p>
      </div>
    </div>
  )
}

const CONFIDENCE_LABEL = { low: 'niska pewność', medium: 'średnia pewność', high: 'wysoka pewność' } as const

/** AI-generated summary of opinions. Contract: `summary` is null when there are too few comments. */
function SummarySection({ summary }: { summary: Summary | null }) {
  return (
    <section className="mt-5 rounded-xl border border-violet-100 bg-violet-50/60 p-3">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-violet-900">
          <span className="rounded bg-violet-600 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
            AI
          </span>
          Podsumowanie opinii
        </h3>
        {summary && <span className="text-[11px] text-violet-700">{CONFIDENCE_LABEL[summary.confidence]}</span>}
      </div>

      {!summary && <p className="mt-2 text-sm text-gray-500">Za mało opinii, żeby przygotować podsumowanie.</p>}

      {summary && (
        <>
          <p className="mt-2 text-sm font-medium text-gray-900">{summary.overall}</p>
          <dl className="mt-2 space-y-1 text-sm text-gray-700">
            {DIMENSIONS.map((d) => (
              <div key={d.id}>
                <dt className="inline font-semibold">{d.label}: </dt>
                <dd className="inline">{summary[d.id]}</dd>
              </div>
            ))}
          </dl>
          {summary.conflicts.length > 0 && (
            <ul className="mt-2 space-y-1 rounded-lg bg-amber-50 p-2 text-xs text-amber-900">
              {summary.conflicts.map((c) => (
                <li key={c}>⚠ {c}</li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-[11px] text-gray-400">
            Wygenerowane automatycznie na podstawie {summary.comments_count} opinii.
          </p>
        </>
      )}
    </section>
  )
}

const PAGE_SIZE = 5

/** Read-only list of opinions (newest first) with "load more"; posting comes with the auth-rating branch. */
function CommentsSection({ segmentId }: { segmentId: number }) {
  const [items, setItems] = useState<Opinion[]>([])
  const [total, setTotal] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchComments(segmentId, page, PAGE_SIZE, ctrl.signal)
      .then((res) => {
        setItems((prev) => (page === 1 ? res.items : [...prev, ...res.items]))
        setTotal(res.total)
      })
      .catch((err: Error) => {
        if (!ctrl.signal.aborted) setError(err.message)
      })
    return () => ctrl.abort()
  }, [segmentId, page])

  return (
    <section className="mt-5 border-t border-gray-100 pt-4">
      <h3 className="text-sm font-semibold">Opinie{total !== null && ` (${total})`}</h3>
      <CommentForm
        segmentId={segmentId}
        onPosted={(o) => {
          setItems((prev) => [o, ...prev])
          setTotal((t) => (t ?? 0) + 1)
        }}
      />
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      {total === 0 && <p className="mt-2 text-sm text-gray-500">Nikt jeszcze nie opisał tej drogi.</p>}
      <ul className="mt-1 divide-y divide-gray-100">
        {items.map((o) => (
          <OpinionCard key={o.id} opinion={o} />
        ))}
      </ul>
      {total !== null && items.length < total && (
        <button onClick={() => setPage((p) => p + 1)} className="mt-3 text-sm font-medium text-sky-700 hover:underline">
          Pokaż więcej opinii
        </button>
      )}
    </section>
  )
}
