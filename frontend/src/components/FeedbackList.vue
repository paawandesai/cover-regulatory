<script setup lang="ts">
import { ref, watch } from 'vue'
import { decideFeedback, feedbackList, type FeedbackRow } from '../api'
import { formatApn, formatDate } from '../format'

const KIND: Record<string, string> = {
  wrong_value: 'Value is wrong',
  bad_citation: "Citation doesn't support it",
  missing_rule: 'A rule is missing',
  other: 'Something else',
}
const status = ref<FeedbackRow['status']>('new')
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
</style>
