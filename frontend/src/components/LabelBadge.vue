<script setup lang="ts">
import { LABEL_TEXT } from '../format'
import type { Label } from '../types'

defineProps<{ label: Label; text?: string }>()
</script>

<template>
  <span class="badge" :class="label">{{ text ?? LABEL_TEXT[label] }}</span>
</template>

<style scoped>
.badge {
  white-space: nowrap;
  font-size: 12px;
  line-height: 16px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid;
  background: var(--surface);
}
.verified {
  color: var(--success);
  border-color: var(--success);
}
.derived {
  color: var(--ink);
  border-color: var(--line-strong);
}
.interpretive {
  color: var(--accent-hover);
  border-color: var(--accent-subtle);
  background: var(--accent-subtle);
}
.uncited,
.mock {
  color: var(--danger);
  border-color: var(--danger);
}
.withheld,
.approximate {
  color: var(--ink-muted);
  border-color: var(--line-strong);
  border-style: dashed;
}
</style>
