<script setup lang="ts">
import { ref, watch } from 'vue'
import { assess, decideFeedback, feedbackList, type FeedbackRow } from '../api'
import { formatApn, formatDate } from '../format'

const KIND: Record<string, string> = {
  wrong_value: 'Value is wrong',
  bad_citation: "Citation doesn't support it",
  missing_rule: 'A rule is missing',
  other: 'Something else',
}
const emit = defineEmits<{ openFragment: [number] }>()
const status = ref<FeedbackRow['status']>('new')
// Rule candidates behind the reported value, looked up by re-running the assessment for that APN.
const rules = ref<Record<number, { id: number; section: string }[] | 'none' | 'loading'>>({})

async function findRules(r: FeedbackRow) {
  if (!r.apn || !r.item_id) return
  rules.value[r.id] = 'loading'
  try {
    const a = await assess(r.apn)
    const item = [...a.items, ...a.parcel.items].find((i) => i.id === r.item_id)
    const seen = new Set<number>()
    const found = (item?.citations ?? [])
      .filter((c) => c.fragment_id != null && !seen.has(c.fragment_id) && seen.add(c.fragment_id))
      .map((c) => ({ id: c.fragment_id as number, section: c.section_id }))
    rules.value[r.id] = found.length ? found : 'none'
  } catch {
    rules.value[r.id] = 'none'
  }
}
const rows = ref<FeedbackRow[]>([])
const error = ref<string | null>(null)

async function load() {
  error.value = null
  try {
    rows.value = await feedbackList(status.value)
  } catch {
    error.value = "Couldn't load feedback."
  }
}
watch(status, load, { immediate: true })

async function mark(r: FeedbackRow, s: 'reviewed' | 'dismissed') {
  try {
    await decideFeedback(r.id, s)
    rows.value = rows.value.filter((x) => x.id !== r.id)
  } catch {
    error.value = "Couldn't update that note."
  }
}
</script>

<template>
  <section aria-label="Feedback" class="card fb">
    <div class="head">
      <label for="fbs" class="sr-only">Feedback status</label>
      <select id="fbs" v-model="status" class="field small">
        <option value="new">New</option>
        <option value="reviewed">Reviewed</option>
        <option value="dismissed">Dismissed</option>
      </select>
      <span class="small muted"
        >Notes from "Report a problem". Marking one reviewed never changes a rule; a rule changes only through a review decision on its
        candidate. The hosted demo deletes notes after a day.</span
      >
    </div>
    <p v-if="error" class="small err" role="alert">{{ error }}</p>
    <p v-else-if="!rows.length" class="small muted empty">Nothing here.</p>
    <div v-for="r in rows" :key="r.id" class="row">
      <div class="main">
        <span class="strong">{{ KIND[r.kind] ?? r.kind }}</span>
        <span class="small muted">
          {{ formatDate(r.created_at) }}
          <template v-if="r.apn">
            ·
            <RouterLink :to="{ path: '/', query: { q: r.apn } }" class="mono">APN {{ formatApn(r.apn) }}</RouterLink></template
          >
          <template v-if="r.item_id">
            · <span class="mono">{{ r.item_id }}</span></template
          >
          <template v-if="r.reviewed_by"> · {{ r.status }} by {{ r.reviewed_by }}</template>
        </span>
        <p v-if="r.comment" class="small">{{ r.comment }}</p>
        <div v-if="r.apn && r.item_id" class="rules small">
          <button v-if="!rules[r.id]" type="button" class="link" @click="findRules(r)">Find the rules behind this value</button>
          <span v-else-if="rules[r.id] === 'loading'" class="muted">Looking up…</span>
          <span v-else-if="rules[r.id] === 'none'" class="muted">No reviewed rule behind it (parcel data or a computed value).</span>
          <template v-else>
            <span class="muted">Rules:</span>
            <button
              v-for="f in rules[r.id] as { id: number; section: string }[]"
              :key="f.id"
              type="button"
              class="chip mono"
              @click="emit('openFragment', f.id)"
            >
              #{{ f.id }} {{ f.section }}
            </button>
          </template>
        </div>
      </div>
      <div v-if="r.status === 'new'" class="act">
        <button type="button" class="btn btn-secondary" @click="mark(r, 'reviewed')">Mark reviewed</button>
        <button type="button" class="btn btn-secondary" @click="mark(r, 'dismissed')">Dismiss</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.head {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
}
.row {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  flex-wrap: wrap;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
}
.row:last-child {
  border-bottom: 0;
}
.main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1 1 320px;
}
.act {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.strong {
  font-weight: 600;
}
.empty,
.err {
  padding: 12px 16px;
  margin: 0;
}
.err {
  color: var(--danger);
}
p {
  margin: 0;
}
.rules {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 4px;
}
.link {
  border: 0;
  background: none;
  padding: 0;
  color: var(--accent);
  text-decoration: underline;
  cursor: pointer;
  font: inherit;
}
.chip {
  min-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  font-size: 12px;
  cursor: pointer;
  color: var(--ink);
}
</style>
