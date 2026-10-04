import { useCallback, useEffect, useState } from 'react'
import { fetchPhotos } from '../api/client'
import type { Photo } from '../api/types'

const PAGE_SIZE = 12

/**
 * Photo gallery of one road piece; a click on a thumbnail opens the full photo. Photos are added together with a rating
 * in the "Twoja opinia" form (RatingForm), not here. Remount (`key`) to reload after a new photo.
 */
export default function PhotosSection({ segmentId }: { segmentId: number }) {
  const [photos, setPhotos] = useState<Photo[]>([])
  const [total, setTotal] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<Photo | null>(null)

  const load = useCallback(
    (p: number, signal?: AbortSignal) =>
      fetchPhotos(segmentId, p, PAGE_SIZE, signal)
        .then((res) => {
          setPhotos((prev) => (p === 1 ? res.items : [...prev, ...res.items]))
          setTotal(res.total)
        })
        .catch(() => {
          // Photos are optional: without them the section just stays empty.
        }),
    [segmentId],
  )

  useEffect(() => {
    const ctrl = new AbortController()
    load(page, ctrl.signal)
    return () => ctrl.abort()
  }, [load, page])

  return (
    <section className="mt-5 border-t border-gray-100 pt-4">
      <h3 className="text-sm font-semibold">Zdjęcia{total !== null && total > 0 && ` (${total})`}</h3>
      {total === 0 && <p className="mt-2 text-sm text-gray-500">Brak zdjęć. Dodasz je, oceniając drogę.</p>}

      {photos.length > 0 && (
        <ul className="mt-3 grid grid-cols-3 gap-1.5">
          {photos.map((p) => (
            <li key={p.id}>
              <button onClick={() => setOpen(p)} className="block aspect-square w-full overflow-hidden rounded-lg bg-gray-100" aria-label="Powiększ zdjęcie">
                <img src={p.thumbnail_url} alt="Zdjęcie drogi" loading="lazy" className="h-full w-full object-cover transition hover:scale-105" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {total !== null && photos.length < total && (
        <button onClick={() => setPage((p) => p + 1)} className="mt-2 text-sm font-medium text-sky-700 hover:underline">
          Pokaż więcej zdjęć
        </button>
      )}

      {open && (
        <div
          role="dialog"
          aria-label="Zdjęcie"
          className="pointer-events-auto fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setOpen(null)}
        >
          <img src={open.url} alt="Zdjęcie drogi" className="max-h-full max-w-full rounded-lg object-contain" />
          <button
            onClick={() => setOpen(null)}
            aria-label="Zamknij"
            className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full bg-white/90 text-lg text-gray-900"
          >
            ✕
          </button>
        </div>
      )}
    </section>
  )
}
