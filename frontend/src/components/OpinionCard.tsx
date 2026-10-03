import { useState } from 'react'
import type { Opinion, TimeOfDay } from '../api/types'
import { DIMENSIONS, scoreColor } from '../lib/dimensions'

/** Mean of the rating's filled dimensions; null when the author gave none. */
function ratingAverage(rating: Opinion['rating']): number | null {
  if (!rating) return null
  const vals = DIMENSIONS.map((d) => rating[d.id]).filter((v): v is number => v !== null)
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
}

/** Five stars, filled up to the rounded value (amber, like Google Maps). */
export function Stars({ value, size = 'text-lg' }: { value: number | null; size?: string }) {
  const filled = value === null ? 0 : Math.round(value)
  return (
    <span
      className={`${size} leading-none tracking-tight text-amber-400`}
      aria-label={value === null ? 'brak ocen' : `${value.toFixed(1)} z 5`}
    >
      {'★'.repeat(filled)}
      <span className="text-gray-300">{'★'.repeat(5 - filled)}</span>
    </span>
  )
}

const AVATAR_COLORS = ['bg-rose-500', 'bg-orange-500', 'bg-emerald-600', 'bg-sky-600', 'bg-violet-600', 'bg-teal-600']

/** Colored circle with the author's initial; color is derived from the name so it stays stable. */
function Avatar({ name }: { name: string }) {
  const color = AVATAR_COLORS[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_COLORS.length]
  return (
    <span
      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-base font-semibold text-white ${color}`}
    >
      {name.charAt(0).toUpperCase()}
    </span>
  )
}

const rtf = new Intl.RelativeTimeFormat('pl', { numeric: 'auto' })

/** "3 dni temu" style date, as on Google Maps. */
function timeAgo(iso: string): string {
  const diffSec = (new Date(iso).getTime() - Date.now()) / 1000
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 31536000],
    ['month', 2592000],
    ['week', 604800],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ]
  for (const [unit, sec] of units) {
    if (Math.abs(diffSec) >= sec) return rtf.format(Math.round(diffSec / sec), unit)
  }
  return 'przed chwilą'
}

const TIME_LABEL: Record<TimeOfDay, string> = {
  morning: 'rano (6–10)',
  day: 'w ciągu dnia (10–16)',
  evening: 'wieczorem (16–22)',
  night: 'w nocy (22–6)',
}

/** "1 opinia", "2 opinie", "5 opinii" */
function opinionsLabel(n: number): string {
  if (n === 1) return '1 opinia'
  const last = n % 10
  return last >= 2 && last <= 4 && (n % 100 < 12 || n % 100 > 14) ? `${n} opinie` : `${n} opinii`
}

function Thumb({ up, filled }: { up: boolean; filled: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinejoin="round"
      strokeLinecap="round"
      className={up ? '' : 'rotate-180'}
      aria-hidden
    >
      <path d="M7 11v9H4a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1h3Zm0 0 4-7a2 2 0 0 1 2 2v3h5.5a1.5 1.5 0 0 1 1.46 1.84l-1.5 7A1.5 1.5 0 0 0 17 20H7" />
    </svg>
  )
}

/**
 * One opinion in the Google Maps style: author, the author's average stars, date and text.
 * Clicking the card expands the text and shows the author's rating per dimension.
 * Votes (👍/👎) are local state only for now: there is no vote endpoint in the contract.
 */
export default function OpinionCard({ opinion: o }: { opinion: Opinion }) {
  const [expanded, setExpanded] = useState(false)
  const [vote, setVote] = useState<Opinion['my_vote']>(o.my_vote)

  const avg = ratingAverage(o.rating)
  // The real backend does not send these fields yet (not in the contract), so default to 0.
  const likes = (o.likes ?? 0) - (o.my_vote === 'up' ? 1 : 0) + (vote === 'up' ? 1 : 0)
  const dislikes = (o.dislikes ?? 0) - (o.my_vote === 'down' ? 1 : 0) + (vote === 'down' ? 1 : 0)
  const toggle = (v: 'up' | 'down') => setVote((cur) => (cur === v ? null : v))

  return (
    <li className="py-3">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((e) => !e)}
        className="block w-full rounded-lg text-left"
      >
        <span className="flex items-center gap-3">
          <Avatar name={o.author.display_name} />
          <span className="min-w-0">
            <span className="block text-sm font-semibold leading-tight">{o.author.display_name}</span>
            {o.author_opinions_count != null && (
              <span className="block text-xs text-gray-500">{opinionsLabel(o.author_opinions_count)}</span>
            )}
          </span>
        </span>

        <span className="mt-2 flex items-center gap-2">
          <Stars value={avg} size="text-sm" />
          {avg !== null && <span className="text-xs font-semibold text-gray-700">{avg.toFixed(1)}</span>}
          <time dateTime={o.created_at} title={new Date(o.created_at).toLocaleString('pl-PL')} className="text-xs text-gray-500">
            {timeAgo(o.created_at)}
          </time>
        </span>

        <span className={`mt-1.5 block whitespace-pre-line break-words text-sm text-gray-800 ${expanded ? '' : 'line-clamp-3'}`}>
          {o.text}
          {!expanded && <span className="ml-1 font-medium text-sky-700">Więcej</span>}
        </span>
      </button>

      {expanded && (
        <div className="mt-3 rounded-xl bg-gray-50 p-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400">Ocena użytkownika</h4>
          {o.rating ? (
            <>
              <ul className="mt-2 space-y-2">
                {DIMENSIONS.map((d) => {
                  const v = o.rating![d.id]
                  return (
                    <li key={d.id} className="flex items-center gap-3 text-sm">
                      <span className="w-28 shrink-0 text-gray-700">{d.label}</span>
                      <span className="h-1.5 flex-1 rounded-full bg-gray-200">
                        <span
                          className="block h-1.5 rounded-full"
                          style={{ width: `${v === null ? 0 : (v / 5) * 100}%`, background: scoreColor(v) }}
                        />
                      </span>
                      <span className="w-8 text-right font-semibold">{v === null ? '–' : `${v}/5`}</span>
                    </li>
                  )
                })}
              </ul>
              <p className="mt-2 text-xs text-gray-500">Oceniono: {TIME_LABEL[o.rating.time_of_day]}</p>
            </>
          ) : (
            <p className="mt-2 text-sm text-gray-500">Autor nie dodał oceny, tylko komentarz.</p>
          )}
        </div>
      )}

      <div className="mt-2 flex items-center gap-2 text-sm text-gray-700">
        <VoteButton active={vote === 'up'} onClick={() => toggle('up')} label="Przydatna opinia" count={likes}>
          <Thumb up filled={vote === 'up'} />
        </VoteButton>
        <VoteButton active={vote === 'down'} onClick={() => toggle('down')} label="Nieprzydatna opinia" count={dislikes}>
          <Thumb up={false} filled={vote === 'down'} />
        </VoteButton>
      </div>
    </li>
  )
}

function VoteButton({
  active,
  onClick,
  label,
  count,
  children,
}: {
  active: boolean
  onClick: () => void
  label: string
  count: number
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={label}
      className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 transition hover:bg-gray-100 ${
        active ? 'bg-sky-50 text-sky-700' : ''
      }`}
    >
      {children}
      {count > 0 && <span className="text-xs font-medium">{count}</span>}
    </button>
  )
}
