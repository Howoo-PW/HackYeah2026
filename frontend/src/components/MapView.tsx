import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { GeolocateControl, Layer, Map, Marker, NavigationControl, Source } from 'react-map-gl/maplibre'
import type { ExpressionSpecification, LayerSpecification } from 'maplibre-gl'
import type { MapLayerMouseEvent, MapRef, ViewStateChangeEvent } from 'react-map-gl/maplibre'
import type { LineLayerSpecification } from 'react-map-gl/maplibre'
import { setWorkerUrl } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { OPINIONS_CHANGED } from '../api/client'
import { SEGMENT_ZOOM, useMapData } from '../map/useMapData'
import type { Bbox, LatLon, Place } from '../api/types'
import { KRAKOW_BBOX, KRAKOW_CENTER, NO_DATA_COLOR, SCORE_COLORS, metricScore } from '../lib/dimensions'
import type { Metric } from '../lib/dimensions'
import type { PointKey } from '../routing/useRouteDraft'
import type { SegmentFilter } from '../api/client'

// MapLibre 6 needs the worker file URL explicitly under Vite (docs/MAP_STACK.md).
setWorkerUrl(workerUrl)

const MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron'

export type Basemap = 'map' | 'satellite'

/** Esri World Imagery; verify the terms of use before the demo (docs/MAP_STACK.md). Not to be cached offline. */
const SATELLITE_TILES = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const SATELLITE_ATTRIBUTION = 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'

/** Layers we add ourselves; never touched when restyling the base map. */
const OWN_LAYERS = new Set(['segments', 'segments-casing', 'segment-selected', 'segment-selected-inner', 'segment-primary', 'segment-primary-inner', 'satellite', 'routes-casing', 'routes-line'])

type StyleInfo = {
  /** Bottom-most layer of the base style: the satellite raster goes below it. */
  firstId: string
  /** First label layer: our colored segments go below it so street names stay readable on top. */
  labelId: string | undefined
}

const hasText = (l: LayerSpecification) =>
  l.type === 'symbol' && (l.layout as Record<string, unknown> | undefined)?.['text-field'] !== undefined

/**
 * Restyles the vector base map for the chosen basemap:
 *  - labels get dark text with a white halo (map) or white text with a dark halo (satellite),
 *  - road names use a bold font,
 *  - in satellite mode everything except labels is hidden so the imagery shows through.
 * `original` remembers each layer's own visibility so switching back restores it exactly.
 */
function applyBasemap(mapRef: MapRef, basemap: Basemap, original: Record<string, string>) {
  const map = mapRef.getMap()
  const satellite = basemap === 'satellite'
  for (const layer of map.getStyle().layers) {
    if (OWN_LAYERS.has(layer.id)) continue
    original[layer.id] ??= (layer.layout?.visibility as string | undefined) ?? 'visible'
    const label = hasText(layer)
    const visibility = satellite && !label ? 'none' : (original[layer.id] as 'visible' | 'none')
    map.setLayoutProperty(layer.id, 'visibility', visibility)
    if (label) {
      map.setPaintProperty(layer.id, 'text-color', satellite ? '#ffffff' : '#1f2937')
      map.setPaintProperty(layer.id, 'text-halo-color', satellite ? 'rgba(0,0,0,0.8)' : 'rgba(255,255,255,0.95)')
      map.setPaintProperty(layer.id, 'text-halo-width', 1.6)
      if (layer.id.startsWith('highway-name')) map.setLayoutProperty(layer.id, 'text-font', ['Noto Sans Bold'])
    }
  }
}
/** A planned route to draw; the selected alternative is emphasised and the map fits to it. */
export type DrawnRoute = { coordinates: [number, number][]; selected: boolean }

