"""Measure assessment latency over the golden parcels: in process (the engine alone) and, optionally, over HTTP.

Run: uv run python -m app.engine.benchmark [--runs 10] [--url http://localhost:8000] [--out eval/latency.md]

In process times `assess()` against the configured database after one warm-up call per parcel. With --url it also
times GET /api/assess end to end (send DEMO_INVITE_CODE in the environment to pass a demo's invite gate). Nothing is
stubbed: the database, PostGIS and the prevailing-front-yard scan all run. Results are a property of the machine.
"""

import argparse
import os
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "backend" / "tests" / "golden" / "cases.yaml"


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p * (len(xs) - 1)))]


def _row(name: str, ms: list[float]) -> str:
    return f"| {name} | {len(ms)} | {statistics.median(ms):.0f} ms | {_pct(ms, 0.95):.0f} ms |"


def in_process(apns: list[str], runs: int) -> list[float]:
    from app.engine.assess import assess

    for a in apns:
        assess(a)  # warm-up: connection, caches
    out = []
    for _ in range(runs):
        for a in apns:
            t = time.perf_counter()
            assess(a)
            out.append((time.perf_counter() - t) * 1000)
    return out


def over_http(url: str, apns: list[str], runs: int) -> list[float]:
    import httpx

    with httpx.Client(base_url=url, timeout=30) as c:
        code = os.environ.get("DEMO_INVITE_CODE")
        if code:
            c.post("/api/invite", json={"code": code}).raise_for_status()
        for a in apns:
            c.get("/api/assess", params={"q": a}).raise_for_status()
        out = []
        for _ in range(runs):
            for a in apns:
                t = time.perf_counter()
                c.get("/api/assess", params={"q": a}).raise_for_status()
                out.append((time.perf_counter() - t) * 1000)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--url")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    apns = [c["apn"] for c in yaml.safe_load(CASES.read_text())["cases"] if c["status"] == "ok"]
    lines = [
        (
            f"Measured {datetime.now(UTC):%Y-%m-%d %H:%M}Z on {platform.machine()} with {os.cpu_count()} CPUs, "
            f"{len(apns)} golden parcels with status ok, {a.runs} runs each, after one warm-up call per parcel."
        ),
        "",
        "| Operation | Runs | p50 | p95 |",
        "|---|---|---|---|",
        _row("`assess()` in process", in_process(apns, a.runs)),
    ]
    if a.url:
        lines.append(_row("GET /api/assess over HTTP", over_http(a.url, apns, a.runs)))
    text = "\n".join(lines) + "\n"
    print(text)
    if a.out:
        a.out.write_text(
            "# Assessment latency\n\nWritten by `python -m app.engine.benchmark`; re-run it to reproduce.\n\n" + text
        )


if __name__ == "__main__":
    main()
