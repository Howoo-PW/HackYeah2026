import { metricScore, type Metric } from '../lib/dimensions'
import { supabase } from '../lib/supabase'
import { mockComments, mockSegmentDetail, mockSegments } from './mocks'
import type { ApiError, AssistantResponse, Bbox, GroupDetail, NearestSegment, Opinion, Paginated, Rating, RatingInput, RouteRequest, RouteResult, GroupMapCollection, MyOpinion, Photo, SegmentCollection, SegmentDetail, StreetHit } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'
/** Force mock data even when the backend is up (set VITE_USE_MOCKS=true). */
const FORCE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'

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

/** Sends a request; with `auth` the signed-in user's token goes along (when there is one), so the answer can include "my ..." fields. */
async function request<T>(path: string, signal?: AbortSignal, post?: unknown, auth = false): Promise<T> {
  const authorization = auth ? await optionalAuthHeader() : {}
  const res = await fetch(`${API_URL}${path}`, {
    signal,
    headers: { ...authorization, ...(post !== undefined && { 'Content-Type': 'application/json' }) },
    ...(post !== undefined && { method: 'POST', body: JSON.stringify(post) }),
  })
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiError | null
    throw new ApiRequestError(res.status, body?.error.code ?? 'INTERNAL_ERROR', body?.error.message ?? res.statusText, body?.error.details ?? null)
  }
  return res.json() as Promise<T>
}

export type SegmentsResult = { data: SegmentCollection; mock: boolean }

export type SegmentFilter = {
  /** Metric the min score applies to. `overall` is filtered on the client (contract only filters by one dimension). */
  dimension: Metric | null
  minScore: number | null
  /** Client-side only: the contract has no query parameter for it, so we drop segments with active obstacles. */
  noObstacles: boolean
}

/**
 * GET /segments for the given viewport. Falls back to mock data when the backend is unreachable
 * (network error or 5xx); contract errors such as 422 "zoom in" are rethrown so the UI can show them.
 */
export async function fetchSegments(bbox: Bbox, filter: SegmentFilter, signal?: AbortSignal): Promise<SegmentsResult> {
  if (!FORCE_MOCKS) {
    const params = new URLSearchParams({ bbox: bbox.map((n) => n.toFixed(5)).join(',') })
    if (filter.dimension && filter.dimension !== 'overall' && filter.minScore !== null) {
      params.set('dimension', filter.dimension)
      params.set('min_score', String(filter.minScore))
    }
    try {
      const data = await request<SegmentCollection>(`/segments?${params}`, signal)
      return { data: clientFilter(data, filter), mock: false }
    } catch (err) {
      if (signal?.aborted) throw err
      if (err instanceof ApiRequestError && err.status < 500) throw err
    }
  }
  return { data: applyMockFilter(mockSegments(bbox), filter), mock: true }
}

/**
 * GET /groups?bbox= : fragments for zoomed-out views (the whole city is about 5 000 features). Unlike
 * {@link fetchSegments} there is no mock fallback; errors are rethrown for the UI.
 */
export async function fetchGroupMap(bbox: Bbox, filter: SegmentFilter, signal?: AbortSignal): Promise<GroupMapCollection> {
  const params = new URLSearchParams({ bbox: bbox.map((n) => n.toFixed(5)).join(',') })
  if (filter.dimension && filter.dimension !== 'overall' && filter.minScore !== null) {
    params.set('dimension', filter.dimension)
    params.set('min_score', String(filter.minScore))
  }
  return request<GroupMapCollection>(`/groups?${params}`, signal)
}

/**
 * GET /segments/{id}. Same mock fallback as {@link fetchSegments}. Sent with the user's token when signed in, so the road
 * comes back with the user's own rating, comment and photo (`my_rating`, `my_comment`, `my_photo`), also after a page reload.
 */
