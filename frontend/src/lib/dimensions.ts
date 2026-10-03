import type { Dimension, Scores } from '../api/types'

/** Bounding box of Kraków (contract section 2): minLon,minLat,maxLon,maxLat. */
export const KRAKOW_BBOX: [number, number, number, number] = [19.792, 49.967, 20.217, 50.126]
export const KRAKOW_CENTER: [number, number] = [19.94, 50.06]

export const DIMENSIONS: { id: Dimension; label: string; low: string; high: string }[] = [
  { id: 'surface', label: 'Nawierzchnia', low: 'dziury, zniszczona', high: 'gładka, nowa' },
  { id: 'views', label: 'Widoki', low: 'nic ciekawego', high: 'piękne widoki' },
  { id: 'safety', label: 'Bezpieczeństwo', low: 'niebezpiecznie', high: 'bezpiecznie' },
  { id: 'traffic', label: 'Obciążenie', low: 'korki, problemy', high: 'płynnie' },
  { id: 'parking', label: 'Parkingi', low: 'brak miejsc', high: 'łatwo zaparkować' },
]

/** 1 = worst, 5 = best everywhere (contract section 3). */
export const SCORE_COLORS = ['#d7191c', '#fdae61', '#ffdf4d', '#a6d96a', '#1a9641']
export const NO_DATA_COLOR = '#9ca3af'

export function dimensionLabel(id: Dimension): string {
  return DIMENSIONS.find((d) => d.id === id)?.label ?? id
}

/** Color for a score, same stops as the map layer (used by legend and panel). */
export function scoreColor(score: number | null): string {
  if (score === null) return NO_DATA_COLOR
  const i = Math.min(4, Math.max(0, Math.round(score) - 1))
  return SCORE_COLORS[i]
}

/** What the map is colored by and what the min-score filter applies to: one dimension or the overall mean. */
export type Metric = Dimension | 'overall'

export const METRICS: { id: Metric; label: string; low: string; high: string }[] = [
  { id: 'overall', label: 'Ogólna', low: 'słabo', high: 'świetnie' },
  ...DIMENSIONS,
]

/**
 * Overall score: mean of the dimensions that have a score, null when nothing is rated.
 * Computed on the client for display and filtering only; the contract has no such field.
 */
export function overallScore(scores: Scores): number | null {
  const vals = Object.values(scores).filter((v): v is number => v !== null)
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
}

/** Score of a segment for the chosen metric. */
export function metricScore(scores: Scores, metric: Metric): number | null {
  return metric === 'overall' ? overallScore(scores) : scores[metric]
}

/** Same area check the backend does (422 OUT_OF_AREA otherwise). */
export function inKrakow(lat: number, lon: number): boolean {
  const [minLon, minLat, maxLon, maxLat] = KRAKOW_BBOX
  return lon >= minLon && lon <= maxLon && lat >= minLat && lat <= maxLat
}
