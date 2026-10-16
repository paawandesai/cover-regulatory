<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ApiError, clearCredentials, decide, fragments, hasCredentials, setCredentials } from '../api'
import AppHeader from '../components/AppHeader.vue'
import FeedbackList from '../components/FeedbackList.vue'
import QuoteInContext from '../components/QuoteInContext.vue'
import type { Fragment } from '../types'

type Status = Fragment['status']
const TABS: [Status, string][] = [
  ['pending', 'Waiting for review'],
  ['invalid', 'Failed checks'],
  ['approved', 'Approved'],
  ['rejected', 'Rejected'],
]

const VALIDATION: Record<string, string> = {
  ok: 'Quote check passed',
  unknown_chunk_id: 'Cited text not found',
  quote_not_in_chunk: 'Quote not in the source',
  unknown_parameter: 'Unknown parameter',
  value_not_in_quote: 'Number not in quote',
  unit_mismatch: 'Unit mismatch',
  no_value: 'No value',
  numeric_value_for_non_numeric_parameter: 'Number where text expected',
  stale_chunk: 'Source text changed',
}

// Advisory results of the three-way check (source text, a second model, official sources). Only a review decision changes a status.
const CHECK: Record<NonNullable<Fragment['check_recommendation']>, string> = {
  approve: 'Checks suggest approve',
  approve_with_note: 'Checks suggest approve, with a note',
  reject: 'Checks suggest reject',
}
const VERDICT: Record<string, string> = {
  agree: 'agrees',
  agree_with_caveat: 'agrees, with a caveat',
  disagree: 'disagrees',
}

const signedIn = ref(hasCredentials())
const user = ref('')
const password = ref('')
const authError = ref<string | null>(null)
const tab = ref<Status>('pending')
const mode = ref<'rules' | 'feedback'>('rules')
const family = ref('')
const advice = ref('')
const lists = ref<Record<Status, Fragment[]>>({
  pending: [],
  invalid: [],
  approved: [],
  rejected: [],
})
const pickedId = ref<number | null>(null)
const note = ref('')
const busy = ref(false)
const actionError = ref<string | null>(null)

async function loadAll() {
  const out = { ...lists.value }
  await Promise.all(TABS.map(async ([s]) => (out[s] = await fragments(s))))
  lists.value = out
}

async function signIn() {
  authError.value = null
  setCredentials(user.value, password.value)
  password.value = ''
  try {
    await loadAll()
    signedIn.value = true
  } catch (e) {
    clearCredentials()
    authError.value =
      e instanceof ApiError && e.status === 503
        ? "Admin sign-in isn't set up on the server. Set ADMIN_USERNAME and ADMIN_PASSWORD_SCRYPT."
        : e instanceof ApiError && e.status === 401
          ? 'Wrong username or password.'
          : 'Could not reach the server.'
  }
}

function signOut() {
  clearCredentials()
  signedIn.value = false
  lists.value = { pending: [], invalid: [], approved: [], rejected: [] }
}

if (signedIn.value) loadAll().catch(signOut)

const families = computed(() =>
  [
    ...new Set(
      Object.values(lists.value)
        .flat()
        .map((f) => f.rule_family),
    ),
  ].sort(),
)
const list = computed(() =>
  lists.value[tab.value].filter(
    (f) => (!family.value || f.rule_family === family.value) && (!advice.value || f.check_recommendation === advice.value),
  ),
)
const selected = computed(() => list.value.find((f) => f.id === pickedId.value) ?? list.value[0] ?? null)

watch([tab, family, advice], () => {
  pickedId.value = null
})
watch(selected, () => {
  note.value = ''
  actionError.value = null
})

const value = (f: Fragment) =>
  f.value_numeric != null ? `${f.value_numeric}${f.unit ? ` ${f.unit === 'sqft' ? 'sq ft' : f.unit}` : ''}` : (f.value_text ?? '—')

const short = (t: string, n = 70) => (t.length > n ? t.slice(0, n - 1) + '…' : t)

// applies_to / conditions may arrive as a JSON array string.
const listText = (v: string | string[] | null) => {
  if (!v) return null
  if (Array.isArray(v)) return v.join(', ')
  try {
    const a = JSON.parse(v)
    if (Array.isArray(a)) return a.join(', ')
  } catch {
    /* plain text */
  }
  return v
}

