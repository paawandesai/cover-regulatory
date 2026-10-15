<script setup lang="ts">
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { nearby } from '../api'
import { bounds, rings } from '../geo'
import type { Geometry } from '../types'

// The worker is a separate module; point MapLibre at the copy Vite serves and bundles.
maplibregl.setWorkerUrl(workerUrl)

const props = defineProps<{ apn: string; geometry: Geometry }>()
const el = ref<HTMLDivElement>()
let map: maplibregl.Map | null = null

const feature = (g: GeoJSON.Geometry | null): GeoJSON.FeatureCollection => ({
  type: 'FeatureCollection',
  features: g ? [{ type: 'Feature', properties: {}, geometry: g }] : [],
})

// No basemap tiles: only parcel outlines from the County data, so nothing is fetched from a tile host.
const style: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#f6f5f2' } }],
}

async function draw() {
  if (!map) return
  const m = map
  const set = (id: string, data: GeoJSON.FeatureCollection) =>
    (m.getSource(id) as maplibregl.GeoJSONSource | undefined)?.setData(data)
  set('lot', feature(props.geometry.lot))
  set('envelope', feature(props.geometry.envelope))
  const [minx, miny, maxx, maxy] = bounds(rings(props.geometry.lot))
  m.fitBounds(
    [
      [minx, miny],
      [maxx, maxy],
    ],
    { padding: 48, duration: 0, maxZoom: 20 },
  )
  try {
    set('nearby', await nearby(props.apn))
  } catch {
    /* context only; the lot still draws */
  }
}

onMounted(() => {
  map = new maplibregl.Map({
    container: el.value!,
    style,
    attributionControl: { compact: true, customAttribution: 'Parcels: LA County Assessor open data' },
    dragRotate: false,
  })
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
  map.on('load', () => {
    const m = map!
    for (const id of ['nearby', 'lot', 'envelope']) m.addSource(id, { type: 'geojson', data: feature(null) })
    m.addLayer({ id: 'nearby-fill', type: 'fill', source: 'nearby', paint: { 'fill-color': '#ffffff' } })
    m.addLayer({ id: 'nearby-line', type: 'line', source: 'nearby', paint: { 'line-color': '#e2dfd8', 'line-width': 1 } })
    m.addLayer({ id: 'lot-fill', type: 'fill', source: 'lot', paint: { 'fill-color': '#ffffff' } })
    m.addLayer({ id: 'lot-line', type: 'line', source: 'lot', paint: { 'line-color': '#1c1b19', 'line-width': 2 } })
    m.addLayer({ id: 'env-fill', type: 'fill', source: 'envelope', paint: { 'fill-color': '#fbe9df' } })
    m.addLayer({
      id: 'env-line',
      type: 'line',
      source: 'envelope',
      paint: { 'line-color': '#c2410c', 'line-width': 2, 'line-dasharray': [3, 2] },
    })
    draw()
  })
})

watch(() => [props.apn, props.geometry], draw)
onBeforeUnmount(() => map?.remove())
</script>

<template>
  <div ref="el" class="map" role="img" aria-label="Map of the lot and neighbouring parcels" />
</template>

<style scoped>
.map {
  width: 100%;
  aspect-ratio: 5 / 6;
  border-radius: var(--radius-sm);
  overflow: hidden;
}
</style>
