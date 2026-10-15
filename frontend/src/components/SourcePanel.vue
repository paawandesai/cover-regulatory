<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { chunk as fetchChunk } from "../api";
import { citeLabel, formatDate, formatValue } from "../format";
import type { Chunk, Citation, Item } from "../types";
import FeedbackForm from "./FeedbackForm.vue";
import LabelBadge from "./LabelBadge.vue";
import QuoteInContext from "./QuoteInContext.vue";

const props = defineProps<{ item: Item; apn: string }>();

// Several fragments can quote the same passage; show each passage once.
const citations = computed(() => {
  const seen = new Set<string>();
  return props.item.citations.filter((c) => {
    const key = `${c.chunk_id}|${c.quote_start}|${c.quote_end}|${c.section_id}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
});
const index = ref(0);
const current = computed<Citation | undefined>(
  () => citations.value[index.value],
);
const chunk = ref<Chunk | null>(null);
const loading = ref(false);

watch(
  () => props.item.id,
  () => {
    index.value = 0;
  },
);

watch(
  current,
  async (c) => {
    chunk.value = null;
    if (!c?.chunk_id) return;
    loading.value = true;
    try {
      chunk.value = await fetchChunk(c.chunk_id);
    } catch {
      chunk.value = null;
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

const REVIEW: Record<string, string> = {
  pending: "Not yet reviewed",
  approved: "Approved by a reviewer",
  "code-cited": "Cited by code (flag)",
};

const coverage = computed(() => {
  const c = props.item.coverage;
  if (c == null) return "n/a";
  return c >= 1 ? "All found" : `${Math.round(c * 100)}% found`;
});
</script>

<template>
  <aside aria-label="Source text" class="card panel">
    <span class="eyebrow">Source text</span>
    <h2>{{ item.title }}</h2>
    <div class="meta">
      <span class="value">{{ formatValue(item) }}</span>
      <span class="mono small">{{ citeLabel(item) }}</span>
      <LabelBadge :label="item.label" />
    </div>
    <p v-if="item.explanation" class="small muted">{{ item.explanation }}</p>

    <template v-if="item.label === 'verified' && item.source">
      <p class="small">
        From the
        <span class="mono">{{ item.source.dataset ?? "derived" }}</span>
        dataset, fetched {{ formatDate(item.source.fetched_at) }}.
      </p>
    </template>

    <template v-else-if="current">
      <div
        v-if="citations.length > 1"
        class="pager"
        role="group"
        aria-label="Citations"
      >
        <button
          v-for="(c, i) in citations"
          :key="i"
          type="button"
          class="chip"
          :class="{ on: i === index }"
          :aria-pressed="i === index"
          @click="index = i"
        >
          {{ i + 1 }}. {{ c.section_id }}
        </button>
      </div>
      <QuoteInContext
        v-if="chunk"
        :text="chunk.text"
        :start="current.quote_start"
        :end="current.quote_end"
        :context="320"
      />
      <blockquote v-else-if="current.quote" class="source">
        <mark>{{ current.quote }}</mark>
      </blockquote>
      <p v-else-if="loading" class="small muted">Loading the source text…</p>
      <dl class="facts small">
        <div>
          <dt>Document</dt>
          <dd>
            {{ chunk?.document_title ?? current.section_id
            }}<template v-if="chunk?.manual_retrieval">
              (saved by hand)</template
            >
          </dd>
        </div>
        <div>
          <dt>Retrieved</dt>
          <dd class="mono">{{ formatDate(current.retrieved_at) }}</dd>
        </div>
        <div>
          <dt>Review</dt>
          <dd>
            {{
              current.review_status === "approved" &&
              current.reviewed_by === "ai-review"
                ? "Approved in an AI review (three-way check), on the project owner's instruction"
                : (REVIEW[current.review_status] ?? current.review_status)
            }}
          </dd>
        </div>
        <div>
          <dt>Inputs found</dt>
          <dd>{{ coverage }}</dd>
        </div>
      </dl>
      <a
        v-if="current.source_url"
        class="small"
        :href="current.source_url"
        target="_blank"
        rel="noopener noreferrer"
        >Open the official source</a
      >
    </template>

    <p v-else class="small muted">No regulation text supports this value.</p>

    <FeedbackForm :apn="apn" :item-id="item.id" />
  </aside>
</template>

<style scoped>
.panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
h2 {
  margin: 0;
  font-size: 18px;
  line-height: 24px;
  font-weight: 600;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
p {
  margin: 0;
}
.facts {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
}
dt {
  color: var(--ink-muted);
}
dd {
  margin: 0;
}
.pager {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  font-family: var(--font-mono);
  font-size: 12px;
  cursor: pointer;
  color: var(--ink);
}
.chip.on {
  background: var(--ink);
  border-color: var(--ink);
  color: #fff;
}
</style>