async function act(decision: 'approved' | 'rejected') {
  const f = selected.value
  if (!f) return
  busy.value = true
  actionError.value = null
  try {
    await decide(f.id, decision, note.value || null)
    const i = list.value.indexOf(f)
    const next = list.value[i + 1] ?? list.value[i - 1] ?? null
    lists.value[f.status] = lists.value[f.status].filter((x) => x.id !== f.id)
    lists.value[decision] = [...lists.value[decision], { ...f, status: decision, review_note: note.value || null }]
    pickedId.value = next?.id ?? null
  } catch (e) {
    actionError.value = e instanceof ApiError ? e.message : 'Could not save the decision.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <AppHeader title="Rule review" :subtitle="signedIn ? 'Admin · signed in' : 'Admin'">
      <span class="spacer" />
      <button v-if="signedIn" type="button" class="link small" @click="signOut">Sign out</button>
      <RouterLink to="/" class="small">Back to assessment</RouterLink>
    </AppHeader>

    <main class="page">
      <form v-if="!signedIn" class="card signin" @submit.prevent="signIn">
        <h1>Sign in to review rules</h1>
        <p class="small muted">
          Rule candidates are used in assessments only after a review approves them. In this demo the decisions were made by an AI review
          (three-way check) and are recorded as such.
        </p>
        <label for="u" class="small">Username</label>
        <input id="u" v-model="user" class="field" autocomplete="username" required />
        <label for="p" class="small">Password</label>
        <input id="p" v-model="password" class="field" type="password" autocomplete="current-password" required />
        <button type="submit" class="btn btn-primary">Sign in</button>
        <p v-if="authError" class="small err" role="alert">{{ authError }}</p>
      </form>

      <template v-else>
        <div class="bar">
          <button
            v-for="[id, name] in TABS"
            :key="id"
            type="button"
            class="tab"
            :class="{ on: mode === 'rules' && tab === id }"
            :aria-pressed="mode === 'rules' && tab === id"
            @click="((tab = id), (mode = 'rules'))"
          >
            {{ name }} <span class="mono small">{{ lists[id].length }}</span>
          </button>
          <button
            type="button"
            class="tab"
            :class="{ on: mode === 'feedback' }"
            :aria-pressed="mode === 'feedback'"
            @click="mode = 'feedback'"
          >
            Feedback
          </button>
          <template v-if="mode === 'rules'">
            <label for="fam" class="sr-only">Rule family</label>
            <select id="fam" v-model="family" class="field small">
              <option value="">All rule families</option>
              <option v-for="f in families" :key="f" :value="f">{{ f }}</option>
            </select>
            <label for="adv" class="sr-only">Check result</label>
            <select id="adv" v-model="advice" class="field small">
              <option value="">All check results</option>
              <option v-for="(label, k) in CHECK" :key="k" :value="k">
                {{ label }}
              </option>
            </select>
            <span class="spacer" />
            <span class="small muted">Pending candidates show only as Interpretation; approval makes them Derived.</span>
          </template>
        </div>

        <FeedbackList v-if="mode === 'feedback'" />
        <div v-else class="cols">
          <section aria-label="Candidate rules" class="card listcol">
            <p v-if="!list.length" class="empty small muted">Nothing here.</p>
            <button
              v-for="f in list"
              :key="f.id"
              type="button"
              class="cand"
              :class="{ on: selected?.id === f.id }"
              @click="pickedId = f.id"
            >
              <span class="top">
                <span class="mono small">{{ f.parameter }}</span>
                <span class="strong" :class="{ txt: f.value_numeric == null }">{{ short(value(f)) }}</span>
              </span>
              <span class="small muted"
                >{{ f.section_id }} · {{ VALIDATION[f.validation] ?? f.validation
                }}<template v-if="f.check_recommendation && f.check_recommendation !== 'approve'">
                  ·
                  <span :class="'chk-' + f.check_recommendation">{{
                    f.check_recommendation === 'reject' ? 'Suggest reject' : 'Note'
                  }}</span></template
                ></span
              >
            </button>
          </section>

          <section v-if="selected" aria-label="Selected rule" class="card detail">
            <div class="dhead">
              <h1 :class="{ txt: selected.value_numeric == null }">
                {{ value(selected) }}
                <span class="mono param">{{ selected.parameter }}</span>
              </h1>
              <span class="badge" :class="selected.validation === 'ok' ? 'ok' : 'bad'">
                {{ VALIDATION[selected.validation] ?? selected.validation }}
              </span>
            </div>
            <dl class="facts small">
              <div>
                <dt>Section</dt>
                <dd class="mono">{{ selected.section_id }}</dd>
              </div>
              <div>
                <dt>Applies to</dt>
                <dd>{{ listText(selected.applies_to) ?? 'Not stated' }}</dd>
              </div>
              <div>
                <dt>Read by</dt>
                <dd class="mono">{{ selected.served_model }} · {{ selected.prompt_version }}</dd>
              </div>
              <div>
                <dt>Conditions</dt>
                <dd>{{ listText(selected.conditions) || 'None stated' }}</dd>
              </div>
            </dl>
            <aside v-if="selected.check_recommendation" class="check" :class="'chk-box-' + selected.check_recommendation">
              <span class="strong" :class="'chk-' + selected.check_recommendation">{{ CHECK[selected.check_recommendation] }}</span>
              <p v-if="selected.check_note" class="small">
                {{ selected.check_note }}
              </p>
              <p v-if="selected.checks" class="small muted">
                Source text check
                {{ VERDICT[selected.checks.source_text ?? ''] ?? '—' }} · second model
                {{ VERDICT[selected.checks.second_model ?? ''] ?? '—' }} · official sources:
                {{ selected.checks.web ?? '—' }}
                <template v-if="selected.checked_on"> · checked {{ selected.checked_on }}</template>
              </p>
              <p class="small muted">Advice only. Your decision is what counts.</p>
            </aside>
            <div class="stack">
              <span class="eyebrow">Full section text, quote highlighted</span>
              <QuoteInContext :text="selected.chunk_text" :start="selected.quote_start" :end="selected.quote_end" />
              <a v-if="selected.source_url" :href="selected.source_url" class="small" target="_blank" rel="noopener noreferrer"
                >Open the source document</a
              >
            </div>
            <p v-if="selected.reviewed_by" class="small muted">
              {{ selected.status === 'approved' ? 'Approved' : 'Rejected' }} by {{ selected.reviewed_by
              }}<template v-if="selected.review_note">: {{ selected.review_note }}</template>
            </p>
            <template v-if="selected.status === 'pending' || selected.status === 'invalid'">
              <div class="stack">
                <label for="note" class="small">Note (optional)</label>
                <textarea id="note" v-model="note" rows="2" class="field" maxlength="2000" />
              </div>
              <div class="actions">
                <button type="button" class="btn btn-primary" :disabled="busy || selected.status !== 'pending'" @click="act('approved')">
                  Approve
                </button>
                <button type="button" class="btn btn-danger" :disabled="busy" @click="act('rejected')">Reject</button>
                <span class="small muted">
                  {{
                    selected.status === 'invalid'
                      ? 'This failed a deterministic check, so it can only be rejected.'
                      : 'Approve only if the value and conditions match the highlighted text. To correct a value, reject it and say why.'
                  }}
                </span>
              </div>
              <p v-if="actionError" class="small err" role="alert">
                {{ actionError }}
              </p>
            </template>
          </section>
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped>
.page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.spacer {
  flex: 1 1 auto;
}
.link {
  border: 0;
  background: none;
  color: var(--accent);
  cursor: pointer;
  font: inherit;
  text-decoration: underline;
  padding: 0;
}
.signin {
  max-width: 420px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.signin h1 {
  margin: 0;
  font-size: 18px;
  line-height: 24px;
}
.signin p {
  margin: 0 0 8px;
}
.err {
  color: var(--danger);
}
.bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.tab {
  min-height: 44px;
  padding: 0 16px;
  border-radius: var(--radius-sm);
  font: inherit;
  cursor: pointer;
  border: 1px solid var(--line-strong);
  background: var(--surface);
  color: var(--ink);
}
.tab.on {
  background: var(--ink);
  border-color: var(--ink);
  color: #fff;
}
.cols {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  align-items: flex-start;
}
.listcol {
  flex: 1 1 380px;
  max-width: 520px;
  min-width: 0;
  max-height: calc(100vh - 200px);
  overflow: auto;
}
.empty {
  padding: 16px;
  margin: 0;
}
.cand {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 16px;
  border: 0;
  border-bottom: 1px solid var(--line);
  text-align: left;
  font: inherit;
  color: inherit;
  cursor: pointer;
  background: var(--surface);
}
.cand.on {
  background: var(--accent-subtle);
}
.top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.strong {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.strong.txt {
  font-weight: 400;
  text-align: right;
}
.dhead h1.txt {
  font-size: 18px;
  line-height: 24px;
}
.detail {
  flex: 999 1 560px;
  min-width: 0;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.dhead {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  align-items: baseline;
  justify-content: space-between;
}
.dhead h1 {
  margin: 0;
  font-size: 28px;
  line-height: 34px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.param {
  font-size: 15px;
  font-weight: 400;
  color: var(--ink-muted);
}
.badge {
  font-size: 12px;
  line-height: 16px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid;
  background: var(--surface);
}
.badge.ok {
  color: var(--success);
}
.badge.bad {
  color: var(--danger);
}
.facts {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 8px 16px;
}
dt {
  color: var(--ink-muted);
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.detail p {
  margin: 0;
}
.check {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  border-left-width: 4px;
}
.chk-box-approve {
  border-left-color: var(--success);
}
.chk-box-approve_with_note {
  border-left-color: var(--accent);
}
.chk-box-reject {
  border-left-color: var(--danger);
}
.chk-approve {
  color: var(--success);
}
.chk-approve_with_note {
  color: var(--accent);
}
.chk-reject {
  color: var(--danger);
}
</style>
