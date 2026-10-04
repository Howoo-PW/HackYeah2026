import { useEffect, useMemo, useReducer, useRef } from 'react'
import { ApiRequestError, fetchGroupMap, fetchSegments } from '../api/client'
import type { SegmentFilter } from '../api/client'
import type { Bbox, MapCollection } from '../api/types'
import { KRAKOW_BBOX } from '../lib/dimensions'

/**
 * From this zoom up the map loads segments (limit 2000 per response, contract 5.2). Below it the viewport is too big
 * for that, so it loads fragments (GET /groups): the whole city is about 5 000, so any zoom works.
 */
export const SEGMENT_ZOOM = 15

/** Fixed grid (degrees). A tile holds a few hundred segments, far below the 2000 limit; a dense one is split on demand. */
const TILE_LON = 0.03
const TILE_LAT = 0.02
const MAX_PARALLEL = 4
/** Tiles kept in memory (about a screenful of segments each). Oldest ones not near the view are dropped first. */
const MAX_ENTRIES = 90
const MAX_SPLIT_DEPTH = 3

type MapFeature = MapCollection['features'][number]
type Tile = { id: string; bbox: Bbox }
type Entry = { state: 'loading' | 'done' | 'error'; features: MapFeature[]; mock: boolean; error: string | null }
type Job = { tile: Tile; key: string; zoomedOut: boolean; filter: SegmentFilter }

export type MapDataStatus = { mock: boolean; error: string | null; loading: boolean }

/** Tiles already requested or loaded, keyed by filter + tile. Shared by all maps, so remounting does not refetch. */
const cache = new Map<string, Entry>()

const entryKey = (fKey: string, tile: Tile) => `${fKey}|${tile.id}`

function clamp(b: Bbox): Bbox | null {
  const [w, s, e, n] = [Math.max(b[0], KRAKOW_BBOX[0]), Math.max(b[1], KRAKOW_BBOX[1]), Math.min(b[2], KRAKOW_BBOX[2]), Math.min(b[3], KRAKOW_BBOX[3])]
  return e - w > 1e-4 && n - s > 1e-4 ? [w, s, e, n] : null
}

/** Tiles covering the viewport ("view") and the ring of neighbours around it ("ring", loaded ahead of panning). */
function tilesFor(bbox: Bbox, zoom: number): { view: Tile[]; ring: Tile[]; zoomedOut: boolean } {
  if (zoom < SEGMENT_ZOOM) return { view: [{ id: 'g:city', bbox: KRAKOW_BBOX }], ring: [], zoomedOut: true }
  const x0 = Math.floor(bbox[0] / TILE_LON)
  const x1 = Math.floor(bbox[2] / TILE_LON)
  const y0 = Math.floor(bbox[1] / TILE_LAT)
  const y1 = Math.floor(bbox[3] / TILE_LAT)
  const view: Tile[] = []
  const ring: Tile[] = []
  for (let x = x0 - 1; x <= x1 + 1; x++) {
    for (let y = y0 - 1; y <= y1 + 1; y++) {
      const box = clamp([x * TILE_LON, y * TILE_LAT, (x + 1) * TILE_LON, (y + 1) * TILE_LAT])
      if (!box) continue
      const inside = x >= x0 && x <= x1 && y >= y0 && y <= y1
      ;(inside ? view : ring).push({ id: `s:${x}:${y}`, bbox: box })
    }
  }
  return { view, ring, zoomedOut: false }
}

function dedupe(features: MapFeature[]): MapFeature[] {
  const seen = new Set<unknown>()
  return features.filter((f) => {
    const id = (f.properties as { id?: unknown }).id
    if (id === undefined) return true
    if (seen.has(id)) return false
    seen.add(id)
    return true
  })
}

/** Segments of a box; a box with more than 2000 of them (422) is split in four and the halves merged. */
async function loadSegments(box: Bbox, filter: SegmentFilter, depth = 0): Promise<{ features: MapFeature[]; mock: boolean }> {
  try {
    const { data, mock } = await fetchSegments(box, filter)
    return { features: data.features as MapFeature[], mock }
  } catch (err) {
    if (!(err instanceof ApiRequestError) || err.status !== 422 || err.code !== 'VALIDATION_ERROR' || depth >= MAX_SPLIT_DEPTH) throw err
    const mx = (box[0] + box[2]) / 2
    const my = (box[1] + box[3]) / 2
    const parts = await Promise.all(
      ([[box[0], box[1], mx, my], [mx, box[1], box[2], my], [box[0], my, mx, box[3]], [mx, my, box[2], box[3]]] as Bbox[]).map((b) =>
        loadSegments(b, filter, depth + 1),
      ),
    )
    return { features: dedupe(parts.flatMap((p) => p.features)), mock: parts.some((p) => p.mock) }
  }
}

