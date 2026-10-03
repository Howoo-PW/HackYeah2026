import { fetchStreets } from './client'
import type { Place, StreetHit } from './types'
import { KRAKOW_BBOX, KRAKOW_CENTER, inKrakow } from '../lib/dimensions'

const PHOTON_URL = 'https://photon.komoot.io/api/'
const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
/** Nominatim policy: max 1 request per second (it is only used as a fallback, on Enter). */
const NOMINATIM_MIN_INTERVAL_MS = 1100

export class SearchError extends Error {}

type PhotonFeature = {
  geometry: { coordinates: [number, number] }
  properties: {
    name?: string
    street?: string
    housenumber?: string
    district?: string
    city?: string
    county?: string
    osm_key?: string
    /** [minLon, maxLat, maxLon, minLat] */
    extent?: [number, number, number, number]
  }
}

type NominatimResult = {
  lat: string
  lon: string
  name?: string
  display_name: string
  /** [south, north, west, east] as strings. */
  boundingbox?: [string, string, string, string]
  address?: Record<string, string>
}

const HIGHWAY_PL: Record<string, string> = {
  motorway: 'autostrada',
  trunk: 'droga ekspresowa',
  primary: 'ulica główna',
  secondary: 'ulica główna',
  tertiary: 'ulica',
  unclassified: 'ulica',
  residential: 'ulica osiedlowa',
  living_street: 'strefa zamieszkania',
  cycleway: 'droga rowerowa',
}

const cache = new Map<string, Place[]>()
let lastNominatimCall = 0

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })
}

function fromPhoton(f: PhotonFeature): Place {
  const p = f.properties
  const [lon, lat] = f.geometry.coordinates
  const street = p.street ? `${p.street}${p.housenumber ? ` ${p.housenumber}` : ''}` : null
  const name = p.name ?? street ?? 'Miejsce'
  const detail = [p.name && street ? street : null, p.district, p.city ?? p.county].filter(Boolean).join(', ') || null
  const e = p.extent
  return {
    lat,
    lon,
    name,
    detail,
    bounds: e ? [e[0], e[3], e[2], e[1]] : null,
    kind: p.osm_key === 'highway' ? 'street' : 'place',
  }
}

function fromStreet(h: StreetHit): Place {
  const length = h.length_m < 1000 ? `${Math.round(h.length_m)} m` : `${(h.length_m / 1000).toFixed(1).replace('.', ',')} km`
  return {
    lat: h.location.lat,
    lon: h.location.lon,
    name: h.name,
    detail: `${HIGHWAY_PL[h.highway] ?? 'droga'} · ${length}`,
    bounds: h.bbox,
    kind: 'street',
    segmentId: h.segment_id,
  }
}

/** Streets from our own database; empty when the backend has none or cannot answer. */
async function ownStreets(query: string, limit: number, signal?: AbortSignal): Promise<Place[]> {
  return ((await fetchStreets(query, limit, signal)) ?? []).map(fromStreet)
}

function fromNominatim(r: NominatimResult): Place {
  const a = r.address ?? {}
  const street = a.road ? `${a.road}${a.house_number ? ` ${a.house_number}` : ''}` : null
  const name = r.name || street || r.display_name.split(',')[0]
  const area = a.suburb ?? a.neighbourhood ?? a.city_district
  const city = a.city ?? a.town ?? a.village
  const detail = [r.name && street && street !== name ? street : null, area, city].filter(Boolean).join(', ') || null
  const b = r.boundingbox
  return {
    lat: Number(r.lat),
    lon: Number(r.lon),
    name,
    detail,
    bounds: b ? [Number(b[2]), Number(b[0]), Number(b[3]), Number(b[1])] : null,
    kind: a.road && !r.name ? 'street' : 'place',
  }
}

/** Keeps places inside Kraków's box, drops duplicates (OSM splits one street into many ways), Kraków first. */
function tidy(places: Place[]): Place[] {
  const seen = new Set<string>()
  const unique = places
    .filter((p) => inKrakow(p.lat, p.lon))
    .filter((p) => {
      const key = `${p.name}|${p.detail}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  const inCity = (p: Place) => (p.detail?.endsWith('Kraków') ? 0 : 1)
  return unique.sort((a, b) => inCity(a) - inCity(b))
}

async function photon(query: string, limit: number, signal?: AbortSignal): Promise<Place[]> {
  const [minLon, minLat, maxLon, maxLat] = KRAKOW_BBOX
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
    bbox: `${minLon},${minLat},${maxLon},${maxLat}`,
    lat: String(KRAKOW_CENTER[1]), // bias ranking towards the city centre
    lon: String(KRAKOW_CENTER[0]),
  })
  let res: Response
  try {
    res = await fetch(`${PHOTON_URL}?${params}`, { signal })
  } catch (err) {
    if (signal?.aborted) throw err
    throw new SearchError('Wyszukiwarka jest chwilowo niedostępna.')
  }
  if (!res.ok) throw new SearchError('Wyszukiwarka jest chwilowo niedostępna.')
  const data = (await res.json()) as { features: PhotonFeature[] }
  return tidy(data.features.map(fromPhoton))
}

async function nominatim(query: string, signal?: AbortSignal): Promise<Place[]> {
  const wait = lastNominatimCall + NOMINATIM_MIN_INTERVAL_MS - Date.now()
  if (wait > 0) await sleep(wait, signal)
  lastNominatimCall = Date.now()

  const [minLon, minLat, maxLon, maxLat] = KRAKOW_BBOX
  const params = new URLSearchParams({
    q: query,
    format: 'jsonv2',
    addressdetails: '1',
    limit: '8',
    countrycodes: 'pl',
    'accept-language': 'pl',
    viewbox: `${minLon},${maxLat},${maxLon},${minLat}`,
    bounded: '1',
  })
  let res: Response
  try {
    res = await fetch(`${NOMINATIM_URL}?${params}`, { signal })
  } catch (err) {
    if (signal?.aborted) throw err
    throw new SearchError('Wyszukiwarka jest chwilowo niedostępna.')
  }
  if (!res.ok) throw new SearchError('Wyszukiwarka jest chwilowo niedostępna.')
  return tidy(((await res.json()) as NominatimResult[]).map(fromNominatim))
}

const normalize = (q: string) => q.trim().replace(/\s+/g, ' ')

/**
 * Typeahead suggestions while the user types: streets from our own database first (GET /search), and when
 * there are none (addresses, shops, other places) OpenStreetMap data via Photon, which is built for autocomplete.
 * Cached; the caller debounces and aborts stale requests.
 */
export async function suggestPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  const q = normalize(query)
  const key = `s:${q.toLowerCase()}`
  const hit = cache.get(key)
  if (hit) return hit
  let places = await ownStreets(q, 8, signal)
  if (places.length === 0) places = await photon(q, 8, signal)
  cache.set(key, places)
  return places
}

/** Full search on Enter: our streets, then Photon, then Nominatim when Photon is down. */
export async function searchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  const q = normalize(query)
  const key = `f:${q.toLowerCase()}`
  const hit = cache.get(key)
  if (hit) return hit
  let places = await ownStreets(q, 10, signal)
  if (places.length === 0) {
    try {
      places = await photon(q, 10, signal)
    } catch (err) {
      if (signal?.aborted || !(err instanceof SearchError)) throw err
      places = await nominatim(q, signal)
    }
  }
  cache.set(key, places)
  return places
}
