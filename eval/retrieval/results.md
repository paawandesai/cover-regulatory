# Retrieval results

Measured 2026-10-15 on this machine (4 CPU cores, no GPU), 32 questions in `questions.yaml`, corpus of
2,817 chunks. Run with `uv run python -m app.search.evaluate --k 5 --mode <mode>` from `backend/`.
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

A re-run of the default mode on 2026-10-16 gave the same recall@5 and MRR, with p50 52 ms and p95 114 ms (the README
quotes this run).

What this does and does not show:
- The question set is small and was written by the same author (Claude Code) who wrote the search code, and
  the fusion weight was chosen on it. There is no holdout, so these numbers are a sanity check, not a
  validated accuracy figure.
- Full text did not help on this set at any weight tried, so it is off by default and used only when no
  embeddings exist. That differs from the plan (decision D15 called for fusion) and is recorded here.
- Misses cluster on questions whose best answer is spread across ZA Memo 143 sections and state law. Those
  are the questions where the assessment uses approved rules rather than search.

## Holdout set (2026-10-16)

`holdout.yaml` has 50 questions written by Claude Sonnet 5.5 (`app/search/write_questions.py`). Each was written
from one randomly sampled chunk (seed 20261016, at most 6 chunks per document), and the writer saw only that
chunk: not the search code, not `questions.yaml`. The label is the source chunk's section. Nothing in search was
changed after these numbers were taken. Corpus: 2,906 chunks.

| Set | Mode | recall@5 | recall@10 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| Dev (`questions.yaml`, 32) | Default | 0.812 | | 0.642 | | |
| **Holdout** (50) | Default (embedding + section-id lookup) | **0.56** | 0.60 | 0.441 | 108 | 157 |
| Holdout (50) | Full text only | 0.12 | 0.20 | 0.070 | 50 | 84 |

What this shows:
- Search is clearly weaker on questions it was not tuned on: recall@5 falls from 0.81 to 0.56. The dev number
  overstates accuracy.
- 16 of the 22 misses are Government Code questions (29 of the 50 are). In 7 of them the top result is ZA Memo 143
  section IV, the City's summary of the same state ADU law, which may well answer the question; the single-label
  scoring counts that as a miss, so 0.56 is a lower bound.
- Full text alone is much worse on natural questions (0.12), which supports keeping it off by default.
- The assessment does not depend on search: values come from reviewed rules. Search feeds the source panel's
  related text and the follow-up chat, which only keeps sentences whose quotes it can find, so a retrieval miss
  there gives "does not answer this" rather than a wrong answer.
- The questions are model-written, not written by a person. A person-written set is still the stronger test.

## Re-measured with the County text (2026-10-17)

Wave 9 added 247 chunks of LA County Title 22 (corpus now 3,694 chunks). Search now takes a jurisdiction:
`city` leaves out Title 22, `county` keeps Title 22 and state law. The follow-up chat uses the parcel's own.

| Set | Scope | recall@5 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|
| Dev (32) | All text | 0.75 | 0.595 | 46 | 117 |
| Dev (32) | City | 0.75 | 0.595 | 50 | 117 |
| Holdout (50) | All text | 0.54 | 0.421 | 110 | 177 |
| Holdout (50) | City | 0.54 | 0.421 | 113 | 163 |

What this shows:
- The County text does not change City results: the numbers with and without it are the same.
- Both sets are lower than on 2026-10-16 (dev 0.81, holdout 0.56). Leaving Title 22 out does not bring them back,
  so the drop came with the City documents added in waves 2 to 7 (Chapter 1A, the fire orders, the specific plan
  and more state law). Which documents cause each miss was not traced. Nothing in search was tuned on the holdout.
- There is no County question set yet.
