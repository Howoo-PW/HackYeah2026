// Types mirror docs/CONTRACT.md section 4. Change the contract first (separate PR), then this file.
import type { FeatureCollection, LineString } from 'geojson'

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
  ratings_count: number
  active_obstacles_count: number
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

export type SegmentDetail = SegmentProperties & {
  geometry: LineString
  surface_osm: string | null
  smoothness_osm: string | null
  maxspeed: number | null
  lit: boolean | null
  last_rating_at: string | null
  scores_by_time_of_day: Record<TimeOfDay, Scores>
  summary: Summary | null
  obstacles: Obstacle[]
  photos_count: number
  my_rating: Rating | null
}

export type SegmentCollection = FeatureCollection<LineString, SegmentProperties>

/** Map viewport, order as in the contract: minLon,minLat,maxLon,maxLat. */
export type Bbox = [number, number, number, number]

export type ApiError = { error: { code: string; message: string; details?: Record<string, unknown> } }
