# Assessment latency

Written by `python -m app.engine.benchmark`; re-run it to reproduce.

Measured 2026-10-18 16:58Z on x86_64 with 4 CPUs, 18 golden parcels with status ok, 10 runs each, after one warm-up call per parcel.

| Operation | Runs | p50 | p95 |
|---|---|---|---|
| `assess()` in process | 180 | 417 ms | 601 ms |
| GET /api/assess over HTTP | 180 | 419 ms | 601 ms |
