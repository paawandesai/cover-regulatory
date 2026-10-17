<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { sourceChecks } from '../api'
import { formatDate } from '../format'
import type { SourceRow } from '../types'

// The weekly source check per document. Changed text has already sent its rules back to review; a hand-saved
// source past its re-check date needs a person to save a fresh copy.
const rows = ref<SourceRow[]>([])
const error = ref<string | null>(null)
onMounted(async () => {
  try {
    rows.value = await sourceChecks()
  } catch {
    error.value = "Couldn't load the source checks."
  }
})

const OUTCOME: Record<NonNullable<SourceRow['outcome']>, string> = {
  unchanged: 'Unchanged',
  changed: 'Changed: rules sent back to review',
  failed: "Couldn't fetch",
  manual_due: 'Due for a hand re-check',
  manual_ok: 'Saved by hand, recent',
}
const alert = (r: SourceRow) => r.outcome === 'changed' || r.outcome === 'failed' || r.outcome === 'manual_due'
const detail = (r: SourceRow) => {
  const d = r.detail ?? {}
  if (r.outcome === 'changed')
    return `${d.to_pending ?? 0} back to review, ${d.retired ?? 0} retired${d.decided_lost ? `, ${d.decided_lost} removed with their text` : ''}`
  if (r.outcome === 'failed') return String(d.error ?? '')
  if (d.age_days != null) return `${d.age_days} day${d.age_days === 1 ? '' : 's'} old`
  return ''
}
</script>

<template>
  <div>
    <p class="small muted intro">
      Downloadable sources are re-fetched weekly. When one changes, every rule whose text changed goes back to review (or is retired if its quote is
      gone). Hand-saved sources are never fetched; they are listed as due after 90 days.
    </p>
    <p v-if="error" class="small err">{{ error }}</p>
    <div class="card scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">Source</th>
            <th scope="col">Last check</th>
            <th scope="col">Result</th>
            <th scope="col">Pending rules</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id" :class="{ alert: alert(r) }">
            <td class="small">
              <a :href="r.source_url" target="_blank" rel="noopener">{{ r.title }}</a>
              <span class="muted"> · loaded {{ formatDate(r.retrieved_at) }}</span>
            </td>
            <td class="small nowrap">{{ r.checked_at ? formatDate(r.checked_at) : 'Not yet checked' }}</td>
            <td class="small">
              <span :class="{ strong: alert(r) }">{{ r.outcome ? OUTCOME[r.outcome] : '' }}</span>
              <span v-if="detail(r)" class="muted"> · {{ detail(r) }}</span>
            </td>
            <td class="small">{{ r.pending }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.intro {
  margin: 0 0 12px;
  max-width: 72ch;
}
.scroll {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  text-align: left;
  vertical-align: top;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line);
}
th {
  font-size: 12px;
  font-weight: 600;
}
.nowrap {
  white-space: nowrap;
}
tr.alert td:first-child {
  box-shadow: inset 3px 0 0 var(--danger);
}
.strong {
  font-weight: 600;
}
.err {
  color: var(--danger);
}
</style>
