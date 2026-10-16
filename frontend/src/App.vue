<script setup lang="ts">
import { ref } from 'vue'
import { ApiError, checkInvite, invite, submitInvite } from './api'

const code = ref('')
const error = ref<string | null>(null)
checkInvite().catch(() => Object.assign(invite, { checked: true }))

async function send() {
  error.value = null
  try {
    await submitInvite(code.value)
    location.reload()
  } catch (e) {
    error.value =
      e instanceof ApiError && e.status === 403
        ? "That code didn't work."
        : e instanceof ApiError && e.status === 429
          ? 'Too many tries. Wait 15 minutes and try again.'
          : 'Could not reach the server.'
  }
}
</script>

<template>
  <div v-if="invite.required" class="demo small">Hosted demo with public data only. Please don't enter personal information.</div>
  <main v-if="invite.needed" class="gate">
    <form class="card" @submit.prevent="send">
      <h1>Regulatory Engine demo</h1>
      <p class="small muted">This demo is invite-only. Enter the code you were given.</p>
      <label for="invite" class="small">Invite code</label>
      <input id="invite" v-model="code" class="field" autocomplete="off" required maxlength="200" />
      <button type="submit" class="btn btn-primary">Continue</button>
      <p v-if="error" class="small err" role="alert">{{ error }}</p>
    </form>
  </main>
  <RouterView v-else-if="invite.checked" />
</template>

<style scoped>
.demo {
  background: var(--ink);
  color: #fff;
  padding: 6px 24px;
  text-align: center;
}
.gate {
  min-height: 80vh;
  display: grid;
  place-items: center;
  padding: 24px;
}
form {
  width: min(400px, 100%);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
h1 {
  margin: 0;
  font-size: 18px;
  line-height: 24px;
}
p {
  margin: 0;
}
.err {
  color: var(--danger);
}
</style>
