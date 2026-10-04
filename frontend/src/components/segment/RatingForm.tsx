import { useEffect, useRef, useState } from 'react'
import { ApiRequestError, deleteMyComment, deleteMyPhotos, postPhoto, postRating, putMyComment } from '../../api/client'
import type { Dimension, Opinion, Photo, Rating, TimeOfDay } from '../../api/types'
import { useAuth } from '../../auth/useAuth'
import { DIMENSIONS } from '../../lib/dimensions'
import { PHOTO_TYPES, fitForUpload } from '../../lib/image'

const COMMENT_MAX = 1000 // contract: comment text 1-1000 characters

const TIMES: { id: TimeOfDay | 'auto'; label: string }[] = [
  { id: 'auto', label: 'Teraz (automatycznie)' },
  { id: 'morning', label: 'Rano (6–10)' },
  { id: 'day', label: 'W ciągu dnia (10–16)' },
  { id: 'evening', label: 'Wieczorem (16–22)' },
  { id: 'night', label: 'W nocy (22–6)' },
]

type Values = Record<Dimension, number | null>

function emptyValues(existing: Rating | null): Values {
  return {
    surface: existing?.surface ?? null,
    views: existing?.views ?? null,
    safety: existing?.safety ?? null,
    traffic: existing?.traffic ?? null,
    parking: existing?.parking ?? null,
  }
}

type Props = {
  segmentId: number
  /** The user's current rating of this road, if any (a new one replaces it, whichever day it was made). */
  existing: Rating | null
  /** The user's current comment on this road, if any (a new text replaces it; an empty one removes it). */
  existingComment?: Opinion | null
  /** The user's current photo of this road, if any (a new photo replaces it). */
  existingPhoto?: Photo | null
  onSaved: (rating: Rating) => void
  /** Called once a comment or a photo was added, changed or removed along with the rating, so the lists below can reload. */
  onContentAdded?: () => void
}

type Step = 'rating' | 'comment' | 'photo'
const STEP_LABEL: Record<Step, string> = { rating: 'oceny', comment: 'komentarza', photo: 'zdjęcia' }

/**
 * Collapsible "your opinion" card: 1-5 stars per dimension (each optional, at least one required), plus an optional comment
 * and an optional photo that go together with the rating in one "Zapisz". There is one opinion per user and road: when the
 * user already has one, the form is filled with it ("Zmień swoją opinię") and saving replaces it (the new rating, the new
 * comment text, the new photo; an emptied comment or a removed photo is deleted). The parts are sent one after another
 * (rating, comment, photo); if a later step fails the finished ones are kept and a retry only repeats what is left.
 */
