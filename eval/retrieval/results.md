# Retrieval results

Measured 2026-10-15 on this machine (4 CPU cores, no GPU), 32 questions in `questions.yaml`, corpus of
2,804 chunks. Run with `uv run python -m app.search.evaluate --k 5 --mode <mode>` from `backend/`.
Latency is per query, end to end in Python (embedding the query plus the database queries), after one
warm-up query loads the model.

| Mode | recall@5 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|
| Embedding only (nomic-embed-text-v1.5) + section-id lookup | 0.781 | 0.631 | 50 | 67 |
| Full text only + section-id lookup | 0.594 | 0.487 | 11 | 44 |
| Fused, full-text weight 1.0 | 0.719 | 0.522 | 60 | 124 |
| Fused, full-text weight 0.5 | 0.750 | 0.567 | | |
| Fused, full-text weight 0.3 | 0.781 | 0.588 | | |
| **Default** (full-text weight 0) at k=10 | 0.812 (recall@10) | 0.636 | 51 | 91 |

What this does and does not show:
- The question set is small and was written by the same author (Claude Code) who wrote the search code, and
  the fusion weight was chosen on it. There is no holdout, so these numbers are a sanity check, not a
  validated accuracy figure.
- Full text did not help on this set at any weight tried, so it is off by default and used only when no
  embeddings exist. That differs from the plan (decision D15 called for fusion) and is recorded here.
- Misses cluster on questions whose best answer is spread across ZA Memo 143 sections and state law. Those
  are the questions where the assessment uses approved rules rather than search.
