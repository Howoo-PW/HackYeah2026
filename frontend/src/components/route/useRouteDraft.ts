import { useRef, useState } from 'react'
import { fetchNearestSegment } from '../../api/client'
import type { Dimension, LatLon, Place, RouteProfile, RouteRequest, RouteWeights } from '../../api/types'
import { inKrakow } from '../../lib/dimensions'

/** 'a' = start, 'b' = destination, a number = index of an intermediate stop. */
export type PointKey = 'a' | 'b' | number

export const MAX_STOPS = 3

export type RouteDraft = {
  a: Place | null
  b: Place | null
  /** Intermediate stops in travel order; null = added but not chosen yet. */
  stops: (Place | null)[]
  /** Point the user explicitly asked to re-pick on the map; null = pick the first empty one. */
  picking: PointKey | null
  profile: RouteProfile
  weights: RouteWeights
}

const NO_WEIGHTS: RouteWeights = { surface: 0, views: 0, safety: 0, traffic: 0, parking: 0 }

const INITIAL: RouteDraft = { a: null, b: null, stops: [], picking: null, profile: 'driving-car', weights: NO_WEIGHTS }

const OUT_OF_AREA = 'Ten punkt jest poza Krakowem. Wybierz miejsce w obrębie miasta.'

export function getPoint(d: RouteDraft, key: PointKey): Place | null {
  if (key === 'a') return d.a
  if (key === 'b') return d.b
  return d.stops[key] ?? null
}

function withPoint(d: RouteDraft, key: PointKey, point: Place | null): RouteDraft {
  if (key === 'a') return { ...d, a: point }
  if (key === 'b') return { ...d, b: point }
  const stops = d.stops.slice()
  stops[key] = point
  return { ...d, stops }
}

/** Which point the next map click will set: the explicit one, else the first empty one in travel order. */
export function activePoint(d: RouteDraft): PointKey | null {
  if (d.picking !== null) return d.picking
  if (!d.a) return 'a'
  const emptyStop = d.stops.findIndex((s) => !s)
  if (emptyStop >= 0) return emptyStop
  if (!d.b) return 'b'
  return null
}

/** The POST /route body for the current choices (stops that are still empty are left out), or null until both ends are set. */
export function buildRouteRequest(d: RouteDraft): RouteRequest | null {
  if (!d.a || !d.b) return null
  const via = d.stops.filter((s): s is Place => s !== null).map((s) => ({ lat: s.lat, lon: s.lon }))
  return {
    from: { lat: d.a.lat, lon: d.a.lon },
    to: { lat: d.b.lat, lon: d.b.lon },
    ...(via.length > 0 ? { via } : {}),
    profile: d.profile,
    weights: { ...d.weights, parking: 0 }, // routes are not planned around parking
  }
}

/** Street name for a point picked on the map, from the closest segment (backend `/segments/nearest`). */
async function nameForPoint(point: LatLon): Promise<Pick<Place, 'name' | 'detail'>> {
  const seg = await fetchNearestSegment(point.lat, point.lon)
  if (!seg) return { name: 'Punkt na mapie', detail: 'poza siecią dróg w bazie' }
  return { name: seg.name ?? 'Droga bez nazwy', detail: null }
}

/**
 * State of the route the user is choosing (points A/B, stops, profile, requirements).
 * Pure UI state: nothing is sent to the backend and nothing is computed from it.
 */
export function useRouteDraft() {
  const [draft, setDraft] = useState<RouteDraft>(INITIAL)
  const [error, setError] = useState<string | null>(null)
  // Guards against a slow name lookup overwriting a newer choice of the same point.
  const lookup = useRef<Record<string, number>>({})
  const bump = (key: PointKey) => (lookup.current[String(key)] = (lookup.current[String(key)] ?? 0) + 1)
  const bumpAll = () => Object.keys(lookup.current).forEach((k) => lookup.current[k]++)

  /** Sets a point from a place that already has a name; rejects places outside Kraków. */
  const place = (key: PointKey, p: Place) => {
    if (!inKrakow(p.lat, p.lon)) {
      setError(OUT_OF_AREA)
      return false
    }
    bump(key)
    setError(null)
    setDraft((d) => ({ ...withPoint(d, key, p), picking: null }))
    return true
  }

  /** Sets a point picked by clicking/dragging on the map, then fills in the street name. */
  const placeFromMap = (key: PointKey, ll: LatLon) => {
    const pending: Place = { ...ll, name: 'Szukam nazwy ulicy…', detail: null, bounds: null }
    if (!place(key, pending)) return
    const ticket = lookup.current[String(key)]
    nameForPoint(ll).then((label) => {
      if (lookup.current[String(key)] !== ticket) return
      setDraft((d) => {
        const current = getPoint(d, key)
        return current ? withPoint(d, key, { ...current, ...label }) : d
      })
    })
  }

  return {
    draft,
    error,
    place,
    placeFromMap,
    /** Map click: sets whichever point is active (see {@link activePoint}). */
    clickMap: (ll: LatLon) => {
      const key = activePoint(draft)
      if (key !== null) placeFromMap(key, ll)
    },
    /** Replaces the whole draft (e.g. with what the assistant understood); returns it so a result can be matched to it. */
    load: (next: Pick<RouteDraft, 'a' | 'b' | 'stops' | 'profile' | 'weights'>): RouteDraft => {
      lookup.current = {}
      setError(null)
      const draft: RouteDraft = { ...next, picking: null }
      setDraft(draft)
      return draft
    },
    /** Starts a fresh route, optionally with the destination already chosen (e.g. from a search result). */
    start: (destination?: Place) => {
      lookup.current = {}
      setError(null)
      setDraft({ ...INITIAL, b: destination ?? null })
    },
    startPicking: (key: PointKey) => {
      setError(null)
      setDraft((d) => ({ ...d, picking: key }))
    },
    /** Empties a point but keeps its row. */
    clearPoint: (key: PointKey) => {
      bump(key)
      setDraft((d) => ({ ...withPoint(d, key, null), picking: null }))
    },
    addStop: () => setDraft((d) => (d.stops.length >= MAX_STOPS ? d : { ...d, stops: [...d.stops, null], picking: null })),
    removeStop: (index: number) => {
      bumpAll() // indices shift, so pending name lookups for stops are void
      setDraft((d) => ({ ...d, stops: d.stops.filter((_, i) => i !== index), picking: null }))
    },
    /** Swaps start and destination and reverses the stops, so the same route is driven backwards. */
    swap: () => {
      bumpAll()
      setDraft((d) => ({ ...d, a: d.b, b: d.a, stops: d.stops.slice().reverse(), picking: null }))
    },
    setProfile: (profile: RouteProfile) => setDraft((d) => ({ ...d, profile })),
    setWeight: (dim: Dimension, value: 0 | 1 | 2 | 3) =>
      setDraft((d) => ({ ...d, weights: { ...d.weights, [dim]: value } })),
    reset: () => {
      lookup.current = {}
      setError(null)
      setDraft(INITIAL)
    },
    setError,
  }
}

export type RouteDraftApi = ReturnType<typeof useRouteDraft>
