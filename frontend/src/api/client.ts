import { metricScore, type Metric } from '../lib/dimensions'
import { supabase } from '../lib/supabase'
import type { ApiError, AssistantResponse, Bbox, GroupDetail, NearestSegment, Opinion, Paginated, Rating, RatingInput, RouteRequest, RouteResult, GroupMapCollection, MyOpinion, Photo, SegmentCollection, SegmentDetail, StreetHit } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'

/** Fired after a rating, comment or photo is saved, so the opinions list and the map can refresh. */
export const OPINIONS_CHANGED = 'opinions-changed'

export class ApiRequestError extends Error {
  status: number
  code: string
  /** Contract `error.details`, e.g. `{ field: "via[0]" }` for a point that is too far from any road. */
  details: Record<string, unknown> | null

  constructor(status: number, code: string, message: string, details: Record<string, unknown> | null = null) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

/** `none`: public call; `optional`: the token goes along when the user is signed in; `required`: 401 error when nobody is. */
type Auth = 'none' | 'optional' | 'required'

type SendOptions = {
  signal?: AbortSignal
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  /** JSON-encoded unless it is a `FormData` (multipart upload). */
  body?: unknown
  auth?: Auth
  /** Announce a successful write on {@link OPINIONS_CHANGED}. */
  changes?: boolean
  /** Message for a network failure (no answer from the server at all). */
  offline?: string
}

async function authHeaders(auth: Auth): Promise<Record<string, string>> {
  if (auth === 'none') return {}
  const { data } = (await supabase?.auth.getSession()) ?? { data: { session: null } }
  if (data.session) return { Authorization: `Bearer ${data.session.access_token}` }
  if (auth === 'required') throw new ApiRequestError(401, 'UNAUTHORIZED', 'Zaloguj się, aby to zrobić.')
  return {}
}

/**
 * Sends one API request and returns the parsed JSON (undefined for 204). Contract errors become `ApiRequestError`
 * with the server's `error.code`, message and details; a network failure becomes status 0, code `NETWORK`.
 * An aborted request rethrows the `AbortError`.
 */
async function send<T>(path: string, { signal, method = 'GET', body, auth = 'none', changes = false, offline = 'Brak połączenia z serwerem.' }: SendOptions = {}): Promise<T> {
  const headers: Record<string, string> = await authHeaders(auth)
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, { signal, method, headers, body: payload })
  } catch (err) {
    if (signal?.aborted) throw err
    throw new ApiRequestError(0, 'NETWORK', offline)
  }
  if (!res.ok) {
    const error = (await res.json().catch(() => null)) as ApiError | null
    throw new ApiRequestError(res.status, error?.error.code ?? 'INTERNAL_ERROR', error?.error.message ?? res.statusText, error?.error.details ?? null)
  }
  if (changes) window.dispatchEvent(new Event(OPINIONS_CHANGED))
  return (res.status === 204 ? undefined : await res.json()) as T
}

/** Like {@link send}, but any failure (other than an abort) gives `null`: for helpers the UI can do without. */
async function sendOrNull<T>(path: string, signal?: AbortSignal): Promise<T | null> {
  try {
    return await send<T>(path, { signal })
  } catch (err) {
    if (signal?.aborted) throw err
    return null
  }
}

export type SegmentFilter = {
  /** Metric the min score applies to. `overall` is filtered on the client (contract only filters by one dimension). */
  dimension: Metric | null
  minScore: number | null
  /** Client-side only: the contract has no query parameter for it, so we drop segments with active obstacles. */
  noObstacles: boolean
}

/** Query string of the map endpoints: the viewport plus the server-side part of the filter (one dimension and its minimum). */
function mapParams(bbox: Bbox, { dimension, minScore }: SegmentFilter): URLSearchParams {
  const params = new URLSearchParams({ bbox: bbox.map((n) => n.toFixed(5)).join(',') })
  if (dimension && dimension !== 'overall' && minScore !== null) {
    params.set('dimension', dimension)
    params.set('min_score', String(minScore))
  }
  return params
}

/** Filters the contract cannot do on the server: no active obstacles and the overall-score minimum. */
function clientFilter(data: SegmentCollection, { noObstacles, dimension, minScore }: SegmentFilter): SegmentCollection {
  const overallMin = dimension === 'overall' ? minScore : null
  if (!noObstacles && overallMin === null) return data
  const features = data.features.filter((f) => {
    if (noObstacles && f.properties.active_obstacles_count > 0) return false
    if (overallMin !== null) {
      const v = metricScore(f.properties.scores, 'overall')
      return v !== null && v >= overallMin
    }
    return true
  })
  return { ...data, features }
}

/** GET /segments for the given viewport (errors such as 422 "zoom in" are thrown for the UI to show). */
export async function fetchSegments(bbox: Bbox, filter: SegmentFilter, signal?: AbortSignal): Promise<SegmentCollection> {
  return clientFilter(await send<SegmentCollection>(`/segments?${mapParams(bbox, filter)}`, { signal }), filter)
}

/** GET /groups?bbox= : fragments for zoomed-out views (the whole city is about 5 000 features). */
export async function fetchGroupMap(bbox: Bbox, filter: SegmentFilter, signal?: AbortSignal): Promise<GroupMapCollection> {
  return send<GroupMapCollection>(`/groups?${mapParams(bbox, filter)}`, { signal })
}

/**
 * GET /segments/{id}. Sent with the user's token when signed in, so the road comes back with the user's own rating,
 * comment and photo (`my_rating`, `my_comment`, `my_photo`), also after a page reload.
 */
