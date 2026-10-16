<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ApiError, previewReport, reportList, signReport, withdrawReport } from '../api'
import { formatApn, formatDate } from '../format'
import type { Report, ReportRow } from '../types'
import ReportBody from './ReportBody.vue'

// Reviewer's queue of client reports: read each one in full, then sign it (which unlocks its link) or withdraw it.
const status = ref<Report['status']>('awaiting_signoff')
const rows = ref<ReportRow[]>([])
const open = ref<Report | null>(null)
const error = ref<string | null>(null)
const form = reactive({ signer_name: '', signer_license: '', note: '', statement_accepted: false })
const signError = ref<string | null>(null)

async function load() {
  error.value = null
  try {
    rows.value = await reportList(status.value)
  } catch {
    error.value = "Couldn't load reports."
  }
}
watch(status, () => ((open.value = null), load()), { immediate: true })

async function show(token: string) {
  signError.value = null
  open.value = await previewReport(token)
}

const link = (token: string) => `${location.origin}/report/${token}`

async function sign() {
  if (!open.value) return
  signError.value = null
  try {
    await signReport(open.value.token, { ...form, note: form.note.trim() || null })
    await show(open.value.token)
    await load()
  } catch (e) {
    signError.value = e instanceof ApiError && e.status === 422 ? 'Enter your name and license, and accept the statement.' : "Couldn't sign."
  }
}

async function withdraw() {
  if (!open.value) return
  await withdrawReport(open.value.token)
  open.value = null
  await load()
}
</script>

<template>
  <div class="wrap">
    <div class="bar">
      <label for="rs" class="sr-only">Report status</label>
      <select id="rs" v-model="status" class="field small">
        <option value="awaiting_signoff">Awaiting sign-off</option>
        <option value="signed">Signed</option>
        <option value="withdrawn">Withdrawn</option>
      </select>
      <span class="small muted">A report's link shows nothing until it is signed here.</span>
    </div>
    <p v-if="error" class="small err">{{ error }}</p>
    <div class="cols">
      <section aria-label="Reports" class="card listcol">
        <p v-if="!rows.length" class="empty small muted">Nothing here.</p>
        <button v-for="r in rows" :key="r.token" type="button" class="row" :class="{ on: open?.token === r.token }" @click="show(r.token)">
          <span class="strong">APN {{ formatApn(r.apn) }}</span>
          <span class="small muted">Created {{ formatDate(r.created_at) }}{{ r.signer_name ? ` · signed by ${r.signer_name}` : '' }}</span>
        </button>
      </section>
      <section v-if="open" aria-label="Report" class="detail">
        <div class="card signbox">
          <template v-if="open.status === 'awaiting_signoff'">
            <h2>Sign this report</h2>
            <form class="grid" @submit.prevent="sign">
              <label>
                <span class="small muted">Your name</span>
                <input v-model="form.signer_name" class="field" required minlength="3" maxlength="120" />
              </label>
              <label>
                <span class="small muted">License type and number</span>
                <input v-model="form.signer_license" class="field" required minlength="3" maxlength="60" placeholder="e.g. Architect C-12345" />
              </label>
              <label class="wide">
                <span class="small muted">Note to the client (optional)</span>
                <textarea v-model="form.note" class="field" rows="2" maxlength="2000" />
              </label>
              <label class="wide check">
                <input v-model="form.statement_accepted" type="checkbox" />
                <span class="small">{{ open.statement }}</span>
              </label>
              <div class="wide actions">
                <button type="submit" class="btn btn-primary">Sign and unlock the link</button>
                <button type="button" class="btn btn-secondary" @click="withdraw">Withdraw</button>
              </div>
              <p v-if="signError" class="small err wide" role="alert">{{ signError }}</p>
            </form>
          </template>
          <template v-else-if="open.status === 'signed'">
            <h2>Signed</h2>
            <p class="small">
              Share this link with the client: <a :href="link(open.token)" target="_blank" rel="noopener">{{ link(open.token) }}</a>
            </p>
            <button type="button" class="btn btn-secondary" @click="withdraw">Withdraw</button>
          </template>
          <p v-else class="small muted">Withdrawn. The link no longer opens.</p>
        </div>
        <ReportBody :report="open" />
      </section>
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
.cols {
  display: grid;
  grid-template-columns: minmax(220px, 300px) 1fr;
  gap: 16px;
  align-items: start;
}
@media (max-width: 800px) {
  .cols {
    grid-template-columns: 1fr;
  }
}
.listcol {
  overflow: hidden;
}
.empty {
  padding: 16px;
  margin: 0;
}
.row {
  display: flex;
  flex-direction: column;
  width: 100%;
  text-align: left;
  padding: 10px 16px;
  border: 0;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  font: inherit;
  color: inherit;
  cursor: pointer;
}
.row.on {
  background: var(--accent-subtle);
}
.strong {
  font-weight: 600;
}
.signbox {
  padding: 16px;
  margin-bottom: 16px;
}
h2 {
  margin: 0 0 12px;
  font-size: 18px;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.wide {
  grid-column: 1 / -1;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.check {
  flex-direction: row;
  align-items: flex-start;
  gap: 8px;
}
.field {
  width: 100%;
}
.actions {
  display: flex;
  gap: 8px;
}
.err {
  color: var(--danger);
}
@media (max-width: 640px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
