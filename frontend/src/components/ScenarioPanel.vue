<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { assess } from '../api'
import type { ProjectCheck, ProjectInputs } from '../types'

// Saved project scenarios for one parcel, kept only in this browser (localStorage). Nothing is sent to the server
// until a comparison runs, and then only as the same query an ordinary check sends.
const props = defineProps<{ apn: string; inputs: Partial<ProjectInputs> }>()
const emit = defineEmits<{ load: [Partial<ProjectInputs>] }>()

type Scenario = { name: string; inputs: Partial<ProjectInputs> }
const MAX = 4
const key = computed(() => `scenarios:${props.apn}`)
const saved = ref<Scenario[]>([])
const name = ref('')
const compared = ref<{ name: string; checks: ProjectCheck[] }[] | null>(null)
const busy = ref(false)
const failed = ref(false)

function read(): Scenario[] {
  try {
    const raw = localStorage.getItem(key.value)
    const v = raw ? JSON.parse(raw) : []
    return Array.isArray(v) ? v.slice(0, MAX) : []
  } catch {
    return []
  }
}
function write() {
  try {
    localStorage.setItem(key.value, JSON.stringify(saved.value))
  } catch {
    /* storage blocked: scenarios last for this page only */
  }
}
watch(
  key,
  () => {
    saved.value = read()
    compared.value = null
  },
  { immediate: true },
)

const hasInputs = computed(() => Object.values(props.inputs).some((v) => v !== undefined))

function save() {
  if (!hasInputs.value || saved.value.length >= MAX) return
  saved.value = [...saved.value, { name: name.value.trim() || `Scenario ${saved.value.length + 1}`, inputs: { ...props.inputs } }]
  name.value = ''
  compared.value = null
  write()
}
function remove(i: number) {
  saved.value = saved.value.filter((_, k) => k !== i)
  compared.value = null
  write()
}

const UNIT: Record<string, string> = { detached: 'detached ADU', attached: 'attached ADU', jadu: 'JADU', guest_house: 'guest house' }
function describe(p: Partial<ProjectInputs>): string {
  const parts: string[] = []
  if (p.height_ft) parts.push(`${p.height_ft} ft high`)
  if (p.floor_area_sqft) parts.push(`${p.floor_area_sqft.toLocaleString('en-US')} sq ft`)
  if (p.second_unit) parts.push(UNIT[p.second_unit] + (p.second_unit_sqft ? ` ${p.second_unit_sqft} sq ft` : ''))
  if (p.side_wall_ft) parts.push(`${p.side_wall_ft} ft side wall`)
  return parts.join(', ') || 'No inputs'
}

async function compare() {
  busy.value = true
  failed.value = false
  try {
    const results = await Promise.all(saved.value.map((s) => assess(props.apn, s.inputs)))
    compared.value = saved.value.map((s, i) => ({ name: s.name, checks: results[i]?.project?.checks ?? [] }))
  } catch {
    failed.value = true
  } finally {
    busy.value = false
  }
}

// Check titles carry each scenario's own numbers ("House height 30 ft"), so rows use a plain name and each cell
// keeps its own title as a tooltip.
const ROW_NAME: Record<string, string> = {
  height: 'House height',
  side_yard: 'Side yards',
  floor_area: 'Floor area',
  plane_break: 'Side wall plane break',
  guest_house: 'Guest house',
  jadu: 'Junior ADU',
  adu_attached: 'Attached ADU',
  adu_detached: 'Detached ADU',
}

// One row per check that any scenario produced, in first-seen order.
const rows = computed(() => {
  const c = compared.value
  if (!c) return []
  const seen = new Map<string, string>()
  for (const s of c) for (const ch of s.checks) if (!seen.has(ch.id)) seen.set(ch.id, ROW_NAME[ch.id] ?? ch.title)
  return [...seen].map(([id, title]) => ({ id, title, cells: c.map((s) => s.checks.find((ch) => ch.id === id) ?? null) }))
})

const STATUS: Record<ProjectCheck['status'], string> = {
  fits: 'Fits',
  confirm: 'Fits, confirm',
  exceeds: 'Over',
  not_determined: 'Not determined',
}
</script>

<template>
  <div class="card scen">
    <div class="ghead">
      <h2>Scenarios</h2>
      <span class="small muted">Saved in this browser only, up to {{ MAX }} per lot</span>
    </div>
    <form class="save" @submit.prevent="save">
      <label class="grow">
        <span class="sr-only">Scenario name</span>
        <input v-model="name" class="field" maxlength="40" placeholder="Name this scenario (optional)" />
      </label>
      <button type="submit" class="btn btn-secondary" :disabled="!hasInputs || saved.length >= MAX">Save current project</button>
    </form>
    <p v-if="!hasInputs && !saved.length" class="small muted pad">Check a project above, then save it here to compare it with others.</p>
    <ul v-if="saved.length" class="list">
      <li v-for="(s, i) in saved" :key="i">
        <span class="ct">
          <span class="strong">{{ s.name }}</span>
          <span class="small muted">{{ describe(s.inputs) }}</span>
        </span>
        <button type="button" class="link" @click="emit('load', s.inputs)">Load</button>
        <button type="button" class="link" :aria-label="`Remove ${s.name}`" @click="remove(i)">Remove</button>
      </li>
    </ul>
    <div v-if="saved.length >= 2" class="pad">
      <button type="button" class="btn btn-primary" :disabled="busy" @click="compare">{{ busy ? 'Comparing…' : 'Compare side by side' }}</button>
      <p v-if="failed" class="small danger">The comparison could not be loaded. Try again.</p>
    </div>
    <div v-if="compared && rows.length" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Check</th>
            <th v-for="s in compared" :key="s.name" scope="col">{{ s.name }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <th scope="row">{{ r.title }}</th>
            <td v-for="(c, k) in r.cells" :key="k">
              <span v-if="c" class="st" :class="c.status" :title="`${c.title}. ${c.detail}`">{{ STATUS[c.status] }}</span>
              <span v-else class="small muted">n/a</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
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
.save {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  flex-wrap: wrap;
}
.grow {
  flex: 1 1 200px;
}
.field {
  height: 40px;
  width: 100%;
}
.pad {
  padding: 0 16px 12px;
  margin: 0;
}
.list {
  list-style: none;
  margin: 0 0 12px;
  padding: 0;
  border-top: 1px solid var(--line);
}
.list li {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--line);
}
.ct {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}
.strong {
  font-weight: 600;
}
.link {
  border: 0;
  background: none;
  color: var(--accent);
  text-decoration: underline;
  cursor: pointer;
  font: inherit;
  padding: 4px;
}
.danger {
  color: var(--danger);
}
.table-wrap {
  overflow-x: auto;
  border-top: 1px solid var(--line);
}
table {
  border-collapse: collapse;
  width: 100%;
  font-size: 14px;
}
th,
td {
  text-align: left;
  padding: 8px 16px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
thead th {
  font-weight: 600;
}
tbody th {
  font-weight: 400;
}
.st {
  font-size: 12px;
  line-height: 16px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid;
  white-space: nowrap;
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
