<script setup lang="ts">
import { computed } from 'vue'
import { labelText } from '../format'
import type { Label, Summary } from '../types'
import LabelBadge from './LabelBadge.vue'

const props = defineProps<{ summary: Summary }>()
const ORDER: Label[] = ['derived', 'verified', 'interpretive', 'withheld', 'approximate', 'flag', 'uncited', 'mock']
const counts = computed(() => ORDER.filter((l) => props.summary.counts[l]).map((l) => ({ label: l, n: props.summary.counts[l]! })))
</script>

<template>
  <div class="card sum">
    <span class="eyebrow">Summary</span>
    <p class="answer">{{ summary.answer }}</p>
    <p class="small">{{ summary.confidence }}</p>
    <div class="counts" :aria-label="'Values by label'">
      <span v-for="c in counts" :key="c.label" class="count">
        <LabelBadge :label="c.label" :text="`${c.n} · ${labelText(c.label)}`" />
      </span>
    </div>
    <details v-if="summary.paths.length">
      <summary class="small strong">Choices to weigh ({{ summary.paths.length }})</summary>
      <div v-for="p in summary.paths" :key="p.id" class="path">
        <span class="small strong">{{ p.title }}</span>
        <ul>
          <li v-for="o in p.options" :key="o" class="small">{{ o }}</li>
        </ul>
      </div>
    </details>
  </div>
</template>

<style scoped>
.sum {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
p {
  margin: 0;
}
.answer {
  font-size: 16px;
  line-height: 24px;
}
.counts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.strong {
  font-weight: 600;
}
summary {
  cursor: pointer;
  padding: 4px 0;
}
.path {
  margin-top: 8px;
}
ul {
  margin: 4px 0 0;
  padding-left: 20px;
}
</style>
