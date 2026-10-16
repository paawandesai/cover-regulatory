<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import type { ProjectCheck, ProjectInputs, SecondUnit } from '../types'

const props = defineProps<{ inputs: Partial<ProjectInputs>; checks: ProjectCheck[] }>()
const emit = defineEmits<{ apply: [Partial<ProjectInputs>]; pick: [string] }>()

type Draft = {
  height_ft: string
  floor_area_sqft: string
  second_unit: SecondUnit | ''
  second_unit_sqft: string
  second_unit_bedrooms: string
  covered_parking_sqft: string
  parking_in_rear: '' | 'true' | 'false'
  accessory_sqft: string
  tall_ceiling_sqft: string
  side_wall_ft: string
}
const draft = reactive<Draft>({
  height_ft: '',
  floor_area_sqft: '',
  second_unit: '',
  second_unit_sqft: '',
  second_unit_bedrooms: '',
  covered_parking_sqft: '',
  parking_in_rear: '',
  accessory_sqft: '',
  tall_ceiling_sqft: '',
  side_wall_ft: '',
})
const more = ref(false)

watch(
  () => props.inputs,
  (i) => {
    draft.height_ft = i.height_ft?.toString() ?? ''
    draft.floor_area_sqft = i.floor_area_sqft?.toString() ?? ''
    draft.second_unit = i.second_unit ?? ''
    draft.second_unit_sqft = i.second_unit_sqft?.toString() ?? ''
    draft.second_unit_bedrooms = i.second_unit_bedrooms?.toString() ?? ''
    draft.covered_parking_sqft = i.covered_parking_sqft?.toString() ?? ''
    draft.parking_in_rear = i.parking_in_rear === undefined ? '' : i.parking_in_rear ? 'true' : 'false'
    draft.accessory_sqft = i.accessory_sqft?.toString() ?? ''
    draft.tall_ceiling_sqft = i.tall_ceiling_sqft?.toString() ?? ''
    draft.side_wall_ft = i.side_wall_ft?.toString() ?? ''
    if (i.covered_parking_sqft || i.accessory_sqft || i.tall_ceiling_sqft || i.side_wall_ft) more.value = true
  },
  { immediate: true },
)

const n = (s: string) => (s.trim() && Number(s) > 0 ? Number(s) : undefined)

function apply() {
  emit('apply', {
    height_ft: n(draft.height_ft),
    floor_area_sqft: n(draft.floor_area_sqft),
    second_unit: draft.second_unit || undefined,
    second_unit_sqft: draft.second_unit ? n(draft.second_unit_sqft) : undefined,
    second_unit_bedrooms: draft.second_unit === 'attached' ? n(draft.second_unit_bedrooms) : undefined,
    covered_parking_sqft: n(draft.covered_parking_sqft),
    parking_in_rear: n(draft.covered_parking_sqft) && draft.parking_in_rear ? draft.parking_in_rear === 'true' : undefined,
    accessory_sqft: n(draft.accessory_sqft),
    tall_ceiling_sqft: n(draft.tall_ceiling_sqft),
    side_wall_ft: n(draft.side_wall_ft),
  })
}

function clear() {
  emit('apply', {})
}

const STATUS: Record<ProjectCheck['status'], string> = {
  fits: 'Fits',
  confirm: 'Fits, confirm',
  exceeds: 'Over the limit',
  not_determined: 'Not determined',
}
</script>

