"""Loads advisory verification results for rule fragments (shown to reviewers; never changes a status).

python -m app.extract.verification data/verification/2026-10-15.json
"""

import json
import sys
from pathlib import Path

from psycopg.types.json import Jsonb

from app.db.connection import connect


def load(path: Path) -> tuple[int, int]:
    data = json.loads(path.read_text())
    loaded = skipped = 0
    with connect() as conn:
        for c in data["candidates"]:
            # Fragment ids come from the database the checks ran against; skip any that now point elsewhere.
            hit = conn.execute(
                "SELECT 1 FROM rule_fragment WHERE id = %s AND chunk_id = %s AND parameter = %s",
                (c["fragment_id"], c["chunk_id"], c["parameter"]),
            ).fetchone()
            if hit is None:
                skipped += 1
                continue
            conn.execute(
                """INSERT INTO fragment_verification (fragment_id, checked_on, recommendation, note, checks)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (fragment_id) DO UPDATE SET checked_on = EXCLUDED.checked_on,
                     recommendation = EXCLUDED.recommendation, note = EXCLUDED.note, checks = EXCLUDED.checks""",
                (c["fragment_id"], data["checked_on"], c["recommendation"], c["note"], Jsonb(c["checks"])),
            )
            loaded += 1
        conn.commit()
    return loaded, skipped


if __name__ == "__main__":
    loaded, skipped = load(Path(sys.argv[1]))
    print(f"loaded {loaded}, skipped {skipped} that no longer match a fragment")