export async function fetchSegmentDetail(id: number, signal?: AbortSignal): Promise<SegmentDetail> {
  try {
    return await send<SegmentDetail>(`/segments/${id}`, { signal, auth: 'optional' })
  } catch (err) {
    // A stale token must not hide the road: read it as a visitor (without "my ..." fields).
    if (err instanceof ApiRequestError && err.status === 401) return send<SegmentDetail>(`/segments/${id}`, { signal })
    throw err
  }
}

/** GET /segments/{id}/comments, newest first (typed as Opinion: see the note on that type). */
export async function fetchComments(id: number, page: number, pageSize: number, signal?: AbortSignal): Promise<Paginated<Opinion>> {
  return send<Paginated<Opinion>>(`/segments/${id}/comments?page=${page}&page_size=${pageSize}`, { signal })
}

/** POST /segments/{id}/ratings: creates the user's rating of the road or replaces the previous one, whichever day (201 new / 200 replaced). Only filled dimensions are sent. */
export async function postRating(segmentId: number, input: RatingInput): Promise<Rating> {
  const body = Object.fromEntries(Object.entries(input).filter(([, v]) => v !== null && v !== undefined))
  return send<Rating>(`/segments/${segmentId}/ratings`, { method: 'POST', body, auth: 'required', changes: true })
}

/** PUT /segments/{id}/comments/mine: writes the user's comment on the road, replacing the previous one (NOT IN docs/CONTRACT.md yet). */
export async function putMyComment(segmentId: number, text: string): Promise<Opinion> {
  return send<Opinion>(`/segments/${segmentId}/comments/mine`, { method: 'PUT', body: { text }, auth: 'required', changes: true })
}

/** DELETE /segments/{id}/comments/mine: removes the user's own comment on the road (NOT IN docs/CONTRACT.md yet). */
export async function deleteMyComment(segmentId: number): Promise<void> {
  return send<void>(`/segments/${segmentId}/comments/mine`, { method: 'DELETE', auth: 'required', changes: true })
}

/** DELETE /segments/{id}/photos/mine: removes the user's own photos on the road, except `keepId` (the new one); NOT IN docs/CONTRACT.md yet. */
export async function deleteMyPhotos(segmentId: number, keepId?: string): Promise<void> {
  return send<void>(`/segments/${segmentId}/photos/mine${keepId ? `?keep=${encodeURIComponent(keepId)}` : ''}`, { method: 'DELETE', auth: 'required', changes: true })
}

/** GET /segments/{id}/photos: visible photos with signed URLs, newest first. */
export async function fetchPhotos(segmentId: number, page: number, pageSize: number, signal?: AbortSignal): Promise<Paginated<Photo>> {
  return send<Paginated<Photo>>(`/segments/${segmentId}/photos?page=${page}&page_size=${pageSize}`, { signal })
}

/** POST /segments/{id}/photos (multipart): JPEG / PNG / WebP up to 5 MB; the backend strips EXIF and makes a thumbnail. */
export async function postPhoto(segmentId: number, file: File): Promise<Photo> {
  const form = new FormData()
  form.append('file', file)
  return send<Photo>(`/segments/${segmentId}/photos`, { method: 'POST', body: form, auth: 'required', changes: true })
}

/** GET /segments/{id}/street: ids of the whole street (same name, joined end to end) the road belongs to; null when it cannot be loaded. */
export async function fetchStreetIds(segmentId: number, signal?: AbortSignal): Promise<number[] | null> {
  return (await sendOrNull<{ segment_ids: number[] }>(`/segments/${segmentId}/street`, signal))?.segment_ids ?? null
}

/** GET /segments/nearest: the street under a point (null when there is no segment within 50 m or the backend is unavailable). */
export async function fetchNearestSegment(lat: number, lon: number, signal?: AbortSignal): Promise<NearestSegment | null> {
  return sendOrNull<NearestSegment>(`/segments/nearest?lat=${lat}&lon=${lon}`, signal)
}

/**
 * GET /search: street autocomplete from our own database (contract 5.10).
 * Returns null when the backend cannot answer (down, older version without the endpoint, rate limit),
 * so the caller can fall back to another source.
 */
export async function fetchStreets(query: string, limit: number, signal?: AbortSignal): Promise<StreetHit[] | null> {
  return (await sendOrNull<{ items: StreetHit[] }>(`/search?q=${encodeURIComponent(query)}&limit=${limit}`, signal))?.items ?? null
}

/** GET /groups/{id}: the street stretch a segment belongs to (null when the backend cannot answer: the panel then shows the single segment). */
export async function fetchGroup(id: number, signal?: AbortSignal): Promise<GroupDetail | null> {
  return sendOrNull<GroupDetail>(`/groups/${id}`, signal)
}

/**
 * POST /route: up to three alternative routes, best first for the given weights (contract 5.8).
 * Errors keep the server's message (e.g. 422 OUT_OF_AREA, 502 when the routing engine is down).
 */
export async function fetchRoutes(req: RouteRequest, signal?: AbortSignal): Promise<RouteResult[]> {
  const res = await send<{ routes: RouteResult[] }>('/route', { signal, method: 'POST', body: req, offline: 'Nie można połączyć się z serwerem tras. Spróbuj ponownie.' })
  return res.routes
}

/** GET /me/opinions: the signed-in user's own ratings and comments, newest first. */
export async function fetchMyOpinions(signal?: AbortSignal): Promise<MyOpinion[]> {
  return send<MyOpinion[]>('/me/opinions', { signal, auth: 'required' })
}

/**
 * POST /assistant: describe a route or a place in words. Takes several seconds (the model reads the request, the backend
 * routes and collects ratings and comments, the model writes the answer). Errors keep the server's status (429 too many questions,
 * 502 AI unavailable).
 */
export async function askAssistant(query: string, signal?: AbortSignal): Promise<AssistantResponse> {
  return send<AssistantResponse>('/assistant', { signal, method: 'POST', body: { query } })
}
