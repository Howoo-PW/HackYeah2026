import { useState } from 'react'
import { fetchNearestSegment } from '../api/client'
import type { Place } from '../api/types'

type Props = {
  place: Place
  /** Opens route mode with this place as the destination. */
  onRoute: () => void
  /** Opens the ratings panel for the segment at this place. */
  onShowRatings: (segmentId: number) => void
  onClose: () => void
}

/** Card for a found place (like Google Maps): name, address line, "Trasa" and "Oceny". */
export default function PlaceCard({ place, onRoute, onShowRatings, onClose }: Props) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const showRatings = async () => {
    if (place.segmentId) return onShowRatings(place.segmentId) // streets from our own search already know it
    setBusy(true)
    setMessage(null)
    const seg = await fetchNearestSegment(place.lat, place.lon)
    setBusy(false)
    if (seg) onShowRatings(seg.id)
    else setMessage('Brak ocenianego odcinka drogi w tym miejscu.')
  }

  return (
    <section className="pointer-events-auto rounded-2xl bg-white p-4 shadow-xl ring-1 ring-black/5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-bold leading-tight">{place.name}</h2>
          {place.detail && <p className="truncate text-sm text-gray-600">{place.detail}</p>}
        </div>
        <button onClick={onClose} aria-label="Zamknij" className="rounded-full p-1.5 text-gray-600 hover:bg-gray-100">
          ✕
        </button>
      </div>

      <div className="mt-3 flex gap-2">
        <button
          onClick={onRoute}
          className="flex-1 rounded-full bg-gray-900 py-2 text-sm font-semibold text-white transition hover:bg-gray-700"
        >
          Trasa
        </button>
        <button
          onClick={showRatings}
          disabled={busy}
          className="flex-1 rounded-full border border-gray-300 py-2 text-sm font-semibold text-gray-800 transition hover:bg-gray-50 disabled:opacity-50"
        >
          {busy ? 'Szukam…' : '★ Oceny'}
        </button>
      </div>
      {message && <p className="mt-2 text-sm text-gray-600">{message}</p>}
    </section>
  )
}