export default function RatingForm({ segmentId, existing, existingComment = null, existingPhoto = null, onSaved, onContentAdded }: Props) {
  const { user, openLogin, configured } = useAuth()
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState<Values>(() => emptyValues(existing))
  const [time, setTime] = useState<TimeOfDay | 'auto'>('auto')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [comment, setComment] = useState('')
  const [photo, setPhoto] = useState<{ file: File; url: string } | null>(null)
  const [removeOldPhoto, setRemoveOldPhoto] = useState(false)
  const [done, setDone] = useState<Set<Step>>(new Set())
  const input = useRef<HTMLInputElement>(null)

  // The preview is an object URL: it is made when a file is picked and released when replaced, removed or on unmount.
  const photoUrl = useRef<string | null>(null)
  const setPickedPhoto = (file: File | null) => {
    if (photoUrl.current) URL.revokeObjectURL(photoUrl.current)
    photoUrl.current = file ? URL.createObjectURL(file) : null
    setPhoto(file && photoUrl.current ? { file, url: photoUrl.current } : null)
  }
  useEffect(
    () => () => {
      if (photoUrl.current) URL.revokeObjectURL(photoUrl.current)
    },
    [],
  )

  const filled = Object.values(values).some((v) => v !== null)
  const hasOpinion = Boolean(existing || existingComment || existingPhoto)

  if (!user) {
    return (
      <button
        onClick={openLogin}
        disabled={!configured}
        className="mt-4 w-full rounded-xl border border-dashed border-gray-300 py-2.5 text-sm font-medium text-gray-700 transition hover:border-gray-900 hover:bg-gray-50 disabled:opacity-50"
      >
        ★ Zaloguj się, aby ocenić tę drogę
      </button>
    )
  }

  if (!open) {
    return (
      <button
        onClick={() => {
          setValues(emptyValues(existing))
          setTime('auto')
          setComment(existingComment?.text ?? '')
          setPickedPhoto(null)
          setRemoveOldPhoto(false)
          setDone(new Set())
          setError(null)
          setSaved(false)
          setOpen(true)
        }}
        className="mt-4 w-full rounded-xl bg-gray-900 py-2.5 text-sm font-semibold text-white transition hover:bg-gray-700"
      >
        {hasOpinion ? '✎ Zmień swoją opinię' : '★ Oceń tę drogę'}
      </button>
    )
  }

  const pickPhoto = (file: File | undefined) => {
    if (!file) return
    if (!PHOTO_TYPES.includes(file.type)) return setError('Dozwolone są pliki JPEG, PNG i WebP.')
    setError(null)
    setPickedPhoto(file)
  }

  const submit = async () => {
    setBusy(true)
    setError(null)
    const finished = new Set(done)
    let step: Step = 'rating'
    let contentChanged = false
    try {
      if (!finished.has('rating')) {
        onSaved(await postRating(segmentId, { ...values, ...(time === 'auto' ? {} : { time_of_day: time }) }))
        finished.add('rating')
      }
      const text = comment.trim()
      if (!finished.has('comment') && text !== (existingComment?.text ?? '')) {
        step = 'comment'
        if (text) await putMyComment(segmentId, text)
        else await deleteMyComment(segmentId)
        finished.add('comment')
        contentChanged = true
      }
      if (!finished.has('photo') && (photo || (removeOldPhoto && existingPhoto))) {
        step = 'photo'
        if (photo) {
          const added = await postPhoto(segmentId, await fitForUpload(photo.file))
          if (existingPhoto) await deleteMyPhotos(segmentId, added.id) // the new photo replaces the old one(s)
        } else {
          await deleteMyPhotos(segmentId)
        }
        finished.add('photo')
        contentChanged = true
      }
      setSaved(true)
      setOpen(false)
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) openLogin()
      const reason = err instanceof Error ? err.message : 'Spróbuj ponownie.'
      setError(
        finished.has('rating')
          ? `Ocena zapisana, ale nie udało się zmienić ${STEP_LABEL[step]}. ${reason} Kliknij „Zapisz opinię”, żeby ponowić brakujące.`
          : `Nie udało się zapisać oceny. ${reason}`,
      )
    } finally {
      setDone(finished)
      setBusy(false)
      if (contentChanged) onContentAdded?.()
    }
  }

  const showOldPhoto = existingPhoto && !removeOldPhoto && !photo

  return (
    <section className="mt-4 rounded-xl border border-gray-200 p-3">
      <h3 className="text-sm font-semibold">{hasOpinion ? 'Zmień swoją opinię' : 'Twoja opinia'}</h3>
      {hasOpinion && <p className="mt-0.5 text-xs text-gray-500">Zapisanie zastąpi Twoją poprzednią opinię o tej drodze.</p>}
      <ul className="mt-2 space-y-2">
        {DIMENSIONS.map((d) => (
          <li key={d.id} className="flex items-center justify-between gap-2 text-sm">
            <span>{d.label}</span>
            <StarPicker
              label={d.label}
              value={values[d.id]}
              onChange={(v) => setValues((cur) => ({ ...cur, [d.id]: v }))}
            />
          </li>
        ))}
      </ul>
      <p className="mt-1 text-[11px] text-gray-400">5 = najlepiej (przy obciążeniu: 5 = płynnie, bez problemów). Kliknij gwiazdkę ponownie, żeby wyczyścić.</p>

      <label className="mt-3 block text-sm">
        <span className="text-gray-600">Pora dnia</span>
        <select
          value={time}
          onChange={(e) => setTime(e.target.value as TimeOfDay | 'auto')}
          className="mt-1 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
        >
          {TIMES.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </label>

      <label className="mt-3 block text-sm">
        <span className="text-gray-600">Komentarz (opcjonalnie)</span>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          maxLength={COMMENT_MAX}
          rows={3}
          disabled={done.has('comment')}
          placeholder="Napisz, jak się tędy jeździ lub chodzi…"
          className="mt-1 w-full resize-y rounded-lg border border-gray-300 p-2 text-sm outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 disabled:bg-gray-50"
        />
        <span className="flex justify-between text-xs text-gray-400">
          <span>{existingComment?.status === 'hidden' ? 'Twój komentarz jest ukryty przez moderatora.' : existingComment ? 'Pusty komentarz usunie Twój poprzedni.' : ''}</span>
          <span>
            {comment.length}/{COMMENT_MAX}
          </span>
        </span>
      </label>

      <div className="mt-2 text-sm">
        <span className="text-gray-600">Zdjęcie (opcjonalnie)</span>
        <input ref={input} type="file" accept={PHOTO_TYPES.join(',')} className="sr-only" aria-label="Wybierz zdjęcie" onChange={(e) => pickPhoto(e.target.files?.[0])} />
        {photo ? (
          <div className="mt-1 flex items-center gap-2">
            <img src={photo.url} alt="Wybrane zdjęcie" className="h-16 w-16 rounded-lg object-cover" />
            <span className="min-w-0 flex-1 truncate text-gray-700">{photo.file.name}</span>
            {!done.has('photo') && (
              <button
                type="button"
                onClick={() => {
                  setPickedPhoto(null)
                  if (input.current) input.current.value = ''
                }}
                aria-label="Usuń wybrane zdjęcie"
                className="rounded-full px-2 py-1 text-gray-600 hover:bg-gray-100"
              >
                ✕
              </button>
            )}
          </div>
        ) : showOldPhoto ? (
          <div className="mt-1 flex items-center gap-2">
            <img src={existingPhoto.thumbnail_url} alt="Twoje dotychczasowe zdjęcie" className="h-16 w-16 rounded-lg object-cover" />
            <span className="min-w-0 flex-1 text-gray-700">Twoje zdjęcie</span>
            <button type="button" onClick={() => input.current?.click()} className="rounded-lg px-2 py-1 text-sky-700 hover:bg-gray-100">
              Zmień
            </button>
            <button type="button" onClick={() => setRemoveOldPhoto(true)} aria-label="Usuń swoje zdjęcie" className="rounded-full px-2 py-1 text-gray-600 hover:bg-gray-100">
              ✕
            </button>
          </div>
        ) : (
          <>
            <button
              type="button"
              onClick={() => input.current?.click()}
              className="mt-1 w-full rounded-lg border border-dashed border-gray-300 py-2 text-sm font-medium text-gray-700 transition hover:border-gray-900 hover:bg-gray-50"
            >
              + Dodaj zdjęcie
            </button>
            {existingPhoto && removeOldPhoto && (
              <p className="mt-1 text-xs text-gray-500">
                Twoje dotychczasowe zdjęcie zostanie usunięte.{' '}
                <button type="button" onClick={() => setRemoveOldPhoto(false)} className="text-sky-700 hover:underline">
                  Cofnij
                </button>
              </p>
            )}
          </>
        )}
      </div>

      {error && <p className="mt-2 rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</p>}

      <div className="mt-3 flex gap-2">
        <button
          onClick={submit}
          disabled={!filled || busy}
          className="flex-1 rounded-lg bg-gray-900 py-2 text-sm font-semibold text-white transition hover:bg-gray-700 disabled:opacity-40"
        >
          {busy ? 'Zapisuję…' : hasOpinion ? 'Zapisz zmiany' : 'Zapisz opinię'}
        </button>
        <button onClick={() => setOpen(false)} className="rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-100">
          Anuluj
        </button>
      </div>
      {saved && <span className="sr-only">Zapisano</span>}
    </section>
  )
}

/** 1–5 clickable stars; clicking the selected value clears it (rating a dimension is optional). */
function StarPicker({ label, value, onChange }: { label: string; value: number | null; onChange: (v: number | null) => void }) {
  const [hover, setHover] = useState<number | null>(null)
  const shown = hover ?? value ?? 0
  return (
    <span className="flex" role="radiogroup" aria-label={`Ocena: ${label}`} onMouseLeave={() => setHover(null)}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} z 5`}
          onMouseEnter={() => setHover(n)}
          onClick={() => onChange(value === n ? null : n)}
          className={`px-0.5 text-2xl leading-none transition ${n <= shown ? 'text-amber-400' : 'text-gray-300'}`}
        >
          ★
        </button>
      ))}
    </span>
  )
}