<template>
  <div class="card proj">
    <div class="ghead">
      <h2>Your project</h2>
      <span class="small muted">Optional. Checked against the values below; nothing is stored on the server.</span>
    </div>
    <form class="grid" @submit.prevent="apply">
      <label>
        <span class="small muted">House height (ft)</span>
        <input v-model="draft.height_ft" class="field" inputmode="decimal" placeholder="e.g. 26" />
      </label>
      <label>
        <span class="small muted">Floor area on the lot (sq ft)</span>
        <input v-model="draft.floor_area_sqft" class="field" inputmode="decimal" placeholder="e.g. 3000" />
      </label>
      <label>
        <span class="small muted">Second unit</span>
        <select v-model="draft.second_unit" class="field">
          <option value="">None</option>
          <option value="detached">Detached ADU</option>
          <option value="attached">Attached ADU</option>
          <option value="jadu">Junior ADU</option>
          <option value="guest_house">Guest house (no kitchen)</option>
        </select>
      </label>
      <label v-if="draft.second_unit && draft.second_unit !== 'guest_house'">
        <span class="small muted">Its size (sq ft)</span>
        <input v-model="draft.second_unit_sqft" class="field" inputmode="decimal" placeholder="e.g. 750" />
      </label>
      <label v-if="draft.second_unit === 'attached'">
        <span class="small muted">Bedrooms</span>
        <input v-model="draft.second_unit_bedrooms" class="field" inputmode="numeric" placeholder="e.g. 1" />
      </label>
      <details class="more" :open="more" @toggle="more = ($event.target as HTMLDetailsElement).open">
        <summary class="small">Floor-area details and side walls</summary>
        <p class="small muted hint">
          With these, floor area is the gross area inside the exterior walls of every building on the lot, and the exemptions in LAMC 12.03
          are taken off.
        </p>
        <div class="grid inner">
          <label>
            <span class="small muted">Required covered parking (sq ft)</span>
            <input v-model="draft.covered_parking_sqft" class="field" inputmode="decimal" placeholder="e.g. 400" />
          </label>
          <label v-if="draft.covered_parking_sqft">
            <span class="small muted">Where the parking is</span>
            <select v-model="draft.parking_in_rear" class="field">
              <option value="">Not sure</option>
              <option value="true">Rear half, or 55 ft+ from the front</option>
              <option value="false">Nearer the front</option>
            </select>
          </label>
          <label>
            <span class="small muted">Sheds and other small detached buildings (sq ft)</span>
            <input v-model="draft.accessory_sqft" class="field" inputmode="decimal" placeholder="each 200 or less" />
          </label>
          <label>
            <span class="small muted">Floor under ceilings over 14 ft (sq ft)</span>
            <input v-model="draft.tall_ceiling_sqft" class="field" inputmode="decimal" placeholder="e.g. 200" />
          </label>
          <label>
            <span class="small muted">Longest side wall over 14 ft high (ft)</span>
            <input v-model="draft.side_wall_ft" class="field" inputmode="decimal" placeholder="e.g. 48" />
          </label>
        </div>
      </details>
      <div class="actions">
        <button type="submit" class="btn btn-primary">Check</button>
        <button v-if="checks.length" type="button" class="btn btn-secondary" @click="clear">Clear</button>
      </div>
    </form>
    <ul v-if="checks.length" class="checks" aria-live="polite">
      <li v-for="c in checks" :key="c.id">
        <button type="button" class="check" :disabled="!c.based_on" @click="c.based_on && emit('pick', c.based_on)">
          <span class="st" :class="c.status">{{ STATUS[c.status] }}</span>
          <span class="ct">
            <span class="strong">{{ c.title }}</span>
            <span class="small muted">{{ c.detail }}</span>
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
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
.grid {
  padding: 12px 16px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 12px;
  align-items: end;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.field {
  height: 40px;
  width: 100%;
}
.actions {
  display: flex;
  gap: 8px;
}
.more {
  grid-column: 1 / -1;
}
.more summary {
  cursor: pointer;
  font-weight: 600;
}
.hint {
  margin: 8px 0 0;
}
.grid.inner {
  padding: 8px 0 0;
}
.checks {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--line);
}
.check {
  width: 100%;
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 10px 16px;
  border: 0;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.check:disabled {
  cursor: default;
}
li:last-child .check {
  border-bottom: 0;
  border-radius: 0 0 var(--radius-md) var(--radius-md);
}
.ct {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.strong {
  font-weight: 600;
}
.st {
  flex: 0 0 112px;
  font-size: 12px;
  line-height: 16px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid;
  text-align: center;
  margin-top: 2px;
}
.fits {
  color: var(--success);
}
.confirm {
  color: var(--accent-hover);
  background: var(--accent-subtle);
  border-color: var(--accent-subtle);
}
.exceeds {
  color: var(--danger);
}
.not_determined {
  color: var(--ink-muted);
  border-style: dashed;
}
</style>
