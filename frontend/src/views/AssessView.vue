<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, assess } from '../api'
import AppHeader from '../components/AppHeader.vue'
import LabelBadge from '../components/LabelBadge.vue'
import LotDiagram from '../components/LotDiagram.vue'
import ProjectForm from '../components/ProjectForm.vue'
import ChatPanel from '../components/ChatPanel.vue'
import ReportRequest from '../components/ReportRequest.vue'
import ScenarioPanel from '../components/ScenarioPanel.vue'
import SummaryCard from '../components/SummaryCard.vue'
import SourcePanel from '../components/SourcePanel.vue'
import StopState from '../components/StopState.vue'
import { citeLabel, formatApn, formatDate, formatExisting, formatValue } from '../format'
import type { Assessment, Item, Label, ProjectInputs } from '../types'

// MapLibre is large; load it only when the map view is opened.
const LotMap = defineAsyncComponent(() => import('../components/LotMap.vue'))

const route = useRoute()
const router = useRouter()
const input = ref(typeof route.query.q === 'string' ? route.query.q : '')
const result = ref<Assessment | null>(null)
const error = ref<{ status: number; message: string } | null>(null)
const loading = ref(false)
const pickedId = ref<string | null>(null)
const view = ref<'diagram' | 'map'>('diagram')
const panel = ref<{ $el: HTMLElement } | null>(null)

// Keyboard users land on the source panel's heading when they open a value, and Escape takes them back.
let viaKeys = false
let returnTo: HTMLElement | null = null
const onKey = () => (viaKeys = true)
const onPointer = () => (viaKeys = false)
onMounted(() => (window.addEventListener('keydown', onKey, true), window.addEventListener('pointerdown', onPointer, true)))
onBeforeUnmount(() => (window.removeEventListener('keydown', onKey, true), window.removeEventListener('pointerdown', onPointer, true)))

