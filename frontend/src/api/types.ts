// Types mirror docs/CONTRACT.md section 4. Change the contract first (separate PR), then this file.
import type { FeatureCollection, Geometry, LineString, MultiLineString } from 'geojson'

export type Dimension = 'surface' | 'views' | 'safety' | 'traffic' | 'parking'
export type TimeOfDay = 'morning' | 'day' | 'evening' | 'night'
export type ObstacleType = 'roadwork' | 'closure' | 'pothole' | 'accident' | 'other'
export type ContentStatus = 'visible' | 'hidden'
export type Confidence = 'low' | 'medium' | 'high'

export type Scores = Record<Dimension, number | null>

export type SegmentProperties = {
  id: number
  osm_way_id: number
  name: string | null
  highway: string
  length_m: number
  scores: Scores
  /** Where `scores` come from: own ratings, estimated from the neighbouring segments of the group, or nothing. */
  scores_source?: 'own' | 'group' | 'none'
  /** The street stretch (about 500 m) this piece belongs to; users see and rate it as one unit (contract 4). */
  group?: GroupRef | null
  ratings_count: number
  active_obstacles_count: number
}

/** A run of consecutive pieces of one street, about 500 m (contract 4, "Grupy"). */
export type GroupRef = {
  id: number
  name: string | null
  highway: string
  length_m: number
  segments_count: number
  /** Most important other street at the start / end of the stretch. */
  from_street: string | null
  to_street: string | null
  /** Ratings of all segments in the group. */
  ratings_count: number
}

/** GET /groups/{id}: merged geometry for highlighting, member segment ids and the group's average scores. */
export type GroupDetail = GroupRef & {
  scores: Scores
  geometry: { type: 'MultiLineString'; coordinates: number[][][] }
  segment_ids: number[]
}

export type Rating = {
  id: string
  segment_id: number
  surface: number | null
  views: number | null
  safety: number | null
  traffic: number | null
  parking: number | null
  time_of_day: TimeOfDay
  created_at: string
}

export type Obstacle = {
  id: string
  segment_id: number | null
  type: ObstacleType
  description: string | null
  location: { lat: number; lon: number }
  valid_until: string | null
  reported_by: string
  created_at: string
}

export type Summary = {
  surface: string
  views: string
  safety: string
  traffic: string
  parking: string
  overall: string
  confidence: Confidence
  conflicts: string[]
  comments_count: number
  model: string
  updated_at: string
}

export type Comment = {
  id: string
  segment_id: number
  author: { id: string; display_name: string }
  text: string
  status: ContentStatus
  created_at: string
}

/**
 * Comment extended with the author's own rating and votes, as shown in the opinions list.
 * NOT IN docs/CONTRACT.md YET: the contract's `Comment` has no rating link and there is no vote endpoint.
 * Needs a contract PR (B1 + FE) before the real backend can return it; until then it comes from mocks.
 */
export type Opinion = Comment & {
  rating?: Rating | null
  author_opinions_count?: number
  likes?: number
  dislikes?: number
  my_vote?: 'up' | 'down' | null
}

/** Body of POST /segments/{id}/ratings (contract 5.3). */
export type RatingInput = Partial<Record<Dimension, number | null>> & { time_of_day?: TimeOfDay }

export type Paginated<T> = { items: T[]; page: number; page_size: number; total: number }

export type SegmentDetail = SegmentProperties & {
  geometry: LineString
  surface_osm: string | null
  smoothness_osm: string | null
  maxspeed: number | null
  lit: boolean | null
  last_rating_at: string | null
  scores_by_time_of_day: Record<TimeOfDay, Scores>
  summary: Summary | null
  /** An AI summary is due and being prepared in the background (NOT IN docs/CONTRACT.md yet). */
  summary_pending?: boolean
  obstacles: Obstacle[]
  photos_count: number
  my_rating: Rating | null
  /** The signed-in user's own comment and photo of this road (NOT IN docs/CONTRACT.md yet); a new opinion replaces them. */
  my_comment?: Opinion | null
  my_photo?: Photo | null
}

export type SegmentCollection = FeatureCollection<LineString, SegmentProperties>

/** One fragment (300-700 m) on a zoomed-out map; `scores` has the same shape as on a segment (contract 5.2, GET /groups). */
export type GroupMapProperties = {
  id: number
  kind: 'group'
  name: string | null
  highway: string
  length_m: number
  segments_count: number
  ratings_count: number
  scores: Scores
  scores_source: 'own' | 'group' | 'none'
}
export type GroupMapCollection = FeatureCollection<MultiLineString, GroupMapProperties>

