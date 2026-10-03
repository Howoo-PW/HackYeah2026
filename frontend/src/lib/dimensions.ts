import type { Dimension } from '../api/types'

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
