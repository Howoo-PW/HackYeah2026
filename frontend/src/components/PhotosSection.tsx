import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError, fetchPhotos, postPhoto } from '../api/client'
import type { Photo } from '../api/types'
import { useAuth } from '../auth/useAuth'

const PAGE_SIZE = 12
const MAX_BYTES = 5 * 1024 * 1024 // contract: photo up to 5 MB
const MAX_SIDE = 2560
const TYPES = ['image/jpeg', 'image/png', 'image/webp']

/**
 * Makes a phone photo fit the 5 MB limit: files already small enough go as they are, bigger ones are scaled down
 * (longest side 2560 px) and re-encoded as JPEG in the browser.
 */
async function fitForUpload(file: File): Promise<File> {
  if (file.size <= MAX_BYTES * 0.8) return file
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85))
  if (!blob) throw new Error('Nie udało się przygotować zdjęcia.')
  return new File([blob], file.name.replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' })
}

/** Photo gallery of one road piece with an "add photo" button for signed-in users; a click on a thumbnail opens the full photo. */
export default function PhotosSection({ segmentId }: { segmentId: number }) {
  const { user, openLogin, configured } = useAuth()
  const [photos, setPhotos] = useState<Photo[]>([])
  const [total, setTotal] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<Photo | null>(null)
  const input = useRef<HTMLInputElement>(null)

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

  const onPick = async (file: File | undefined) => {
    if (!file) return
    setError(null)
    if (!TYPES.includes(file.type)) return setError('Dozwolone są pliki JPEG, PNG i WebP.')
    setBusy(true)
    try {
      const photo = await postPhoto(segmentId, await fitForUpload(file))
      setPhotos((prev) => [photo, ...prev])
      setTotal((t) => (t ?? 0) + 1)
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) openLogin()
      setError(err instanceof Error ? err.message : 'Nie udało się dodać zdjęcia.')
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <section className="mt-5 border-t border-gray-100 pt-4">
      <h3 className="text-sm font-semibold">Zdjęcia{total !== null && total > 0 && ` (${total})`}</h3>

      {user ? (
        <>
          <input
            ref={input}
            type="file"
            accept={TYPES.join(',')}
            className="sr-only"
            aria-label="Wybierz zdjęcie"
            onChange={(e) => onPick(e.target.files?.[0])}
          />
          <button
            onClick={() => input.current?.click()}
            disabled={busy}
            className="mt-2 w-full rounded-xl border border-dashed border-gray-300 py-2 text-sm font-medium text-gray-700 transition hover:border-gray-900 hover:bg-gray-50 disabled:opacity-50"
          >
            {busy ? 'Wysyłam…' : '+ Dodaj zdjęcie'}
          </button>
        </>
      ) : (
        <button
          onClick={openLogin}
          disabled={!configured}
          className="mt-2 w-full rounded-xl border border-dashed border-gray-300 py-2 text-sm font-medium text-gray-700 transition hover:border-gray-900 hover:bg-gray-50 disabled:opacity-50"
        >
          Zaloguj się, aby dodać zdjęcie
        </button>
      )}
      {error && <p className="mt-2 rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</p>}

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
