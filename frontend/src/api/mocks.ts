// Mock data shaped like the examples in docs/CONTRACT.md. Used when the backend is unreachable.
import type { Bbox, Opinion, Paginated, Rating, Scores, Summary, SegmentCollection, SegmentDetail, SegmentProperties } from './types'

// A few streets around the Old Town as [lon, lat] polylines, split into short segments below.
const STREETS: { name: string; highway: string; coords: [number, number][] }[] = [
  { name: 'ulica Grodzka', highway: 'residential', coords: [[19.9370, 50.0614], [19.9385, 50.0580], [19.9395, 50.0550]] },
  { name: 'ulica Floriańska', highway: 'pedestrian', coords: [[19.9400, 50.0645], [19.9372, 50.0617]] },
  { name: 'Aleja Mickiewicza', highway: 'primary', coords: [[19.9150, 50.0640], [19.9250, 50.0650], [19.9350, 50.0660]] },
  { name: 'ulica Dietla', highway: 'secondary', coords: [[19.9450, 50.0570], [19.9500, 50.0520], [19.9560, 50.0490]] },
  { name: 'Bulwar Wiślany', highway: 'cycleway', coords: [[19.9300, 50.0500], [19.9380, 50.0480], [19.9470, 50.0465], [19.9560, 50.0450]] },
  { name: 'ulica Kałuży', highway: 'tertiary', coords: [[19.9700, 50.0800], [19.9800, 50.0850], [19.9900, 50.0900]] },
]

/** Deterministic pseudo-random score in 1.0–5.0 (or null for unrated), so the map is stable across reloads. */
function pseudo(id: number, salt: number): number | null {
  const x = Math.sin(id * 12.9898 + salt * 78.233) * 43758.5453
  const r = x - Math.floor(x)
  if (r < 0.12) return null
  return Math.round((1 + r * 4) * 10) / 10
}

function buildSegments(): SegmentCollection['features'] {
  const features: SegmentCollection['features'] = []
  let id = 1000
  STREETS.forEach((street, s) => {
    for (let i = 0; i < street.coords.length - 1; i++) {
      id += 1
      const scores: Scores = {
        surface: pseudo(id, 1),
        views: pseudo(id, 2),
        safety: pseudo(id, 3),
        traffic: pseudo(id, 4),
        parking: pseudo(id, 5),
      }
      const rated = Object.values(scores).some((v) => v !== null)
      const props: SegmentProperties = {
        id,
        osm_way_id: 23456000 + s,
        name: street.name,
        highway: street.highway,
        length_m: 140 + (id % 7) * 20,
        scores,
        ratings_count: rated ? 3 + (id % 25) : 0,
        active_obstacles_count: id % 11 === 0 ? 1 : 0,
      }
      features.push({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: [street.coords[i], street.coords[i + 1]] },
        properties: props,
      })
    }
  })
  return features
}

const ALL = buildSegments()

export function mockSegments(bbox: Bbox): SegmentCollection {
  const [minLon, minLat, maxLon, maxLat] = bbox
  const features = ALL.filter((f) =>
    f.geometry.coordinates.some(([lon, lat]) => lon >= minLon && lon <= maxLon && lat >= minLat && lat <= maxLat),
  )
  return { type: 'FeatureCollection', features }
}

// Placeholder until the AI service is wired in (branch backend/ai-integration).
const MOCK_SUMMARY: Summary = {
  surface: 'Nawierzchnia w większości nowa, ale przy skrzyżowaniach pojawiają się dziury.',
  views: 'Użytkownicy chwalą widoki na Wawel i Wisłę.',
  safety: 'Wieczorem brakuje oświetlenia, część osób czuje się niepewnie.',
  traffic: 'Rano spokojnie, po południu korki.',
  parking: 'Trudno zaparkować, zwłaszcza w weekendy.',
  overall: 'Ładna trasa z dobrą nawierzchnią, ale wieczorem zatłoczona i słabo oświetlona.',
  confidence: 'medium',
  conflicts: ['Jedni opisują nawierzchnię jako gładką, inni zgłaszają dziury przy skrzyżowaniu.'],
  comments_count: 5,
  model: 'mock',
  updated_at: '2026-09-30T12:00:00Z',
}

export function mockSegmentDetail(id: number): SegmentDetail | null {
  const f = ALL.find((s) => s.properties.id === id)
  if (!f) return null
  const p = f.properties
  const empty: Scores = { surface: null, views: null, safety: null, traffic: null, parking: null }
  return {
    ...p,
    geometry: f.geometry,
    surface_osm: 'asphalt',
    smoothness_osm: null,
    maxspeed: 30,
    lit: true,
    last_rating_at: p.ratings_count > 0 ? '2026-09-28T17:10:00Z' : null,
    scores_by_time_of_day: { morning: p.scores, day: p.scores, evening: empty, night: empty },
    summary: p.ratings_count >= 5 ? MOCK_SUMMARY : null,
    obstacles: [],
    photos_count: 0,
    my_rating: null,
  }
}

const MOCK_TEXTS = [
  'Nowy asfalt od mostu, ale wieczorem korki.',
  'Piękny widok na Wawel, ale dziury przy skrzyżowaniu.',
  'Rano spokojnie, polecam na rower.',
  'Brakuje oświetlenia po zmroku, czuć się niepewnie.',
  'Trudno zaparkować, szczególnie w weekendy.',
]

/** Deterministic mock opinions (3–5 per rated segment) with the author's own rating and votes. */
export function mockComments(segmentId: number, page: number, pageSize: number): Paginated<Opinion> {
  const seg = ALL.find((s) => s.properties.id === segmentId)
  const total = seg && seg.properties.ratings_count > 0 ? 3 + (segmentId % 3) : 0
  const times = ['morning', 'day', 'evening', 'night'] as const
  const all: Opinion[] = Array.from({ length: total }, (_, i) => {
    const seed = segmentId * 10 + i
    const score = (salt: number) => {
      const v = pseudo(seed, salt)
      return v === null ? null : Math.round(v)
    }
    const created_at = new Date(Date.UTC(2026, 8, 28 - i * 3, 17, 10)).toISOString()
    const rating: Rating = {
      id: `mock-rating-${seed}`,
      segment_id: segmentId,
      surface: score(1) ?? 3,
      views: score(2),
      safety: score(3),
      traffic: score(4),
      parking: score(5),
      time_of_day: times[seed % 4],
      created_at,
    }
    return {
      id: `mock-${segmentId}-${i}`,
      segment_id: segmentId,
      author: { id: `mock-user-${i}`, display_name: ['Ania', 'Marek', 'Kasia', 'Tomek', 'Ola'][(segmentId + i) % 5] },
      text: MOCK_TEXTS[(segmentId + i) % MOCK_TEXTS.length],
      status: 'visible',
      created_at,
      rating,
      author_opinions_count: 1 + (seed % 12),
      likes: seed % 9,
      dislikes: seed % 3,
      my_vote: null,
    }
  })
  const start = (page - 1) * pageSize
  return { items: all.slice(start, start + pageSize), page, page_size: pageSize, total }
}
