<script setup lang="ts">
import { computed } from 'vue'
import { bounds, centroid, rings, toLocal } from '../geo'
import type { Geometry } from '../types'

const props = defineProps<{ geometry: Geometry; dims: string | null }>()

const W = 300
const H = 360
const PAD = 44

// Rotate so the street-facing side is at the bottom, then fit into the viewBox (screen y grows downwards).
const drawing = computed(() => {
  const g = props.geometry
  const lotRings = rings(g.lot)
  const origin = centroid(lotRings[0])
  let angle = 0
  if (g.front_mid) {
    // Turn the lot edge nearest the front midpoint horizontal, with the lot above it.
    const flat = toLocal(origin)
    const [fx, fy] = flat(g.front_mid)
    const pts = lotRings[0].map(flat)
    let best = { d: Infinity, a: 0 }
    for (let i = 0; i < pts.length - 1; i++) {
      const [[ax, ay], [bx, by]] = [pts[i], pts[i + 1]]
      const d = Math.hypot((ax + bx) / 2 - fx, (ay + by) / 2 - fy)
      if (d < best.d && Math.hypot(bx - ax, by - ay) > 1) best = { d, a: Math.atan2(by - ay, bx - ax) }
    }
    angle = -best.a
    // Edge horizontal now; flip if the front ended up on top.
    const fyRot = fx * Math.sin(angle) + fy * Math.cos(angle)
    if (fyRot > 0) angle += Math.PI
  }
  const project = toLocal(origin, angle)
  const lot = lotRings.map((r) => r.map(project))
  const env = g.envelope ? rings(g.envelope).map((r) => r.map(project)) : []
  const bldg = (g.buildings ?? []).flatMap((b) => rings(b).map((r) => r.map(project)))
  const [minx, miny, maxx, maxy] = bounds(lot)
  // Extra room at the bottom for the FRONT and STREET labels.
  const scale = Math.min((W - 2 * PAD) / (maxx - minx), (H - 2 * PAD - 24) / (maxy - miny))
  const sx = (x: number) => W / 2 + (x - (minx + maxx) / 2) * scale
  const sy = (y: number) => (H - 24) / 2 - (y - (miny + maxy) / 2) * scale
  const path = (rs: [number, number][][]) =>
    rs.map((r) => 'M' + r.map(([x, y]) => `${sx(x).toFixed(1)},${sy(y).toFixed(1)}`).join('L') + 'Z').join(' ')
  return {
    lot: path(lot),
    env: env.length ? path(env) : null,
    bldg: bldg.length ? path(bldg) : null,
    top: sy(maxy),
    bottom: sy(miny),
    left: sx(minx),
    right: sx(maxx),
    oriented: Boolean(g.front_mid),
    // Narrow lots: put the area label beside the lot instead of inside it.
    labelX: sx(maxx) - sx(minx) < 100 ? sx(maxx) + 10 : W / 2,
    labelAnchor: sx(maxx) - sx(minx) < 100 ? 'start' : 'middle',
    midY: (sy(maxy) + sy(miny)) / 2,
  }
})

const yards = computed(() => props.geometry.yards_ft)
const area = computed(() => (props.geometry.envelope_area_sqft != null ? props.geometry.envelope_area_sqft.toLocaleString('en-US') : null))
const ariaLabel = computed(() => {
  const base = `Lot outline${props.dims ? `, about ${props.dims.replace(' x ', ' by ')} feet` : ''}`
  const withEnv = drawing.value.env ? `${base}, with the buildable area inside the front, side and rear yards` : base
  return drawing.value.bldg ? `${withEnv}, and the approximate outline of the existing buildings` : withEnv
})
</script>

<template>
  <svg :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="ariaLabel" class="diagram">
    <path :d="drawing.lot" fill="#ffffff" stroke="var(--ink)" stroke-width="2" stroke-linejoin="round" />
    <path v-if="drawing.env" :d="drawing.env" fill="var(--accent-subtle)" stroke="var(--accent)" stroke-width="2" stroke-dasharray="6 4" />
    <path v-if="drawing.bldg" :d="drawing.bldg" fill="var(--ink-muted)" fill-opacity="0.35" stroke="var(--ink-muted)" stroke-width="1" />
    <g v-if="drawing.oriented" class="lbl">
      <text v-if="yards" :x="W / 2" :y="drawing.top - 8" text-anchor="middle">REAR {{ yards.rear }} FT</text>
      <text v-if="yards" :x="W / 2" :y="drawing.bottom + 16" text-anchor="middle">FRONT {{ yards.front }} FT</text>
      <text
        v-if="yards"
        :x="drawing.left - 10"
        :y="drawing.midY"
        text-anchor="middle"
        :transform="`rotate(-90 ${drawing.left - 10} ${drawing.midY})`"
      >
        SIDE {{ yards.side }} FT
      </text>
      <text :x="W / 2" :y="Math.min(H - 6, drawing.bottom + 34)" text-anchor="middle">STREET</text>
    </g>
    <g v-if="drawing.env">
      <text :x="drawing.labelX" :y="drawing.midY - 4" :text-anchor="drawing.labelAnchor" class="big">Buildable area</text>
      <text v-if="area" :x="drawing.labelX" :y="drawing.midY + 14" :text-anchor="drawing.labelAnchor" class="lbl-t">{{ area }} SQ FT</text>
    </g>
  </svg>
</template>

<style scoped>
.diagram {
  width: 100%;
  height: auto;
  background: var(--canvas);
  border-radius: var(--radius-sm);
}
.lbl text,
.lbl-t {
  font-family: var(--font-mono);
  font-size: 11px;
  fill: var(--ink-muted);
}
.big {
  font-family: var(--font-sans);
  font-size: 13px;
  fill: var(--ink);
}
</style>
