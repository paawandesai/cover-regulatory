<script setup lang="ts">
import { ref, watch } from 'vue'
import { auditLog } from '../api'
import type { AuditRow } from '../types'

// Every review action, newest first. The server keeps this log append-only; nothing here can change it.
const emit = defineEmits<{ 'open-fragment': [id: number] }>()
const kind = ref<AuditRow['object_type'] | ''>('')
const rows = ref<AuditRow[]>([])
const error = ref<string | null>(null)
watch(
  kind,
  async () => {
    error.value = null
    try {
      rows.value = await auditLog(kind.value)
    } catch {
      error.value = "Couldn't load the audit log."
    }
  },
  { immediate: true },
)

const ACTION: Record<string, string> = {
  fragment_approved: 'Approved rule text',
  fragment_rejected: 'Rejected rule text',
  fragment_to_pending: 'Sent rule text back to review (source changed)',
  fragment_retired: 'Retired rule text (quote gone from the source)',
  feedback_reviewed: 'Marked feedback reviewed',
  feedback_dismissed: 'Dismissed feedback',
  report_signed: 'Signed a client report',
  report_withdrawn: 'Withdrew a client report',
  reviewer_added: 'Added or reset a reviewer',
  reviewer_deactivated: 'Deactivated a reviewer',
}
const who = (r: AuditRow) =>
  r.actor === 'ai-review' ? 'AI review' : r.actor === 'source-refresh' ? 'Weekly source check' : (r.display_name ?? r.actor)
const extra = (r: AuditRow) => {
  const d = r.detail as Record<string, string | null>
  if (d.instructed_by) return `on ${d.instructed_by}'s instruction (${d.file})`
  if (d.license) return `license ${d.license}`
  return d.note ?? ''
}
</script>

<template>
  <div>
    <div class="bar">
      <label for="ak" class="sr-only">What changed</label>
      <select id="ak" v-model="kind" class="field small">
        <option value="">Everything</option>
        <option value="rule_fragment">Rule text</option>
        <option value="feedback">Feedback</option>
        <option value="report">Client reports</option>
        <option value="reviewer">Reviewer accounts</option>
      </select>
      <span class="small muted">Who did what, and when. Entries can't be edited or deleted.</span>
    </div>
    <p v-if="error" class="small err">{{ error }}</p>
    <div class="card scroll">
      <p v-if="!rows.length" class="small muted empty">Nothing recorded yet.</p>
      <table v-else>
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Who</th>
            <th scope="col">What</th>
            <th scope="col">On</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td class="small nowrap">{{ r.at.slice(0, 16).replace('T', ' ') }} UTC</td>
            <td class="small">{{ who(r) }}</td>
            <td class="small">
              {{ ACTION[r.action] ?? r.action }}<span v-if="extra(r)" class="muted"> · {{ extra(r) }}</span>
            </td>
            <td class="small mono">
              <button v-if="r.object_type === 'rule_fragment'" type="button" class="link" @click="emit('open-fragment', Number(r.object_id))">
                Rule #{{ r.object_id }}
              </button>
              <template v-else>{{ r.object_type === 'report' ? 'Report' : r.object_type === 'feedback' ? 'Feedback' : 'Reviewer' }} {{ r.object_id }}</template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.scroll {
  overflow-x: auto;
}
.empty {
  padding: 16px;
  margin: 0;
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
.err {
  color: var(--danger);
}
</style>