type Props = {
  routes: DrawnRoute[]
  basemap: Basemap
  dimension: Metric
  filter: SegmentFilter
  /** When set, only these roads (zoomed in) and the fragments containing them (zoomed out) are drawn. */
  only: { segmentIds: Set<number>; groupIds: Set<number> } | null
  /** Segments to highlight: the street stretch of the clicked piece (only the pieces with the clicked street's name, not side streets). */
  selectedIds: number[]
  /** The clicked piece itself: outlined in another color inside the highlighted stretch. */
  primaryId: number | null
  onSelect: (id: number | null) => void
  /** Fly/fit the map to this place whenever the object changes (a new object per search result). */
  focus: { place: Place } | null
  /** Pin for the place found by the search (hidden in route mode, where the A/B pins are shown). */
  placeMarker: Place | null
  /** Numbered pins (e.g. the streets the assistant found); shown outside route mode. */
  pins: { lat: number; lon: number; label: string }[]
  /** Route mode: map clicks set the route points instead of selecting a segment. */
  routeMode: boolean
  routePoints: { a: LatLon | null; b: LatLon | null; stops: (LatLon | null)[] }
  /** True while the user is expected to click the map to place a point. */
  placing: boolean
  onRouteClick: (p: LatLon) => void
  onRouteDrag: (key: PointKey, p: LatLon) => void
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
  'line-width': ['interpolate', ['linear'], ['zoom'], 11, 1.6, 13, 3, 17, 8],
  'line-opacity': ['case', ['==', ['get', 'score'], null], 0.55, 0.95],
}

/** On imagery the rating colors need to be bolder: full opacity (grey for unrated), thicker line. */
const satelliteLineColor: LineLayerSpecification['paint'] = {
  ...lineColor,
  'line-width': ['interpolate', ['linear'], ['zoom'], 11, 2, 13, 4, 17, 10],
  'line-opacity': ['case', ['==', ['get', 'score'], null], 0.85, 1],
}

const segmentsLayout = { 'line-cap': 'round', 'line-join': 'round' } as const

const ROUTE_PINS = [
  { key: 'a', label: 'A', color: '#059669' },
  { key: 'stops', label: '', color: '#d97706' },
  { key: 'b', label: 'B', color: '#e11d48' },
] as const

