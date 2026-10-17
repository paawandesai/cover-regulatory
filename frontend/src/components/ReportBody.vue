<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import { authority, authorityOf, formatApn, formatDate, formatValue } from '../format'
import type { Assessment, Item, Report } from '../types'
import LabelBadge from './LabelBadge.vue'

// The printable body of a client report: the frozen assessment, each value with its label and sources.
const props = defineProps<{ report: Report }>()
const a = computed(() => props.report.snapshot as Assessment)
// Data credits the licences require (ODbL for the outlines behind footprint-based values, CC BY for City limits).
const credits = computed(() => {
  const seen = new Set<string>(['City limits: City of Los Angeles, Bureau of Engineering (CC BY 4.0)'])
  for (const i of [...(a.value.parcel?.items ?? []), ...(a.value.items ?? [])]) if (i.source?.attribution) seen.add(i.source.attribution)
  return [...seen]
})
watchEffect(() => (authority.value = authorityOf(a.value)))

const SECTIONS: [string, string[]][] = [
  ['Zone envelope', ['r1_envelope', 'r2_envelope', 're_envelope', 'county_r1_envelope']],
  ['What can be built', ['guest_house', 'adu', 'jadu']],
  ['SB 9', ['sb9']],
  ['Specific plan', ['plan']],
  ['Fire rebuild', ['rebuild']],
  ['Conditions flagged, not evaluated', ['flag']],
]
const groups = computed(() =>
  SECTIONS.map(([title, fams]) => ({ title, rows: a.value.items.filter((i) => fams.includes(i.family)) })).filter((g) => g.rows.length),
)
const parcel = (id: string) => a.value.parcel.items.find((i) => i.id === id)
const sections = (i: Item) => [...new Map(i.citations.map((c) => [c.section_id, c])).values()]
</script>

<template>
  <article class="report">
    <header class="head">
      <div>
        <p class="eyebrow">Buildability assessment</p>
        <h1>APN {{ formatApn(a.parcel.apn) }}</h1>
        <p class="small muted">
          Zone {{ parcel('zone')?.value ?? 'not recorded' }} · Lot {{ parcel('lot_area') ? formatValue(parcel('lot_area')!) : 'not recorded' }} ·
          Assessed {{ formatDate(a.generated_at) }}
        </p>
      </div>
      <div v-if="report.signed" class="sig">
        <p class="eyebrow">Reviewed and signed</p>
        <p class="strong">{{ report.signed.name }}</p>
        <p class="small">{{ report.signed.license }}</p>
        <p class="small muted">{{ formatDate(report.signed.at) }}</p>
      </div>
      <div v-else class="sig unsigned">
        <p class="eyebrow">Not signed</p>
        <p class="small">A licensed reviewer has not signed this report. It is not for the client yet.</p>
      </div>
    </header>

    <section v-if="a.summary">
      <h2>Summary</h2>
      <p>{{ a.summary.answer }}</p>
      <p class="small muted">{{ a.summary.confidence }}</p>
    </section>

    <section v-if="a.project?.checks?.length">
      <h2>The project checked</h2>
      <ul class="plain">
        <li v-for="c in a.project.checks" :key="c.id">
          <span class="strong">{{ c.title }}:</span> {{ c.detail }}
        </li>
      </ul>
    </section>

    <section v-for="g in groups" :key="g.title">
      <h2>{{ g.title }}</h2>
      <table>
        <tbody>
          <tr v-for="i in g.rows" :key="i.id">
            <th scope="row">
              {{ i.title }}
              <span v-if="i.explanation" class="small muted expl">{{ i.explanation }}</span>
            </th>
            <td class="val">{{ formatValue(i) }}</td>
            <td>
              <LabelBadge :label="i.label" />
              <span v-for="c in sections(i)" :key="c.section_id" class="small cite">
                <a v-if="c.source_url" :href="c.source_url" target="_blank" rel="noopener">{{ c.section_id }}</a>
                <template v-else>{{ c.section_id }}</template>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="report.signed?.note">
      <h2>Reviewer's note</h2>
      <p>{{ report.signed.note }}</p>
    </section>

    <footer class="small muted">
      <p v-if="report.statement && report.signed">Sign-off statement: "{{ report.statement }}"</p>
      <p>{{ a.ai_disclosure }}</p>
      <p v-for="d in a.disclaimers" :key="d">{{ d }}</p>
      <p>Data: {{ credits.join('; ') }}.</p>
      <p>
        Labels: "Derived from rule" is computed from reviewed regulation text; "Interpretation" needs confirming with the {{ authority }}; "Approximate"
        rests on map outlines; "Flag" is detected, not evaluated. The assessment is as of the date above; regulations and data may have changed
        since.
      </p>
    </footer>
  </article>
</template>

<style scoped>
.report {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 24px;
  max-width: 960px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--line);
  padding-bottom: 16px;
}
h1 {
  margin: 4px 0;
  font-size: 24px;
}
h2 {
  font-size: 16px;
  margin: 24px 0 8px;
}
.eyebrow {
  margin: 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ink-muted);
}
.sig {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 8px 12px;
  min-width: 200px;
}
.sig p {
  margin: 2px 0;
}
.unsigned {
  border-color: var(--danger);
  color: var(--danger);
}
.strong {
  font-weight: 600;
}
.plain {
  margin: 0;
  padding-left: 20px;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  text-align: left;
  vertical-align: top;
  padding: 8px 8px 8px 0;
  border-bottom: 1px solid var(--line);
}
th {
  font-weight: 600;
  width: 55%;
}
.expl {
  display: block;
  font-weight: 400;
  margin-top: 2px;
}
.val {
  white-space: nowrap;
  width: 15%;
}
.cite {
  display: block;
  margin-top: 4px;
  font-family: var(--font-mono);
}
footer {
  margin-top: 24px;
  border-top: 1px solid var(--line);
}
@media print {
  .report {
    border: 0;
    padding: 0;
    max-width: none;
  }
  a {
    color: inherit;
  }
}
@media (max-width: 640px) {
  .report {
    padding: 16px;
  }
  th {
    width: auto;
  }
  .val {
    white-space: normal;
  }
}
</style>
