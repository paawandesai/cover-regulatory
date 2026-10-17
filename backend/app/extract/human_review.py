"""Records a person's re-review of rule fragments, from the review sheet they filled in.

    python -m app.extract.human_review decisions.csv --reviewer "Paawan"

The CSV needs the sheet's "Fragment id", "Your decision" (approve, reject or edit) and "Your note" columns; rows
with no decision are left alone. Unlike `apply_review`, this decides fragments an AI review already approved or
rejected, because re-reviewing those is the point. Each decision is stored under the reviewer's name, and the
earlier status and reviewer go to the audit log. "edit" rejects the fragment and keeps the correction in the note,
for a corrected fragment to be extracted and reviewed. Approval still needs the source text to be unchanged and a
fragment that passed the deterministic checks.
"""

import argparse
import csv
from pathlib import Path

from app.api.reviewers import record
from app.db.connection import connect

DECISION = {"approve": "approved", "reject": "rejected", "edit": "rejected"}


def apply(path: Path, reviewer: str) -> dict[str, int]:
    counts = {"approved": 0, "rejected": 0, "edit": 0, "unchanged": 0, "skipped": 0}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("Your decision") or "").strip()]
    with connect() as conn:
        for r in rows:
            choice = r["Your decision"].strip().lower()
            note = (r.get("Your note") or "").strip()
            if choice not in DECISION or (choice == "edit" and not note):
                counts["skipped"] += 1
                continue
            fid = int(r["Fragment id"])
            f = conn.execute(
                """SELECT f.status, f.reviewed_by, f.chunk_hash, c.content_hash FROM rule_fragment f
                   JOIN reg_chunk c ON c.id = f.chunk_id WHERE f.id = %s FOR UPDATE""",
                (fid,),
            ).fetchone()
            decision = DECISION[choice]
            if f is None or (
                decision == "approved"
                and (f["status"] not in ("pending", "approved", "rejected") or f["chunk_hash"] != f["content_hash"])
            ):
                counts["skipped"] += 1
                continue
            if f["status"] == decision and f["reviewed_by"] == reviewer:
                counts["unchanged"] += 1
                continue
            text = f"Re-reviewed by {reviewer} (a person)."
            if choice == "edit":
                text += f" Correction: {note}"
            elif note:
                text += f" {note}"
            conn.execute(
                "UPDATE rule_fragment SET status=%s, reviewed_by=%s, reviewed_at=now(), review_note=%s WHERE id=%s",
                (decision, reviewer, text[:2000], fid),
            )
            record(
                conn,
                reviewer,
                f"fragment_{decision}",
                "rule_fragment",
                fid,
                {"from": f["status"], "from_reviewer": f["reviewed_by"], "choice": choice, "file": path.name},
            )
            counts["edit" if choice == "edit" else decision] += 1
        conn.commit()
    return counts


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path", type=Path)
    p.add_argument("--reviewer", required=True, help="the person whose decisions these are")
    a = p.parse_args()
    if a.reviewer.strip().lower() in ("ai-review", ""):
        raise SystemExit("--reviewer must name the person who reviewed")
    print(apply(a.path, a.reviewer.strip()))