/** Map with segments colored by the chosen dimension; reports clicks as segment ids. */
export default function MapView({ routes, basemap, dimension, filter, only, selectedIds, primaryId, onSelect, focus, placeMarker, pins, routeMode, routePoints, placing, onRouteClick, onRouteDrag, onStatus }: Props) {
  const mapRef = useRef<MapRef>(null)
  const [bbox, setBbox] = useState<Bbox | null>(null)
  const [zoom, setZoom] = useState(13)
  const [styleInfo, setStyleInfo] = useState<StyleInfo | null>(null)
  const originalVisibility = useRef<Record<string, string>>({})

  const syncViewport = useCallback(() => {
    const map = mapRef.current
    if (!map) return
    const b = map.getBounds()
    setBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
    setZoom(map.getZoom())
  }, [])

  // A saved rating changes the scores: refetch the viewport.
  const [dataVersion, setDataVersion] = useState(0)
  useEffect(() => {
    const bump = () => setDataVersion((v) => v + 1)
    window.addEventListener(OPINIONS_CHANGED, bump)
    return () => window.removeEventListener(OPINIONS_CHANGED, bump)
  }, [])

  // Tiles around the viewport are cached and loaded ahead of panning (see map/useMapData.ts).
  const { data, status } = useMapData(bbox, zoom, filter, dataVersion)
  useEffect(() => {
    onStatus({ mock: status.mock, error: status.error, zoomedOut: false, loading: status.loading })
    // onStatus is stable enough (setState wrapper in the parent); intentionally not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.mock, status.error, status.loading])

  // Once the base style is loaded, learn where our layers go and style it for the current basemap.
  const onLoad = () => {
    syncViewport()
    const layers = mapRef.current?.getStyle().layers
    if (layers?.length) setStyleInfo({ firstId: layers[0].id, labelId: layers.find(hasText)?.id })
  }

  useEffect(() => {
    const map = mapRef.current
    if (map && styleInfo) applyBasemap(map, basemap, originalVisibility.current)
  }, [basemap, styleInfo])

  // Flatten the chosen dimension into a single `score` property so the paint expression stays simple.
  const colored = useMemo(() => {
    if (!data) return null
    const features = only
      ? data.features.filter((f) => {
          const id = (f.properties as { id?: number }).id
          return id !== undefined && (f.properties.kind === 'group' ? only.groupIds : only.segmentIds).has(id)
        })
      : data.features
    return {
      ...data,
      features: features.map((f) => ({
        ...f,
        properties: { ...f.properties, score: metricScore(f.properties.scores, dimension) },
      })),
    }
  }, [data, dimension, only])

  // Move the map to a searched place; leave room for the left panels on desktop.
  useEffect(() => {
    const map = mapRef.current
    if (!focus || !map) return
    const { place } = focus
    const left = window.innerWidth >= 768 ? 470 : 40
    if (place.bounds) {
      const [w, s, e, n] = place.bounds
      map.fitBounds([[w, s], [e, n]], { padding: { top: 90, bottom: 90, left, right: 60 }, maxZoom: 17, duration: 800 })
    } else {
      map.flyTo({ center: [place.lon, place.lat], zoom: 17, duration: 800 })
    }
  }, [focus])

  // Fit the map to the selected route whenever the set of routes or the selection changes.
  useEffect(() => {
    const map = mapRef.current
    const route = routes.find((r) => r.selected)
    if (!map || !route || route.coordinates.length === 0) return
    const lons = route.coordinates.map((c) => c[0])
    const lats = route.coordinates.map((c) => c[1])
    const left = window.innerWidth >= 768 ? 470 : 40
    map.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: { top: 90, bottom: 90, left, right: 60 }, maxZoom: 17, duration: 800 },
    )
  }, [routes])

  const routeFeatures = useMemo(
    () => ({
      type: 'FeatureCollection' as const,
      // selected last so it is drawn on top of the alternatives
      features: [...routes].sort((a, b) => Number(a.selected) - Number(b.selected)).map((r) => ({
        type: 'Feature' as const,
        properties: { selected: r.selected },
        geometry: { type: 'LineString' as const, coordinates: r.coordinates },
      })),
    }),
    [routes],
  )

  // The loaded stretch also contains side streets joined to it (a stretch is a group of connected roads), so the highlight keeps only the
  // pieces with the clicked street's name. Only segments (not the coarse fragments shown when zoomed out) can be selected.
  const primaryName = useMemo(() => {
    const hit = data?.features.find((f) => (f.properties as { id?: number }).id === primaryId)
    return (hit?.properties as { name?: string | null } | undefined)?.name ?? null
  }, [data, primaryId])
  const selectedFilter = useMemo(
    () =>
      [
        'all',
        ['!=', ['get', 'kind'], 'group'],
        ['in', ['get', 'id'], ['literal', selectedIds]],
        ...(primaryName ? [['==', ['get', 'name'], primaryName]] : []),
      ] as unknown as ExpressionSpecification,
    [selectedIds, primaryName],
  )
  const primaryFilter = useMemo(
    () => ['all', ['!=', ['get', 'kind'], 'group'], ['==', ['get', 'id'], primaryId ?? -1]] as ExpressionSpecification,
    [primaryId],
  )


  const onClick = (e: MapLayerMouseEvent) => {
    if (routeMode) {
      onRouteClick({ lat: e.lngLat.lat, lon: e.lngLat.lng })
      return
    }
    const feature = e.features?.[0]
    if (feature?.properties?.kind === 'group') {
      mapRef.current?.flyTo({ center: [e.lngLat.lng, e.lngLat.lat], zoom: SEGMENT_ZOOM + 1, duration: 600 })
      return
    }
    const id = feature?.properties?.id
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
      onLoad={onLoad}
      onMoveEnd={(_e: ViewStateChangeEvent) => syncViewport()}
      onClick={onClick}
      cursor={routeMode && placing ? 'crosshair' : 'auto'}
    >
      <NavigationControl position="bottom-right" showCompass={false} />
      <GeolocateControl position="bottom-right" showAccuracyCircle={false} fitBoundsOptions={{ maxZoom: 16 }} />
      {!routeMode &&
        pins.map((pin) => (
          <Marker key={`${pin.label}-${pin.lat}-${pin.lon}`} longitude={pin.lon} latitude={pin.lat} anchor="bottom">
            <PinIcon label={pin.label} color="#6d28d9" />
          </Marker>
        ))}
      {!routeMode && placeMarker && (
        <Marker longitude={placeMarker.lon} latitude={placeMarker.lat} anchor="bottom">
          <PinIcon label="" color="#111827" />
        </Marker>
      )}
      {routeMode &&
        ROUTE_PINS.flatMap(({ key, label, color }) => {
          const points: { key: PointKey; label: string; color: string; point: LatLon | null }[] =
            key === 'stops'
              ? routePoints.stops.map((point, i) => ({ key: i, label: String(i + 1), color, point }))
              : [{ key, label, color, point: routePoints[key] }]
          return points.map(
            (p) =>
              p.point && (
                <Marker
                  key={String(p.key)}
                  longitude={p.point.lon}
                  latitude={p.point.lat}
                  anchor="bottom"
                  draggable
                  onDragEnd={(e) => onRouteDrag(p.key, { lat: e.lngLat.lat, lon: e.lngLat.lng })}
                >
                  <PinIcon label={p.label} color={p.color} />
                </Marker>
              ),
          )
        })}
      {styleInfo && basemap === 'satellite' && (
        <Source id="satellite" type="raster" tiles={[SATELLITE_TILES]} tileSize={256} maxzoom={19} attribution={SATELLITE_ATTRIBUTION}>
          <Layer id="satellite" type="raster" beforeId={styleInfo.firstId} />
        </Source>
      )}
      {styleInfo && colored && (
        // key: re-adds the layers in declaration order on a basemap change, so the white casing stays under the colors
        <Source key={`segments-${basemap}`} id="segments" type="geojson" data={colored}>
          {basemap === 'satellite' && (
            <Layer
              id="segments-casing"
              type="line"
              beforeId={styleInfo.labelId}
              layout={{ 'line-cap': 'round', 'line-join': 'round' }}
              paint={{ 'line-color': '#ffffff', 'line-opacity': 0.9, 'line-width': ['interpolate', ['linear'], ['zoom'], 13, 7, 17, 14] }}
            />
          )}
          {/* Selected street stretch: opaque blue outline with a thin white gap, drawn under the colored line so ratings stay visible. */}
          <Layer
            id="segment-selected"
            type="line"
            beforeId={styleInfo.labelId}
            filter={selectedFilter}
            layout={segmentsLayout}
            paint={{ 'line-color': '#2563eb', 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 7, 13, 12, 17, 26] }}
          />
          <Layer
            id="segment-selected-inner"
            type="line"
            beforeId={styleInfo.labelId}
            filter={selectedFilter}
            layout={segmentsLayout}
            paint={{ 'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 3.5, 13, 6.5, 17, 14] }}
          />
          {/* The clicked piece: an orange outline over the blue stretch, so it stands out inside it. */}
          <Layer
            id="segment-primary"
            type="line"
            beforeId={styleInfo.labelId}
            filter={primaryFilter}
            layout={segmentsLayout}
            paint={{ 'line-color': '#f59e0b', 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 7, 13, 12, 17, 26] }}
          />
          <Layer
            id="segment-primary-inner"
            type="line"
            beforeId={styleInfo.labelId}
            filter={primaryFilter}
            layout={segmentsLayout}
            paint={{ 'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 3.5, 13, 6.5, 17, 14] }}
          />
          <Layer
            id="segments"
            type="line"
            layout={segmentsLayout}
            paint={basemap === 'satellite' ? satelliteLineColor : lineColor}
            beforeId={styleInfo.labelId}
          />
        </Source>
      )}
      {styleInfo && routes.length > 0 && (
        <Source key={`routes-${basemap}`} id="routes" type="geojson" data={routeFeatures}>
          <Layer
            id="routes-casing"
            type="line"
            beforeId={styleInfo.labelId}
            layout={{ 'line-cap': 'round', 'line-join': 'round' }}
            paint={{ 'line-color': '#ffffff', 'line-width': ['case', ['get', 'selected'], 11, 8], 'line-opacity': 0.95 }}
          />
          <Layer
            id="routes-line"
            type="line"
            beforeId={styleInfo.labelId}
            layout={{ 'line-cap': 'round', 'line-join': 'round' }}
            paint={{ 'line-color': ['case', ['get', 'selected'], '#2563eb', '#94a3b8'], 'line-width': ['case', ['get', 'selected'], 7, 4.5] }}
          />
        </Source>
      )}
    </Map>
  )
}

/** Teardrop pin with a letter, drawn in SVG so it needs no image files. */
function PinIcon({ label, color }: { label: string; color: string }) {
  return (
    <svg width="34" height="44" viewBox="0 0 34 44" className="drop-shadow-md" role="img" aria-label={label ? `Punkt ${label}` : 'Znalezione miejsce'}>
      <path d="M17 1C8.7 1 2 7.6 2 15.8 2 26.5 17 43 17 43s15-16.5 15-27.2C32 7.6 25.3 1 17 1Z" fill={color} stroke="white" strokeWidth="2" />
      {label ? (
        <text x="17" y="21" textAnchor="middle" fontSize="15" fontWeight="700" fill="white" fontFamily="sans-serif">
          {label}
        </text>
      ) : (
        <circle cx="17" cy="16" r="5" fill="white" />
      )}
    </svg>
  )
}
