import { mockSegmentDetail, mockSegments } from './mocks'
import type { ApiError, Bbox, Dimension, SegmentCollection, SegmentDetail } from './types'

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

export type SegmentFilter = { dimension: Dimension | null; minScore: number | null; ratedOnly: boolean }

/**
 * GET /segments for the given viewport. Falls back to mock data when the backend is unreachable
 * (network error or 5xx); contract errors such as 422 "zoom in" are rethrown so the UI can show them.
 */
export async function fetchSegments(bbox: Bbox, filter: SegmentFilter, signal?: AbortSignal): Promise<SegmentsResult> {
  if (!FORCE_MOCKS) {
    const params = new URLSearchParams({ bbox: bbox.map((n) => n.toFixed(5)).join(',') })
    if (filter.dimension && filter.minScore !== null) {
      params.set('dimension', filter.dimension)
      params.set('min_score', String(filter.minScore))
    }
    if (filter.ratedOnly) params.set('rated_only', 'true')
    try {
      return { data: await request<SegmentCollection>(`/segments?${params}`, signal), mock: false }
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

function applyMockFilter(data: SegmentCollection, { dimension, minScore, ratedOnly }: SegmentFilter): SegmentCollection {
  const features = data.features.filter((f) => {
    if (ratedOnly && f.properties.ratings_count === 0) return false
    if (dimension && minScore !== null) {
      const v = f.properties.scores[dimension]
      return v !== null && v >= minScore
    }
    return true
  })
  return { ...data, features }
}