export async function fetchSegmentDetail(id: number, signal?: AbortSignal): Promise<SegmentDetail> {
  if (!FORCE_MOCKS) {
    try {
      try {
        return await request<SegmentDetail>(`/segments/${id}`, signal, undefined, true)
      } catch (err) {
        // A stale token must not hide the road: read it as a visitor (without "my ..." fields).
        if (err instanceof ApiRequestError && err.status === 401) return await request<SegmentDetail>(`/segments/${id}`, signal)
        throw err
      }
    } catch (err) {
      if (signal?.aborted) throw err
      if (err instanceof ApiRequestError && err.status < 500) throw err
    }
  }
  const detail = mockSegmentDetail(id)
  if (!detail) throw new ApiRequestError(404, 'NOT_FOUND', 'Nie znaleziono odcinka')
  return detail
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

/** GET /segments/{id}/comments, newest first (typed as Opinion: see the note on that type). Same mock fallback as {@link fetchSegments}. */
export async function fetchComments(id: number, page: number, pageSize: number, signal?: AbortSignal): Promise<Paginated<Opinion>> {
  if (!FORCE_MOCKS) {
    try {
      return await request<Paginated<Opinion>>(`/segments/${id}/comments?page=${page}&page_size=${pageSize}`, signal)
    } catch (err) {
      if (signal?.aborted) throw err
      if (err instanceof ApiRequestError && err.status < 500) throw err
    }
  }
  return mockComments(id, page, pageSize)
}

/** Mock stand-in for the server-side filter (dimension + min_score) plus the client-side ones. */
function applyMockFilter(data: SegmentCollection, filter: SegmentFilter): SegmentCollection {
  const { dimension, minScore } = filter
  const features = clientFilter(data, filter).features.filter((f) => {
    if (dimension && dimension !== 'overall' && minScore !== null) {
      const v = f.properties.scores[dimension]
      return v !== null && v >= minScore
    }
    return true
  })
  return { ...data, features }
}

/** Fired after a rating, comment or photo is saved, so the opinions list and the map can refresh. */
export const OPINIONS_CHANGED = 'opinions-changed'

/** `Authorization: Bearer <Supabase access token>` for the signed-in user; throws a 401 error when nobody is signed in. */
async function authHeader(): Promise<Record<string, string>> {
  const { data } = (await supabase?.auth.getSession()) ?? { data: { session: null } }
  if (!data.session) throw new ApiRequestError(401, 'UNAUTHORIZED', 'Zaloguj się, aby to zrobić.')
  return { Authorization: `Bearer ${data.session.access_token}` }
}

/** Like {@link authHeader}, but anonymous visitors simply get no header (public reads work for everybody). */
async function optionalAuthHeader(): Promise<Record<string, string>> {
  const { data } = (await supabase?.auth.getSession()) ?? { data: { session: null } }
  return data.session ? { Authorization: `Bearer ${data.session.access_token}` } : {}
}

/** Sends an authenticated write (JSON or multipart) and returns the parsed response. */
async function write<T>(path: string, body: BodyInit, json: boolean, method = 'POST'): Promise<T> {
  const headers = { ...(await authHeader()), ...(json && { 'Content-Type': 'application/json' }) }
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, { method, headers, body })
  } catch {
    throw new ApiRequestError(0, 'NETWORK', 'Brak połączenia z serwerem.')
  }
  if (!res.ok) {
    const err = (await res.json().catch(() => null)) as ApiError | null
    throw new ApiRequestError(res.status, err?.error.code ?? 'INTERNAL_ERROR', err?.error.message ?? res.statusText, err?.error.details ?? null)
  }
  window.dispatchEvent(new Event(OPINIONS_CHANGED))
  return res.json() as Promise<T>
}

/** POST /segments/{id}/ratings: creates the user's rating of the road or replaces the previous one, whichever day (201 new / 200 replaced). Only filled dimensions are sent. */
export async function postRating(segmentId: number, input: RatingInput): Promise<Rating> {
  const body = Object.fromEntries(Object.entries(input).filter(([, v]) => v !== null && v !== undefined))
  return write<Rating>(`/segments/${segmentId}/ratings`, JSON.stringify(body), true)
}

/** POST /segments/{id}/comments: the comment comes back with the author's latest rating of the road, when there is one. */
export async function postComment(segmentId: number, text: string): Promise<Opinion> {
  return write<Opinion>(`/segments/${segmentId}/comments`, JSON.stringify({ text }), true)
}

/** PUT /segments/{id}/comments/mine: writes the user's comment on the road, replacing the previous one (NOT IN docs/CONTRACT.md yet). */
export async function putMyComment(segmentId: number, text: string): Promise<Opinion> {
  return write<Opinion>(`/segments/${segmentId}/comments/mine`, JSON.stringify({ text }), true, 'PUT')
}

/** Sends an authenticated DELETE that answers 204 (no body). */
async function remove(path: string): Promise<void> {
  const headers = await authHeader()
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, { method: 'DELETE', headers })
  } catch {
    throw new ApiRequestError(0, 'NETWORK', 'Brak połączenia z serwerem.')
  }
  if (!res.ok) {
    const err = (await res.json().catch(() => null)) as ApiError | null
    throw new ApiRequestError(res.status, err?.error.code ?? 'INTERNAL_ERROR', err?.error.message ?? res.statusText, err?.error.details ?? null)
  }
  window.dispatchEvent(new Event(OPINIONS_CHANGED))
}

/** DELETE /segments/{id}/comments/mine: removes the user's own comment on the road (NOT IN docs/CONTRACT.md yet). */
export async function deleteMyComment(segmentId: number): Promise<void> {
  return remove(`/segments/${segmentId}/comments/mine`)
}