// On narrow screens the source panel sits below the list; bring it into view when a row is picked.
async function pick(id: string) {
  pickedId.value = id
  const keys = viaKeys
  returnTo = keys ? (document.activeElement as HTMLElement | null) : null
  await nextTick()
  if (keys) panel.value?.$el.querySelector<HTMLElement>('h2')?.focus()
  if (window.matchMedia('(max-width: 1100px)').matches) panel.value?.$el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function backToList() {
  returnTo?.focus()
  returnTo = null
}

const PROJECT_KEYS = [
  'height_ft',
  'floor_area_sqft',
  'second_unit',
  'second_unit_sqft',
  'second_unit_bedrooms',
  'covered_parking_sqft',
  'parking_in_rear',
  'accessory_sqft',
  'tall_ceiling_sqft',
  'side_wall_ft',
] as const

// Project inputs live in the URL so a checked scenario can be shared or reloaded.
const project = computed<Partial<ProjectInputs>>(() => {
  const out: Record<string, string | number | boolean> = {}
  for (const k of PROJECT_KEYS) {
    const v = route.query[k]
    if (typeof v === 'string' && v) out[k] = k === 'second_unit' ? v : k === 'parking_in_rear' ? v === 'true' : Number(v)
  }
  return out as Partial<ProjectInputs>
})

function applyProject(p: Partial<ProjectInputs>) {
  const query: Record<string, string> = { q: String(route.query.q ?? '') }
  for (const [k, v] of Object.entries(p)) if (v !== undefined) query[k] = String(v)
  router.push({ query })
}

async function load(q: string) {
  loading.value = true
  error.value = null
  const keepPick = result.value?.parcel && pickedId.value
  try {
    const r = await assess(q, project.value)
    result.value = r
    document.title = `APN ${formatApn(r.parcel.apn)} · Regulatory Engine`
    const first = r.items.find((i) => i.citations.length && i.family !== 'parcel') ?? r.items[0]
    if (!keepPick || ![...r.items, ...r.parcel.items].some((i) => i.id === keepPick)) pickedId.value = first?.id ?? null
  } catch (e) {
    result.value = null
    error.value = e instanceof ApiError ? { status: e.status, message: e.message } : { status: 0, message: String(e) }
  } finally {
    loading.value = false
  }
}

watch(
  () => JSON.stringify(route.query),
  () => {
    const q = route.query.q
    if (typeof q === 'string' && q.trim().length >= 3) {
      input.value = q
      load(q)
    } else {
      result.value = null
    }
  },
  { immediate: true },
)

function submit() {
  const q = input.value.trim()
  if (q.length < 3) return
  if (q === route.query.q) load(q)
  else router.push({ query: { q } })
}

const parcelItem = (id: string) => result.value?.parcel.items.find((i) => i.id === id)
const item = (id: string) => result.value?.items.find((i) => i.id === id)
const zone = computed(() => parcelItem('zone')?.value as string | null | undefined)
const dims = computed(() => item('lot_dimensions'))

const facts = computed(() => {
  const r = result.value
  if (!r) return []
  const rows: { k: string; v: string; item: Item; text?: string; badge?: Label }[] = []
  const add = (it: Item | undefined, k: string, v?: string, text?: string, badge?: Label) =>
    it && rows.push({ k, v: v ?? formatValue(it), item: it, text, badge })
  add(parcelItem('lot_area'), 'Lot area')
  add(dims.value, 'Lot width x depth', undefined, 'Approximate (parcel shape)')
  add(parcelItem('community_plan_area'), 'Community plan area')
  const regime = parcelItem('code_regime')
  add(regime, 'Zoning code in effect', regime?.value === 'I' ? 'Chapter I' : regime?.value === '1A' ? 'Chapter 1A' : undefined)
  const existing = parcelItem('existing')
  add(existing, 'Existing building (Assessor)', formatExisting(existing?.value))
  // Machine-learned outlines carry their own label, so they don't read as verified records.
  add(item('existing_footprint'), 'Existing buildings (outline)')
  return rows
})

const isHillside = computed(() => Boolean(item('hillside')?.value))
const groups = computed(() => {
  const r = result.value
  if (!r) return []
  const of = (fams: string[]) => r.items.filter((i) => fams.includes(i.family))
  // One envelope family per lot: R1 (12.08), R2 (12.09), RE (12.07.01) or County R-1 (Title 22).
  const envs = ['r1_envelope', 'r2_envelope', 're_envelope', 'county_r1_envelope'] as const
  const env = envs.find((f) => r.items.some((i) => i.family === f)) ?? 'r1_envelope'
  const zoneName = { r1_envelope: 'R1', r2_envelope: 'R2', re_envelope: 'RE', county_r1_envelope: 'County R-1' }[env]
  return [
    {
      title: `${zoneName} envelope`,
      sub: r.items.some((i) => i.family === env && i.label === 'withheld')
        ? 'Some values withheld for this lot'
        : env === 'county_r1_envelope'
          ? 'Title 22, from a copy whose edition is not stated'
          : isHillside.value
          ? 'Hillside Area standards (LAMC 12.21 C.10)'
          : item('coastal')?.value
            ? 'Coastal Zone (LAMC 12.21.1)'
            : `Flat-land ${zoneName}`,
      rows: of([env]),
    },
    {
      title: 'What can be built',
      sub: 'Single-family home within the envelope above, plus',
      rows: of(['guest_house', 'adu', 'jadu']),
    },
    { title: 'SB 9', sub: 'Two homes, or a lot split, under state law', rows: of(['sb9']) },
    { title: 'Specific plan', sub: 'Plans whose text is loaded', rows: of(['plan']) },
    { title: 'Fire rebuild', sub: "Mayor's emergency orders after the January 2025 fires", rows: of(['rebuild']) },
    { title: 'Flags', sub: 'Shown, not evaluated', rows: of(['flag']) },
  ].filter((g) => g.rows.length)
})

const fire = computed(() => item('fire_rebuild'))
const picked = computed(() => {
  const r = result.value
  if (!r || !pickedId.value) return null
  return [...r.items, ...r.parcel.items].find((i) => i.id === pickedId.value) ?? null
})

const parcelFetched = computed(() => formatDate(parcelItem('lot_area')?.source?.fetched_at))
// Hover text on the map: the value each shape stands for.
const mapLabels = computed<Record<string, string>>(() => {
  const out: Record<string, string> = {}
  for (const it of result.value?.items ?? []) out[it.id] = `${it.title}: ${formatValue(it)}`
  if (out.max_rfa) out.max_rfa = `Buildable area (illustrative). ${out.max_rfa}`
  return out
})
const zoningFetched = computed(() => formatDate(parcelItem('zone')?.source?.fetched_at))

const notFoundBody = computed(() => {
  const q = String(route.query.q ?? '').replace(/[\s-]/g, '')
  const where = 'Only five study areas are loaded (Reseda, Boyle Heights, Pacific Palisades, a Westside strip by Beverly Hills, and Del Aire in unincorporated LA County).'
  return /^\d+$/.test(q)
    ? q.length === 10
      ? `No parcel with that APN is loaded. ${where}`
      : `An APN has 10 digits; that has ${q.length}. ${where}`
    : `That address isn't in the loaded parcel data. ${where} Inside them, an address or the 10-digit APN works.`
})

const stop = computed(() => {
  const r = result.value
  if (!r || r.status === 'ok') return null
  const note = r.notes[r.notes.length - 1] ?? ''
  switch (r.status) {
    case 'outside_city':
      return {
        title: 'Outside the City of Los Angeles',
        body: note,
        detail: 'Checked against the City boundary before any zoning lookup.',
      }
    case 'regime_not_modeled':
      return {
        title: 'New Zoning Code applies (Chapter 1A)',
        body: note,
        detail: 'Code regime from the Community Plan Area, checked before the zone is read.',
      }
    default:
      return {
        title: `Zone ${zone.value ?? 'unknown'} is not modeled`,
        body: note || 'Only the R1, R2 and RE zones are modeled.',
        detail: 'No rules are shown rather than rules from the wrong zone.',
      }
  }
})
</script>

<template>
  <div>
    <AppHeader title="Regulatory Engine" subtitle="City of Los Angeles · Chapter I · R1, R2, RE">
      <form class="search" role="search" @submit.prevent="submit">
        <label for="q" class="sr-only">APN or street address</label>
        <input
          id="q"
          v-model="input"
          class="field mono"
          placeholder="APN (2121-005-008) or street address"
          autocomplete="off"
          spellcheck="false"
          maxlength="200"
        />
        <button type="submit" class="btn btn-primary" :disabled="loading">
          {{ loading ? 'Assessing…' : 'Assess' }}
        </button>
      </form>
      <RouterLink to="/review" class="small">Rule review</RouterLink>
    </AppHeader>

    <aside class="disclaimer" aria-label="Disclaimer">
      <p class="small">
        Decision support for licensed professionals, not a zoning determination. Confirm every result with LA City Planning and LADBS.
      </p>
    </aside>

    <main class="page">
      <StopState
        v-if="error?.status === 404"
        eyebrow="Search"
        title="Parcel not found"
        :body="notFoundBody"
        detail="Lookup order: APN, County address points, County parcel situs, then the US Census geocoder."
      />
      <StopState
        v-else-if="error"
        eyebrow="Error"
        title="The assessment didn't load"
        :body="error.status === 422 ? 'Enter at least three characters.' : 'The server returned an error. Try again.'"
      />

      <template v-else-if="result && stop">
        <StopState :eyebrow="`APN ${formatApn(result.parcel.apn)}`" :title="stop.title" :body="stop.body" :detail="stop.detail" />
        <section v-if="result.items.length" class="card stop-items" aria-label="What the loaded text says">
          <h2>What the loaded Chapter 1A text says</h2>
          <div v-for="i in result.items" :key="i.id" class="stop-item">
            <div class="stop-head">
              <strong>{{ i.title }}</strong>
              <span class="mono">{{ formatValue(i) }}</span>
              <LabelBadge :label="i.label" :text="i.label_text" />
            </div>
            <p class="small">{{ i.explanation }}</p>
            <p v-if="i.citations.length" class="small muted">
              Sources:
              <template v-for="(c, n) in i.citations" :key="n">
                <a v-if="c.source_url" :href="c.source_url" target="_blank" rel="noopener">{{ c.section_id }}</a><span v-else>{{ c.section_id }}</span>{{ n < i.citations.length - 1 ? ', ' : '' }}
              </template>
            </p>
          </div>
        </section>
        <p v-for="d in result.disclaimers" :key="d" class="small muted stop-note">{{ d }}</p>
      </template>

      <template v-else-if="result">
        <div v-if="fire" class="card alert fire" role="note">
          <strong>{{ fire.title }}</strong>
          <p class="small">{{ fire.explanation }}</p>
        </div>
        <div class="cols">
          <section aria-label="Parcel" class="left">
            <div class="card parcel">
              <div class="apn">
                <span class="eyebrow">APN</span>
                <span class="mono small">{{ formatApn(result.parcel.apn) }}</span>
              </div>
              <h1>{{ zone ? `${zone} lot` : 'Parcel' }}</h1>
              <button
                v-for="f in facts"
                :key="f.k"
                type="button"
                class="fact"
                :class="{ on: pickedId === f.item.id }"
                @click="pick(f.item.id)"
              >
                <span class="fk">
                  <span class="small muted">{{ f.k }}</span>
                  <span class="strong">{{ f.v }}</span>
                </span>
                <LabelBadge :label="f.badge ?? f.item.label" :text="f.text" />
              </button>
            </div>

            <figure v-if="result.geometry" class="card fig">
              <div class="toggle" role="group" aria-label="Lot view">
                <button type="button" :aria-pressed="view === 'diagram'" :class="{ on: view === 'diagram' }" @click="view = 'diagram'">
                  Diagram
                </button>
                <button type="button" :aria-pressed="view === 'map'" :class="{ on: view === 'map' }" @click="view = 'map'">Map</button>
              </div>
              <LotDiagram v-if="view === 'diagram'" :geometry="result.geometry" :dims="(dims?.value as string) ?? null" @pick="pick" />
              <LotMap v-else :apn="result.parcel.apn" :geometry="result.geometry" :labels="mapLabels" @pick="pick" />
              <figcaption class="small muted">
                Illustrative, not survey-grade. Front taken as the street-facing side. Click a yard, the buildable area or a building to see
                its source.
                <template v-if="result.geometry.note">
                  {{ result.geometry.note[0].toUpperCase() + result.geometry.note.slice(1) }}.</template
                >
                <template v-if="view === 'map'"> Neighbouring parcel outlines from LA County Assessor data; no basemap.</template>
                <template v-if="result.geometry.buildings?.length">
                  Grey shapes are existing buildings, traced from imagery by machine learning (Microsoft, ODbL); approximate.</template
                >
              </figcaption>
            </figure>

            <p class="small muted">
              Parcel data: LA County Assessor open parcels, fetched
              {{ parcelFetched }}. Zoning: City of LA zoning layer, fetched {{ zoningFetched }}. Informational only; not suitable for legal,
              engineering or surveying use.
            </p>
          </section>

          <section aria-label="Assessment" class="mid">
            <SummaryCard v-if="result.summary" :summary="result.summary" />
            <ProjectForm :inputs="project" :checks="result.project?.checks ?? []" @apply="applyProject" @pick="pick" />
            <ScenarioPanel :apn="result.parcel.apn" :inputs="project" @load="applyProject" />
            <div v-for="n in result.notes" :key="n" class="card note small">
              {{ n }}
            </div>

            <div v-for="g in groups" :key="g.title" class="card">
              <div class="ghead">
                <h2>{{ g.title }}</h2>
                <span class="small muted">{{ g.sub }}</span>
              </div>
              <button
                v-for="r in g.rows"
                :key="r.id"
                type="button"
                class="row"
                :class="{ on: pickedId === r.id }"
                :aria-pressed="pickedId === r.id"
                @click="pick(r.id)"
              >
                <span class="rt">{{ r.title }}</span>
                <span class="rv">{{ formatValue(r) }}</span>
                <span class="rc mono small muted">{{ citeLabel(r) }}</span>
                <LabelBadge :label="r.label" />
              </button>
            </div>
            <p class="small muted">{{ result.ai_disclosure }}</p>
            <ChatPanel :apn="result.parcel.apn" :items="result.items" />
            <ReportRequest :apn="result.parcel.apn" :inputs="project" />
          </section>

          <SourcePanel v-if="picked" ref="panel" class="right" :item="picked" :apn="result.parcel.apn" @keydown.esc="backToList" />
        </div>
      </template>

      <section v-else-if="!loading" class="card intro">
        <h1>Check what can be built on a City of LA residential lot</h1>
        <p>
          Enter a 10-digit APN or a street address. You get the zone envelope (R1, R2 or RE), ADU, JADU and guest house limits, each with the regulation text
          it comes from and a label saying how much to trust it.
        </p>
        <p class="small muted">Try 2121-005-008 (Reseda), 4412-014-028 (Pacific Palisades) or 5179-003-026 (Boyle Heights).</p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.search {
  display: flex;
  flex: 1 1 420px;
  gap: 8px;
  min-width: 0;
}
.search .field {
  flex: 1 1 auto;
  min-width: 0;
  height: 44px;
}
.stop-items {
  max-width: 640px;
  margin-top: 16px;
  padding: 24px;
}
.stop-items h2 {
  margin: 0 0 12px;
  font-size: 16px;
}
.stop-item + .stop-item {
  border-top: 1px solid var(--line);
  margin-top: 12px;
  padding-top: 12px;
}
.stop-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
}
.stop-note {
  max-width: 640px;
  margin: 12px auto 0;
}
.disclaimer {
  background: var(--accent-subtle);
  border-bottom: 1px solid var(--line);
}
.disclaimer p {
  max-width: 1440px;
  margin: 0 auto;
  padding: 8px 24px;
}
.page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 24px;
}
.cols {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  align-items: flex-start;
}
.left {
  flex: 1 1 340px;
  max-width: 420px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.mid {
  flex: 999 1 560px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.right {
  flex: 1 1 340px;
  max-width: 420px;
  min-width: 0;
  position: sticky;
  top: 16px;
}
.parcel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.apn {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
h1 {
  margin: 0;
  font-size: 28px;
  line-height: 34px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.fact {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 10px 0 0;
  border: 0;
  border-top: 1px solid var(--line);
  background: none;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.fact.on .strong {
  color: var(--accent-hover);
}
.fk {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.strong {
  font-weight: 600;
}
.fig {
  margin: 0;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.toggle {
  display: flex;
  gap: 0;
  align-self: flex-start;
}
.toggle button {
  min-height: 32px;
  padding: 0 12px;
  border: 1px solid var(--line-strong);
  background: var(--surface);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  color: var(--ink);
}
.toggle button:first-child {
  border-radius: var(--radius-sm) 0 0 var(--radius-sm);
}
.toggle button:last-child {
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  border-left: 0;
}
.toggle button.on {
  background: var(--ink);
  border-color: var(--ink);
  color: #fff;
}
.ghead {
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
h2 {
  margin: 0;
  font-size: 18px;
  line-height: 24px;
  font-weight: 600;
}
.row {
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  align-items: center;
  padding: 12px 16px;
  border: 0;
  border-bottom: 1px solid var(--line);
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: var(--surface);
}
.row:last-child {
  border-bottom: 0;
  border-radius: 0 0 var(--radius-md) var(--radius-md);
}
.row:hover {
  background: var(--canvas);
}
.row.on {
  background: var(--accent-subtle);
}
.rt {
  flex: 1 1 180px;
  min-width: 0;
}
.rv {
  flex: 0 0 auto;
  min-width: 120px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.rc {
  flex: 0 0 auto;
  min-width: 140px;
}
.alert {
  padding: 12px 16px;
  border-color: var(--accent);
  border-left-width: 4px;
}
.fire {
  margin-bottom: 24px;
}
.alert p {
  margin: 4px 0 0;
}
.note {
  padding: 12px 16px;
}
.intro {
  max-width: 720px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.intro p,
.mid > p,
.left > p {
  margin: 0;
}
@media (max-width: 1100px) {
  .right {
    position: static;
  }
}
/* Phones: the answer first, then the parcel facts and drawing, then the source text. */
@media (max-width: 760px) {
  .mid {
    order: -1;
  }
}
</style>
