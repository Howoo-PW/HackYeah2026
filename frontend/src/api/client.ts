import { metricScore, type Metric } from '../lib/dimensions'
import { mockComments, mockCreatedComment, mockCreatedRating, mockSegmentDetail, mockSegments } from './mocks'
import type { ApiError, Bbox, Opinion, Paginated, Rating, RatingInput, SegmentCollection, SegmentDetail } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'
/** Force mock data even when the backend is up (set VITE_USE_MOCKS=true). */
const FORCE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'

export class ApiRequestError extends Error {
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { signal })
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiError | null
    throw new ApiRequestError(res.status, body?.error.code ?? 'INTERNAL_ERROR', body?.error.message ?? res.statusText)
  }
  return res.json() as Promise<T>
}

export type SegmentsResult = { data: SegmentCollection; mock: boolean }

export type SegmentFilter = {
  /** Metric the min score applies to. `overall` is filtered on the client (contract only filters by one dimension). */
  dimension: Metric | null
  minScore: number | null
  ratedOnly: boolean
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
    if (filter.ratedOnly) params.set('rated_only', 'true')
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

/** GET /segments/{id}. Same mock fallback as {@link fetchSegments}. */
export async function fetchSegmentDetail(id: number, signal?: AbortSignal): Promise<SegmentDetail> {
  if (!FORCE_MOCKS) {
    try {
      return await request<SegmentDetail>(`/segments/${id}`, signal)
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

/** Mock stand-in for the server-side filters (rated_only, dimension + min_score) plus the client-side ones. */
function applyMockFilter(data: SegmentCollection, filter: SegmentFilter): SegmentCollection {
  const { dimension, minScore, ratedOnly } = filter
  const features = clientFilter(data, filter).features.filter((f) => {
    if (ratedOnly && f.properties.ratings_count === 0) return false
    if (dimension && dimension !== 'overall' && minScore !== null) {
      const v = f.properties.scores[dimension]
      return v !== null && v >= minScore
    }
    return true
  })
  return { ...data, features }
}

// Forms are UI-only for now: nothing is sent anywhere, the result lives in component state until reload.
// TODO(backend/core): replace the bodies below with
//   POST /segments/{id}/ratings  (body: RatingInput, 201 new / 200 replaced -> Rating)
//   POST /segments/{id}/comments (body: { text }, 201 -> Comment)
// and send the Supabase JWT as `Authorization: Bearer` (see getSession in lib/supabase.ts).

/** Builds the rating the form just collected, locally. */
export async function postRating(segmentId: number, input: RatingInput): Promise<Rating> {
  return mockCreatedRating(segmentId, input)
}

/** Builds the opinion the form just collected, locally. */
export async function postComment(
  segmentId: number,
  text: string,
  author: { id: string; display_name: string },
): Promise<Opinion> {
  return mockCreatedComment(segmentId, text, author)
}