async function loadJob(job: Job): Promise<{ features: MapFeature[]; mock: boolean }> {
  if (job.zoomedOut) return { features: (await fetchGroupMap(job.tile.bbox, job.filter)).features as MapFeature[], mock: false }
  return loadSegments(job.tile.bbox, job.filter)
}

/**
 * Map data with a tile cache and read-ahead. The view is cut into fixed tiles; those under the viewport load first,
 * then the ring around it. Panning to a tile that is already in memory shows it at once, and the next ring starts
 * loading in the background, so the user rarely waits for an area. `version` drops everything (e.g. after a saved rating).
 */
export function useMapData(bbox: Bbox | null, zoom: number, filter: SegmentFilter, version: number) {
  const [tick, bump] = useReducer((n: number) => n + 1, 0)
  const queue = useRef<Job[]>([])
  const active = useRef(0)
  const wanted = useRef(new Set<string>())

  const fKey = `${filter.dimension}|${filter.minScore}|${filter.noObstacles}|${version}`
  const plan = useMemo(() => (bbox ? tilesFor(bbox, zoom) : null), [bbox, zoom])

  useEffect(() => {
    if (!plan) return
    const tiles = [...plan.view, ...plan.ring]
    wanted.current = new Set(tiles.map((t) => entryKey(fKey, t)))

    const pump = () => {
      while (active.current < MAX_PARALLEL && queue.current.length > 0) {
        const job = queue.current.shift()!
        if (cache.get(job.key)?.state === 'loading') continue
        cache.set(job.key, { state: 'loading', features: [], mock: false, error: null })
        active.current++
        loadJob(job)
          .then((r) => cache.set(job.key, { state: 'done', features: r.features, mock: r.mock, error: null }))
          .catch((err: Error) => cache.set(job.key, { state: 'error', features: [], mock: false, error: err.message }))
          .finally(() => {
            active.current--
            if (cache.size > MAX_ENTRIES) {
              for (const key of cache.keys()) {
                if (cache.size <= MAX_ENTRIES) break
                if (!wanted.current.has(key) && cache.get(key)?.state !== 'loading') cache.delete(key)
              }
            }
            bump()
            pump()
          })
      }
    }

    // viewport tiles first, then the ring; failed tiles are retried, finished and running ones are left alone
    queue.current = tiles
      .map((tile) => ({ tile, key: entryKey(fKey, tile), zoomedOut: plan.zoomedOut, filter }))
      .filter((j) => {
        const e = cache.get(j.key)
        if (e?.state === 'error') cache.delete(j.key)
        return !cache.has(j.key)
      })
    pump()
    // `filter` is covered by fKey (its three fields); `bump` and the refs are stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan, fKey])

  // What the map shows: every loaded tile of the view and its ring, without duplicates from tile borders.
  const loaded = plan ? [...plan.view, ...plan.ring].filter((t) => cache.get(entryKey(fKey, t))?.state === 'done') : []
  const signature = `${fKey}#${loaded.map((t) => t.id).join(',')}`
  const built = useMemo(() => {
    if (loaded.length === 0) return null
    const features = dedupe(loaded.flatMap((t) => cache.get(entryKey(fKey, t))!.features))
    return { type: 'FeatureCollection', features } as MapCollection
    // The signature names exactly the tiles used, so the object stays the same while panning inside loaded tiles.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature])

  // Keep showing the previous data until the new area/filter has something to show (no flash of an empty map).
  const last = useRef<MapCollection | null>(null)
  useEffect(() => {
    if (built) last.current = built
  }, [built])

  const viewEntries = plan ? plan.view.map((t) => cache.get(entryKey(fKey, t))) : []
  const status: MapDataStatus = {
    loading: plan !== null && viewEntries.some((e) => !e || e.state === 'loading'),
    error: viewEntries.find((e) => e?.state === 'error')?.error ?? null,
    mock: loaded.some((t) => cache.get(entryKey(fKey, t))!.mock),
  }
  void tick // re-render when a tile finishes
  return { data: built ?? last.current, status, zoomedOut: plan?.zoomedOut ?? false }
}
