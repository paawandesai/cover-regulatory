<script setup lang="ts">
import { ref, watch } from 'vue'
import { ApiError, createReport } from '../api'
import type { ProjectInputs } from '../types'

// Freezes this assessment (and the project being checked) as a client report. Its link opens only after a licensed
// reviewer signs it in Rule review.
const props = defineProps<{ apn: string; inputs: Partial<ProjectInputs> }>()
const link = ref<string | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)
const copied = ref(false)
watch(
  () => [props.apn, JSON.stringify(props.inputs)],
  () => ((link.value = null), (copied.value = false)),
)

async function create() {
  busy.value = true
  error.value = null
  try {
    const r = await createReport(props.apn, props.inputs)
    link.value = `${location.origin}/report/${r.token}`
  } catch (e) {
    error.value = e instanceof ApiError && e.status === 429 ? 'Too many reports this hour. Try again later.' : "Couldn't create the report."
  } finally {
    busy.value = false
  }
}

async function copy() {
  if (!link.value) return
  try {
    await navigator.clipboard.writeText(link.value)
    copied.value = true
  } catch {
    /* clipboard blocked; the link is shown to copy by hand */
  }
}
</script>

<template>
  <div class="card rep">
    <div class="ghead">
      <h2>Client report</h2>
      <span class="small muted">Opens for the client only after a licensed reviewer signs it</span>
    </div>
    <div class="body">
      <button v-if="!link" type="button" class="btn btn-secondary" :disabled="busy" @click="create">
        {{ busy ? 'Creating…' : 'Create a report for sign-off' }}
      </button>
      <template v-else>
        <p class="small">Sent for sign-off. This link shows "Awaiting sign-off" until a reviewer signs it:</p>
        <p class="small mono linkline">{{ link }}</p>
        <button type="button" class="btn btn-secondary" @click="copy">{{ copied ? 'Copied' : 'Copy link' }}</button>
      </template>
      <p v-if="error" class="small err" role="alert">{{ error }}</p>
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
.body {
  padding: 12px 16px;
}
.body p {
  margin: 0 0 8px;
}
.linkline {
  word-break: break-all;
}
.err {
  color: var(--danger);
}
</style>
