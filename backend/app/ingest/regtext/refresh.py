"""Scheduled source check: re-fetch each downloadable regulation document and act on any change.

For a `fetch: url` document the file is downloaded again and compared by SHA-256. When it changed, it is
re-ingested and every decided rule fragment whose chunk text changed is sent back to review:
- if its quote is still verbatim in the new text, it becomes 'pending' (the engine then shows Interpretation);
- otherwise it is retired as 'invalid' / 'stale_chunk' (the engine then shows no cited value).
Each of these is written to the audit log as 'source-refresh'. Hand-saved (`fetch: manual`) documents are never
fetched; they are reported as due for a hand re-check once older than MANUAL_RECHECK_DAYS.

Run: uv run python -m app.ingest.regtext.refresh      (the hosted demo runs it weekly)
"""

import hashlib
import json
import os
import sys
from datetime import UTC, datetime

import httpx

from app.api.reviewers import record
from app.db.connection import connect
from app.extract.validate import locate_quote
from app.ingest.regtext import ingest as I

ACTOR = "source-refresh"
MANUAL_RECHECK_DAYS = int(os.environ.get("MANUAL_RECHECK_DAYS", "90"))


def _download(doc: dict) -> bytes:
    if any(h in doc["url"] for h in I.NEVER_FETCH):
        raise ValueError("automated fetch from this host is not allowed")
    return I.fetch_allowed(doc["url"]).content


def send_back_to_review(conn, document_id: str) -> dict:
    """Decided fragments of this document whose chunk text changed: approved ones go back to pending if the quote
    survived; rejected ones stay rejected (the engine reads pending values, so a text change must never bring back a
    value a reviewer turned down). Either is retired if its quote is gone."""
    rows = conn.execute(
        """SELECT f.id, f.status, f.source_quote, c.text, c.content_hash FROM rule_fragment f
           JOIN reg_chunk c ON c.id = f.chunk_id
           WHERE c.document_id = %s AND f.status IN ('approved', 'rejected') AND f.chunk_hash <> c.content_hash
           FOR UPDATE OF f""",
        (document_id,),
    ).fetchall()
    out = {"to_pending": 0, "retired": 0, "kept_rejected": 0}
    for r in rows:
        span = locate_quote(r["source_quote"], r["text"])
        note = f"Source text changed on {datetime.now(UTC).date()}; was {r['status']}."
        if span and r["status"] == "rejected":
            conn.execute(
                """UPDATE rule_fragment SET chunk_hash = %s, quote_start = %s, quote_end = %s,
                       review_note = left(coalesce(review_note || ' ', '') || %s, 2000) WHERE id = %s""",
                (r["content_hash"], span[0], span[1], note + " Quote still present; stays rejected.", r["id"]),
            )
            out["kept_rejected"] += 1
        elif span:
            conn.execute(
                """UPDATE rule_fragment SET status = 'pending', chunk_hash = %s, quote_start = %s, quote_end = %s,
                       review_note = left(coalesce(review_note || ' ', '') || %s, 2000) WHERE id = %s""",
                (r["content_hash"], span[0], span[1], note + " Quote still present; needs a new review.", r["id"]),
            )
            record(conn, ACTOR, "fragment_to_pending", "rule_fragment", r["id"], {"was": r["status"]})
            out["to_pending"] += 1
        else:
            conn.execute(
                """UPDATE rule_fragment SET status = 'invalid', validation = 'stale_chunk',
                       review_note = left(coalesce(review_note || ' ', '') || %s, 2000) WHERE id = %s""",
                (note + " Quote no longer in the text; retired.", r["id"]),
            )
            record(conn, ACTOR, "fragment_retired", "rule_fragment", r["id"], {"was": r["status"]})
            out["retired"] += 1
    return out


def check_document(doc: dict) -> tuple[str, dict]:
    with connect() as conn:
        row = conn.execute("SELECT file_sha256, retrieved_at FROM reg_document WHERE id = %s", (doc["id"],)).fetchone()
    if doc["fetch"] == "manual":
        if row is None:
            return "manual_due", {"reason": "never loaded"}
        age = (datetime.now(UTC) - row["retrieved_at"]).days
        return ("manual_due" if age >= MANUAL_RECHECK_DAYS else "manual_ok"), {"age_days": age}
    try:
        data = _download(doc)
    except (httpx.HTTPError, ValueError) as e:
        return "failed", {"error": type(e).__name__}
    sha = hashlib.sha256(data).hexdigest()
    if row is not None and row["file_sha256"] == sha:
        return "unchanged", {}
    with connect() as conn:
        decided = conn.execute(
            """SELECT count(*) AS n FROM rule_fragment f JOIN reg_chunk c ON c.id = f.chunk_id
               WHERE c.document_id = %s AND f.status IN ('approved', 'rejected')""",
            (doc["id"],),
        ).fetchone()["n"]
    I.RAW.mkdir(parents=True, exist_ok=True)
    (I.RAW / f"{doc['id']}.pdf").write_bytes(data)
    result = I.ingest(doc) or {}
    with connect() as conn:
        review = send_back_to_review(conn, doc["id"])
        still = conn.execute(
            """SELECT count(*) AS n FROM rule_fragment f JOIN reg_chunk c ON c.id = f.chunk_id
               WHERE c.document_id = %s AND f.status IN ('approved', 'rejected')""",
            (doc["id"],),
        ).fetchone()["n"]
        conn.commit()
    # Fragments on removed chunks are deleted with them; count them so the alert says so.
    lost = decided - still - review["to_pending"] - review["retired"]
    return "changed", {**{k: result.get(k) for k in ("added", "changed", "removed")}, **review, "decided_lost": lost}


def refresh(docs: list[dict] | None = None) -> list[dict]:
    out = []
    for doc in docs if docs is not None else I.load_registry():
        outcome, detail = check_document(doc)
        with connect() as conn:
            conn.execute(
                "INSERT INTO source_check (document_id, outcome, detail) VALUES (%s, %s, %s)",
                (doc["id"], outcome, json.dumps(detail)),
            )
            conn.commit()
        out.append({"doc": doc["id"], "outcome": outcome, **detail})
    if any(r["outcome"] == "changed" for r in out):
        from app.search.index import run as embed

        embed()
    return out


if __name__ == "__main__":
    results = refresh()
    for r in results:
        print(json.dumps(r))
    sys.exit(0)
