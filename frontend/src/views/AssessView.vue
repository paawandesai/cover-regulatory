<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, assess } from '../api'
import AppHeader from '../components/AppHeader.vue'
import LabelBadge from '../components/LabelBadge.vue'
import LotDiagram from '../components/LotDiagram.vue'
import SourcePanel from '../components/SourcePanel.vue'
import StopState from '../components/StopState.vue'
import { citeLabel, formatApn, formatDate, formatExisting, formatValue } from '../format'
import type { Assessment, Item } from '../types'

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

// On narrow screens the source panel sits below the list; bring it into view when a row is picked.
async function pick(id: string) {
  pickedId.value = id
  if (window.matchMedia('(max-width: 1100px)').matches) {
    await nextTick()
    panel.value?.$el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

async function load(q: string) {
  loading.value = true
  error.value = null
  try {
    const r = await assess(q)
    result.value = r
    const first = r.items.find((i) => i.citations.length && i.family !== 'parcel') ?? r.items[0]
    pickedId.value = first?.id ?? null
  } catch (e) {
    result.value = null
    error.value = e instanceof ApiError ? { status: e.status, message: e.message } : { status: 0, message: String(e) }
  } finally {
    loading.value = false
  }
}

watch(
  () => route.query.q,
  (q) => {
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
  const rows: { k: string; v: string; item: Item; text?: string }[] = []
  const add = (it: Item | undefined, k: string, v?: string, text?: string) =>
    it && rows.push({ k, v: v ?? formatValue(it), item: it, text })
  add(parcelItem('lot_area'), 'Lot area')
  add(dims.value, 'Lot width x depth', undefined, 'Derived (parcel shape)')
  add(parcelItem('community_plan_area'), 'Community plan area')
  const regime = parcelItem('code_regime')
  add(regime, 'Zoning code in effect', regime?.value === 'I' ? 'Chapter I' : regime?.value === '1A' ? 'Chapter 1A' : undefined)
  const existing = parcelItem('existing')
  add(existing, 'Existing building (Assessor)', formatExisting(existing?.value))
  return rows
})

const isHillside = computed(() => Boolean(item('hillside')?.value))
const groups = computed(() => {
  const r = result.value
  if (!r) return []
  const of = (fams: string[]) => r.items.filter((i) => fams.includes(i.family))
  return [
    {
      title: 'R1 envelope',
      sub: isHillside.value ? 'Hillside Area: flat-land values withheld' : 'Flat-land R1, two stories or less',
      rows: of(['r1_envelope']),
    },
    { title: 'What can be built', sub: 'Single-family home within the envelope above, plus', rows: of(['guest_house', 'adu', 'jadu']) },
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
        body: note || 'Only the R1 one-family zone family is modeled.',
        detail: 'No rules are shown rather than rules from the wrong zone.',
      }
  }
})
</script>

<template>
  <div>
    <AppHeader title="Regulatory Engine" subtitle="City of Los Angeles · Chapter I · R1">
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
        <button type="submit" class="btn btn-primary" :disabled="loading">{{ loading ? 'Assessing…' : 'Assess' }}</button>
      </form>
      <RouterLink to="/review" class="small">Rule review</RouterLink>
    </AppHeader>

    <div class="disclaimer">
      <p class="small">
        Decision support for licensed professionals, not a zoning determination. Confirm every result with LA City
        Planning and LADBS.
      </p>
    </div>

    <main class="page">
      <StopState
        v-if="error?.status === 404"
        eyebrow="Search"
        title="Address not found"
        body="That address isn't in the loaded parcel data. Try the 10-digit APN instead."
        detail="Lookup order: APN, City address points, County parcel situs, then the US Census geocoder."
      />
      <StopState
        v-else-if="error"
        eyebrow="Error"
        title="The assessment didn't load"
        :body="error.status === 422 ? 'Enter at least three characters.' : 'The server returned an error. Try again.'"
      />

      <template v-else-if="result && stop">
        <StopState :eyebrow="`APN ${formatApn(result.parcel.apn)}`" :title="stop.title" :body="stop.body" :detail="stop.detail" />
      </template>

      <div v-else-if="result" class="cols">
        <section aria-label="Parcel" class="left">
          <div class="card parcel">
            <div class="apn">
              <span class="eyebrow">APN</span>
              <span class="mono small">{{ formatApn(result.parcel.apn) }}</span>
            </div>
            <h1>{{ zone ? `${zone} one-family lot` : 'Parcel' }}</h1>
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
              <LabelBadge :label="f.item.label" :text="f.text" />
            </button>
          </div>

          <figure v-if="result.geometry" class="card fig">
            <div class="toggle" role="group" aria-label="Lot view">
              <button type="button" :aria-pressed="view === 'diagram'" :class="{ on: view === 'diagram' }" @click="view = 'diagram'">
                Diagram
              </button>
              <button type="button" :aria-pressed="view === 'map'" :class="{ on: view === 'map' }" @click="view = 'map'">
                Map
              </button>
            </div>
            <LotDiagram v-if="view === 'diagram'" :geometry="result.geometry" :dims="(dims?.value as string) ?? null" />
            <LotMap v-else :apn="result.parcel.apn" :geometry="result.geometry" />
            <figcaption class="small muted">
              Illustrative, not survey-grade. Front taken as the street-facing side.
              <template v-if="result.geometry.note"> {{ result.geometry.note[0].toUpperCase() + result.geometry.note.slice(1) }}.</template>
              <template v-if="view === 'map'"> Neighbouring parcel outlines from LA County Assessor data; no basemap.</template>
            </figcaption>
          </figure>

          <p class="small muted">
            Parcel data: LA County Assessor open parcels, fetched {{ parcelFetched }}. Informational only; not suitable
            for legal, engineering or surveying use.
          </p>
        </section>

        <section aria-label="Assessment" class="mid">
          <div v-if="fire" class="card alert" role="note">
            <strong>{{ fire.title }}</strong>
            <p class="small">{{ fire.explanation }}</p>
          </div>
          <div v-for="n in result.notes" :key="n" class="card note small">{{ n }}</div>

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
        </section>

        <SourcePanel v-if="picked" ref="panel" class="right" :item="picked" :apn="result.parcel.apn" />
      </div>

      <section v-else-if="!loading" class="card intro">
        <h1>Check what can be built on a City of LA R1 lot</h1>
        <p>
          Enter a 10-digit APN or a street address. You get the R1 envelope, ADU, JADU and guest house limits, each with
          the regulation text it comes from and a label saying how much to trust it.
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
  flex: 1 1 220px;
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
</style>
