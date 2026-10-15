<script setup lang="ts">
import { ref, watch } from 'vue'
import { sendFeedback } from '../api'

const props = defineProps<{ apn: string | null; itemId: string | null }>()
const open = ref(false)
const kind = ref('wrong_value')
const comment = ref('')
const state = ref<'idle' | 'sending' | 'sent' | 'error'>('idle')

watch(
  () => props.itemId,
  () => {
    open.value = false
    state.value = 'idle'
    comment.value = ''
  },
)

async function submit() {
  state.value = 'sending'
  try {
    await sendFeedback({ apn: props.apn, item_id: props.itemId, kind: kind.value, comment: comment.value || null })
    state.value = 'sent'
    open.value = false
  } catch {
    state.value = 'error'
  }
}
</script>

<template>
  <div class="fb">
    <p v-if="state === 'sent'" class="small" role="status">
      Thanks. This is queued for a reviewer; it doesn't change any value by itself.
    </p>
    <button v-else-if="!open" type="button" class="btn btn-secondary" @click="open = true">
      Report a problem with this value
    </button>
    <form v-else class="form" @submit.prevent="submit">
      <label class="small" for="fb-kind">What's wrong?</label>
      <select id="fb-kind" v-model="kind" class="field">
        <option value="wrong_value">The value is wrong</option>
        <option value="bad_citation">The citation doesn't support it</option>
        <option value="missing_rule">A rule that applies is missing</option>
        <option value="other">Something else</option>
      </select>
      <label class="small" for="fb-comment">Details (optional; please leave out names and addresses)</label>
      <textarea id="fb-comment" v-model="comment" class="field" rows="3" maxlength="2000" />
      <div class="row">
        <button type="submit" class="btn btn-primary" :disabled="state === 'sending'">Send</button>
        <button type="button" class="btn btn-secondary" @click="open = false">Cancel</button>
      </div>
      <p v-if="state === 'error'" class="small err" role="alert">Couldn't send that. Try again.</p>
    </form>
  </div>
</template>

<style scoped>
.form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.row {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
.err {
  color: var(--danger);
}
p {
  margin: 0;
}
</style>
