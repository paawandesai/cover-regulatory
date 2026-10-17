"""Applies the verification recommendations as review decisions, for when the project owner asks for that.

    python -m app.extract.apply_review data/verification/2026-10-15.json --instructed-by "Paawan"

Every decision is recorded as an AI review under the owner's instruction, never as a person's approval. The same
rules as the review screen apply: only pending fragments are decided, and only while their source text is unchanged.
"""

import argparse
import json
from pathlib import Path

from app.api.reviewers import record
from app.db.connection import connect

REVIEWER = "ai-review"
DECISION = {"approve": "approved", "approve_with_note": "approved", "reject": "rejected"}


def apply(path: Path, instructed_by: str) -> dict[str, int]:
    data = json.loads(path.read_text())
    counts = {"approved": 0, "rejected": 0, "skipped": 0}
    with connect() as conn:
        for c in data["candidates"]:
            f = conn.execute(
                """SELECT f.status, f.chunk_hash, c.content_hash FROM rule_fragment f
                   JOIN reg_chunk c ON c.id = f.chunk_id
                   WHERE f.id = %s AND f.chunk_id = %s AND f.parameter = %s FOR UPDATE""",
                (c["fragment_id"], c["chunk_id"], c["parameter"]),
            ).fetchone()
            if f is None or f["status"] != "pending" or f["chunk_hash"] != f["content_hash"]:
                counts["skipped"] += 1
                continue
            decision = DECISION[c["recommendation"]]
            note = (
                f"AI-reviewed from the {data['checked_on']} three-way verification, applied on "
                f"{instructed_by}'s instruction."
            )
            if c.get("note"):
                note += " " + c["note"]
            conn.execute(
                "UPDATE rule_fragment SET status=%s, reviewed_by=%s, reviewed_at=now(), review_note=%s WHERE id=%s",
                (decision, REVIEWER, note[:2000], c["fragment_id"]),
            )
            record(
                conn,
                REVIEWER,
                f"fragment_{decision}",
                "rule_fragment",
                c["fragment_id"],
                {"instructed_by": instructed_by, "file": path.name},
            )
            counts[decision] += 1
        conn.commit()
    return counts


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path", type=Path)
    p.add_argument("--instructed-by", required=True)
    a = p.parse_args()
    print(apply(a.path, a.instructed_by))
