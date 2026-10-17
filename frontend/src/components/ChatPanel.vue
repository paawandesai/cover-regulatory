<script setup lang="ts">
import { ref, watch } from 'vue'
import { ApiError, askChat } from '../api'
import { authority } from '../format'
import type { ChatAnswer, Item } from '../types'

// A follow-up question about this parcel. The server answers only with sentences whose quotes it found in the
// regulation text, or whose values come from this assessment; it never sends the APN or address to the model.
const props = defineProps<{ apn: string; items: Item[] }>()
const question = ref('')
const answer = ref<ChatAnswer | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)
watch(
  () => props.apn,
  () => ((answer.value = null), (question.value = '')),
)
const title = (id: string) => props.items.find((i) => i.id === id)?.title ?? id

async function ask() {
  if (question.value.trim().length < 3) return
  busy.value = true
  error.value = null
  try {
    answer.value = await askChat(props.apn, question.value.trim())
  } catch (e) {
    const s = e instanceof ApiError ? e.status : 0
    error.value =
      s === 503
        ? 'Follow-up questions are turned off on this server.'
        : s === 429
          ? 'Too many questions this hour. Try again later.'
          : "Couldn't answer."
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="card chat">
    <div class="ghead">
      <h2>Ask a follow-up</h2>
      <span class="small muted">Answered only from the cited regulation text</span>
    </div>
    <form class="body" @submit.prevent="ask">
      <label for="chatq" class="sr-only">Question</label>
      <textarea
        id="chatq"
        v-model="question"
        class="field"
        rows="2"
        maxlength="500"
        placeholder="e.g. Can the guest house have a kitchen?"
      />
      <button type="submit" class="btn btn-secondary" :disabled="busy || question.trim().length < 3">
        {{ busy ? 'Checking…' : 'Ask' }}
      </button>
      <p v-if="error" class="small err" role="alert">{{ error }}</p>
      <div v-if="answer" class="ans" aria-live="polite">
        <p v-if="answer.answer">{{ answer.answer }}</p>
        <div v-for="(s, n) in answer.sentences" :key="n" class="sent">
          <p>{{ s.text }}</p>
          <blockquote v-for="c in s.citations" :key="c.chunk_id + c.quote" class="small">
            "{{ c.quote }}"
            <a v-if="c.source_url" :href="c.source_url" target="_blank" rel="noopener" class="mono">{{ c.section_id }}</a>
            <span v-else class="mono">{{ c.section_id }}</span>
          </blockquote>
          <p v-if="s.items.length" class="small muted">From this assessment: {{ s.items.map(title).join(', ') }}</p>
        </div>
        <p class="small muted">
          {{ answer.disclosure }}<template v-if="answer.dropped"> {{ answer.dropped }} removed.</template> Interpretation, confirm with the
          {{ authority }}.
        </p>
      </div>
    </form>
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
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}
.field {
  width: 100%;
}
.ans {
  width: 100%;
}
.ans p {
  margin: 0 0 6px;
}
.sent {
  margin-bottom: 12px;
}
blockquote {
  margin: 4px 0 4px 0;
  padding-left: 10px;
  border-left: 3px solid var(--line);
}
blockquote a,
blockquote span {
  margin-left: 6px;
}
.err {
  color: var(--danger);
}
</style>