/** DELETE /segments/{id}/photos/mine: removes the user's own photos on the road, except `keepId` (the new one); NOT IN docs/CONTRACT.md yet. */
export async function deleteMyPhotos(segmentId: number, keepId?: string): Promise<void> {
  return remove(`/segments/${segmentId}/photos/mine${keepId ? `?keep=${encodeURIComponent(keepId)}` : ''}`)
}

/** GET /segments/{id}/photos: visible photos with signed URLs, newest first. */
export async function fetchPhotos(segmentId: number, page: number, pageSize: number, signal?: AbortSignal): Promise<Paginated<Photo>> {
  return request<Paginated<Photo>>(`/segments/${segmentId}/photos?page=${page}&page_size=${pageSize}`, signal)
}

/** POST /segments/{id}/photos (multipart): JPEG / PNG / WebP up to 5 MB; the backend strips EXIF and makes a thumbnail. */
export async function postPhoto(segmentId: number, file: File): Promise<Photo> {
  const form = new FormData()
  form.append('file', file)
  return write<Photo>(`/segments/${segmentId}/photos`, form, false)
}

/** GET /segments/{id}/street: ids of the whole street (same name, joined end to end) the road belongs to; null when it cannot be loaded. */
export async function fetchStreetIds(segmentId: number, signal?: AbortSignal): Promise<number[] | null> {
  try {
    return (await request<{ segment_ids: number[] }>(`/segments/${segmentId}/street`, signal)).segment_ids
  } catch {
    return null
  }
}

/**
 * GET /segments/nearest: the street under a point, used to show a name instead of coordinates.
 * Best effort: returns null when there is no segment within 50 m or the backend is unavailable.
 */
export async function fetchNearestSegment(lat: number, lon: number, signal?: AbortSignal): Promise<NearestSegment | null> {
  if (FORCE_MOCKS) return null
  try {
    return await request<NearestSegment>(`/segments/nearest?lat=${lat}&lon=${lon}`, signal)
  } catch (err) {
    if (signal?.aborted) throw err
    return null
  }
}

/**
 * GET /search: street autocomplete from our own database (contract 5.10).
 * Returns null when the backend cannot answer (down, older version without the endpoint, rate limit),
 * so the caller can fall back to another source.
 */
export async function fetchStreets(query: string, limit: number, signal?: AbortSignal): Promise<StreetHit[] | null> {
  if (FORCE_MOCKS) return null
  try {
    const res = await request<{ items: StreetHit[] }>(`/search?q=${encodeURIComponent(query)}&limit=${limit}`, signal)
    return res.items
  } catch (err) {
    if (signal?.aborted) throw err
    return null
  }
}

/**
 * GET /groups/{id}: the street stretch a segment belongs to. Best effort: null when the backend cannot
 * answer, in which case the panel simply shows the single segment.
 */
export async function fetchGroup(id: number, signal?: AbortSignal): Promise<GroupDetail | null> {
  if (FORCE_MOCKS) return null
  try {
    return await request<GroupDetail>(`/groups/${id}`, signal)
  } catch (err) {
    if (signal?.aborted) throw err
    return null
  }
}

/**
 * POST /route: up to three alternative routes, best first for the given weights (contract 5.8).
 * Errors keep the server's message (e.g. 422 OUT_OF_AREA, 502 when the routing engine is down).
 */
export async function fetchRoutes(req: RouteRequest, signal?: AbortSignal): Promise<RouteResult[]> {
  try {
    return (await request<{ routes: RouteResult[] }>('/route', signal, req)).routes
  } catch (err) {
    if (signal?.aborted || err instanceof ApiRequestError) throw err
    throw new ApiRequestError(0, 'NETWORK', 'Nie można połączyć się z serwerem tras. Spróbuj ponownie.')
  }
}

/** GET /me/opinions: the signed-in user's own ratings and comments, newest first. Needs the Supabase access token. */
export async function fetchMyOpinions(accessToken: string, signal?: AbortSignal): Promise<MyOpinion[]> {
  const res = await fetch(`${API_URL}/me/opinions`, { signal, headers: { Authorization: `Bearer ${accessToken}` } })
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiError | null
    throw new ApiRequestError(res.status, body?.error.code ?? 'INTERNAL_ERROR', body?.error.message ?? res.statusText, body?.error.details ?? null)
  }
  return res.json() as Promise<MyOpinion[]>
}

/**
 * POST /assistant: describe a route or a place in words. Takes several seconds (the model reads the request, the backend
 * routes and collects ratings and comments, the model writes the answer). Errors keep the server's status (429 too many questions,
 * 502 AI unavailable).
 */
export async function askAssistant(query: string, signal?: AbortSignal): Promise<AssistantResponse> {
  try {
    return await request<AssistantResponse>('/assistant', signal, { query })
  } catch (err) {
    if (signal?.aborted || err instanceof ApiRequestError) throw err
    throw new ApiRequestError(0, 'NETWORK', 'Brak połączenia z serwerem.')
  }
}