/** What the map layer draws: segments or fragments, both carry `scores`. */
export type MapCollection = FeatureCollection<Geometry, { scores: Scores; kind?: 'group' }>

/** Map viewport, order as in the contract: minLon,minLat,maxLon,maxLat. */
export type Bbox = [number, number, number, number]

export type ApiError = { error: { code: string; message: string; details?: Record<string, unknown> } }

/** Point as an object (contract section 2): note `lat` first here, unlike GeoJSON `[lon, lat]`. */
export type LatLon = { lat: number; lon: number }

export type RouteProfile = 'driving-car' | 'cycling-regular' | 'foot-walking'

/** How much each dimension matters for the route: 0 = not at all … 3 = very much (contract 5.8). */
export type RouteWeights = Record<Dimension, 0 | 1 | 2 | 3>

/** Body of POST /route (contract 5.8). `via`: up to 5 intermediate stops in travel order. */
export type RouteRequest = { from: LatLon; to: LatLon; via?: LatLon[]; profile: RouteProfile; weights: RouteWeights }

/**
 * A named place: a search result, a street picked on the map or the user's location.
 * `bounds` is [west, south, east, north] when the place is an area/street (used to fit the map), else null.
 */
export type Place = {
  lat: number
  lon: number
  name: string
  detail: string | null
  bounds: [number, number, number, number] | null
  /** Street or other place; only used to pick an icon in search results. */
  kind?: 'street' | 'place'
  /** Set for streets from our own database: the segment to open in the ratings panel. */
  segmentId?: number
}

/** GET /segments/nearest (contract 5.2): the closest segment within 50 m. */
export type NearestSegment = SegmentProperties & { distance_m: number }

/** One item of GET /search (contract 5.10): a street from our own segments. */
export type StreetHit = {
  name: string
  highway: string
  segments_count: number
  length_m: number
  location: LatLon
  /** minLon,minLat,maxLon,maxLat */
  bbox: Bbox
  segment_id: number
}

/** One route from POST /route (contract 5.8). `score` is null when no rated segment lies on the route. */
export type RouteResult = {
  rank: number
  geometry: { type: 'LineString'; coordinates: [number, number][] }
  distance_m: number
  duration_s: number
  score: number | null
  scores: Scores
  /** Share (0-1) of the route length that lies on rated segments. */
  coverage: number
  segment_ids: number[]
}

/** One of the signed-in user's own ratings or comments (GET /me/opinions). NOT IN docs/CONTRACT.md YET: needs a contract PR. */
export type MyOpinion = {
  kind: 'rating' | 'comment'
  id: string
  segment_id: number
  segment_name: string | null
  /** Fragment (group) the road belongs to; the zoomed-out map draws fragments. */
  group_id: number | null
  created_at: string
  time_of_day: TimeOfDay | null
  surface: number | null
  views: number | null
  safety: number | null
  traffic: number | null
  parking: number | null
  text: string | null
  status: ContentStatus | null
}

/** A segment photo (contract 5.7): signed URLs valid for one hour. */
export type Photo = {
  id: string
  segment_id: number
  url: string
  thumbnail_url: string
  taken_at: string | null
  created_at: string
}

/** A named point in an assistant answer. */
export type AssistantPoint = { name: string; lat: number; lon: number }

/** A rated fragment of a street the assistant found by a criterion. */
export type AssistantStreet = {
  name: string
  group_id: number
  highway: string | null
  length_m: number
  location: AssistantPoint
  segment_ids: number[]
  scores: Scores
  ratings_count: number
  score: number | null
}

/**
 * POST /assistant (docs/ASSISTANT.md): a request in words became a route (with the routes, as POST /route returns them),
 * a place, a list of streets, or only a message (`clarify`). `answer` is written from ratings, comments and obstacles.
 */
export type AssistantResponse = {
  intent: 'route' | 'place' | 'streets' | 'clarify'
  interpretation: string
  answer: string
  model: string
  route: { from: AssistantPoint; to: AssistantPoint; via: AssistantPoint[]; profile: RouteProfile; weights: RouteWeights; routes: RouteResult[] } | null
  place: { name: string; lat: number; lon: number; segment_id: number | null } | null
  streets: AssistantStreet[]
}
