<script setup lang="ts">
import { computed } from 'vue'

// Shows `text` with [start, end) highlighted. With `context`, trims to that many characters either side.
const props = defineProps<{ text: string; start: number | null; end: number | null; context?: number }>()

const parts = computed(() => {
  const { text, start, end, context } = props
  if (start == null || end == null || start < 0 || end > text.length || start >= end) {
    return { before: '', quote: '', after: text, cutBefore: false, cutAfter: false }
  }
  const from = context ? Math.max(0, start - context) : 0
  const to = context ? Math.min(text.length, end + context) : text.length
  return {
    before: text.slice(from, start),
    quote: text.slice(start, end),
    after: text.slice(end, to),
    cutBefore: from > 0,
    cutAfter: to < text.length,
  }
})
</script>

<template>
  <blockquote class="source" tabindex="0" aria-label="Source text"><template v-if="parts.cutBefore">…</template>{{ parts.before }}<mark v-if="parts.quote">{{ parts.quote }}</mark>{{ parts.after }}<template v-if="parts.cutAfter">…</template></blockquote>
</template>
