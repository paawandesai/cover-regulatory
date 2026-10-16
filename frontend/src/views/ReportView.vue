<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ApiError, getReport } from '../api'
import ReportBody from '../components/ReportBody.vue'
import type { Report } from '../types'

const route = useRoute()
const report = ref<Report | null>(null)
const error = ref<string | null>(null)
const print = () => window.print()

onMounted(async () => {
  document.title = 'Client report · Regulatory Engine'
  try {
    report.value = await getReport(String(route.params.token))
  } catch (e) {
    error.value = e instanceof ApiError && e.status === 404 ? 'This report does not exist or was withdrawn.' : "Couldn't load the report."
  }
})
</script>

<template>
  <main class="wrap">
    <p v-if="error" class="card msg">{{ error }}</p>
    <p v-else-if="!report" class="small muted">Loading…</p>
    <div v-else-if="report.status !== 'signed'" class="card msg">
      <h1>Awaiting sign-off</h1>
      <p>
        This report opens once a licensed reviewer has checked it and signed it. Created {{ report.created_at.slice(0, 10) }}. Ask the person who
        sent you the link to check again later.
      </p>
    </div>
    <template v-else>
      <div class="actions no-print">
        <button type="button" class="btn btn-secondary" @click="print">Print or save as PDF</button>
      </div>
      <ReportBody :report="report" />
    </template>
  </main>
</template>

<style scoped>
.wrap {
  padding: 24px 16px;
  max-width: 992px;
  margin: 0 auto;
}
.msg {
  padding: 24px;
  max-width: 640px;
  margin: 40px auto;
}
.msg h1 {
  margin-top: 0;
  font-size: 20px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}
@media print {
  .no-print {
    display: none;
  }
  .wrap {
    padding: 0;
  }
}
</style>
