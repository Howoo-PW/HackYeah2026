import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Layer, Map, NavigationControl, Source } from 'react-map-gl/maplibre'
import type { MapLayerMouseEvent, MapRef, ViewStateChangeEvent } from 'react-map-gl/maplibre'
import type { LayerProps, LineLayerSpecification } from 'react-map-gl/maplibre'
import { setWorkerUrl } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { fetchSegments } from '../api/client'
import type { Bbox, SegmentCollection } from '../api/types'
import { KRAKOW_BBOX, KRAKOW_CENTER, NO_DATA_COLOR, SCORE_COLORS, metricScore } from '../lib/dimensions'
import type { Metric } from '../lib/dimensions'
import type { SegmentFilter } from '../api/client'

// MapLibre 6 needs the worker file URL explicitly under Vite (docs/MAP_STACK.md).
setWorkerUrl(workerUrl)

const MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron'
/** Below this zoom the viewport is too big for the 2000 segments/response limit (contract 5.2). */
const MIN_FETCH_ZOOM = 13

type Props = {
  dimension: Metric
  filter: SegmentFilter
  selectedId: number | null
  onSelect: (id: number | null) => void
  onStatus: (s: { mock: boolean; error: string | null; zoomedOut: boolean; loading: boolean }) => void
}

const lineColor: LineLayerSpecification['paint'] = {
  'line-color': [
    'case',
    ['==', ['get', 'score'], null],
    NO_DATA_COLOR,
    [
      'interpolate',
      ['linear'],
      ['get', 'score'],
      1, SCORE_COLORS[0],
      2, SCORE_COLORS[1],
      3, SCORE_COLORS[2],
      4, SCORE_COLORS[3],
      5, SCORE_COLORS[4],
    ],
  ],
  'line-width': ['interpolate', ['linear'], ['zoom'], 13, 3, 17, 8],
  'line-opacity': ['case', ['==', ['get', 'score'], null], 0.55, 0.95],
}

const segmentsLayer: LayerProps = { id: 'segments', type: 'line', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: lineColor }

/** Map with segments colored by the chosen dimension; reports clicks as segment ids. */
export default function MapView({ dimension, filter, selectedId, onSelect, onStatus }: Props) {
  const mapRef = useRef<MapRef>(null)
  const [bbox, setBbox] = useState<Bbox | null>(null)
  const [zoom, setZoom] = useState(13)
  const [data, setData] = useState<SegmentCollection | null>(null)

  const syncViewport = useCallback(() => {
    const map = mapRef.current
    if (!map) return
    const b = map.getBounds()
    setBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
    setZoom(map.getZoom())
  }, [])

  // Refetch on viewport/filter change; abort the previous request so stale responses never win.
  useEffect(() => {
    if (!bbox) return
    if (zoom < MIN_FETCH_ZOOM) {
      onStatus({ mock: false, error: null, zoomedOut: true, loading: false })
      return
    }
    const ctrl = new AbortController()
    onStatus({ mock: false, error: null, zoomedOut: false, loading: true })
    const timer = setTimeout(() => {
      fetchSegments(bbox, filter, ctrl.signal)
        .then(({ data, mock }) => {
          setData(data)
          onStatus({ mock, error: null, zoomedOut: false, loading: false })
        })
        .catch((err: Error) => {
          if (ctrl.signal.aborted) return
          onStatus({ mock: false, error: err.message, zoomedOut: false, loading: false })
        })
    }, 250)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
    // onStatus is stable enough (setState wrapper in the parent); intentionally not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bbox, zoom, filter])

  // Flatten the chosen dimension into a single `score` property so the paint expression stays simple.
  const colored = useMemo(() => {
    if (!data) return null
    return {
      ...data,
      features: data.features.map((f) => ({
        ...f,
        properties: { ...f.properties, score: metricScore(f.properties.scores, dimension) },
      })),
    }
  }, [data, dimension])

  const onClick = (e: MapLayerMouseEvent) => {
    const id = e.features?.[0]?.properties?.id
    onSelect(typeof id === 'number' ? id : null)
  }

  return (
    <Map
      ref={mapRef}
      initialViewState={{ longitude: KRAKOW_CENTER[0], latitude: KRAKOW_CENTER[1], zoom: 13 }}
      minZoom={11}
      maxBounds={[KRAKOW_BBOX[0] - 0.05, KRAKOW_BBOX[1] - 0.05, KRAKOW_BBOX[2] + 0.05, KRAKOW_BBOX[3] + 0.05]}
      mapStyle={MAP_STYLE}
      interactiveLayerIds={['segments']}
      onLoad={syncViewport}
      onMoveEnd={(_e: ViewStateChangeEvent) => syncViewport()}
      onClick={onClick}
      cursor="auto"
    >
      <NavigationControl position="bottom-right" showCompass={false} />
      {colored && (
        <Source id="segments" type="geojson" data={colored}>
          <Layer {...segmentsLayer} />
          <Layer
            id="segment-selected"
            type="line"
            filter={['==', ['get', 'id'], selectedId ?? -1]}
            layout={{ 'line-cap': 'round' }}
            paint={{ 'line-color': '#111827', 'line-width': ['interpolate', ['linear'], ['zoom'], 13, 6, 17, 13], 'line-opacity': 0.35 }}
          />
        </Source>
      )}
    </Map>
  )
}
