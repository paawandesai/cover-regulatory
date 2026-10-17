"""Writes the API responses the browser tests replay (frontend/e2e/fixtures/), from the local database.

    cd backend && .venv/bin/python ../scripts/e2e-fixtures.py

Parcels are identified by APN only, as in the golden cases. Regulation chunks are cut down to the quotes the
assessment already cites, so no hand-saved code text beyond those quotes is committed.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "frontend" / "e2e" / "fixtures"
APNS = ["2121005008", "4142004002", "4144001800", "4327028024"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    c = TestClient(app)
    chunks: dict[str, dict] = {}
    for apn in APNS:
        r = c.get("/api/assess", params={"q": apn})
        r.raise_for_status()
        body = r.json()
        body["generated_at"] = "2026-10-17T00:00:00Z"
        (OUT / f"assess-{apn}.json").write_text(json.dumps(body, indent=1, sort_keys=True) + "\n")
        n = c.get(f"/api/parcels/{apn}/nearby")
        if n.status_code == 200:
            (OUT / f"nearby-{apn}.json").write_text(json.dumps(n.json(), sort_keys=True) + "\n")
        for item in body["items"] + body["parcel"]["items"]:
            for cit in item.get("citations") or []:
                cid = cit.get("chunk_id")
                if not cid:
                    continue
                full = c.get(f"/api/chunks/{cid}").json()
                quotes = chunks.get(cid, {}).get("_quotes", [])
                quotes.append(cit.get("quote") or "")
                chunks[cid] = full | {"_quotes": quotes}
    out = {}
    for cid, ch in chunks.items():
        quotes = [q for q in dict.fromkeys(ch.pop("_quotes")) if q]
        ch["text"] = "\n\n".join(quotes) or "(fixture)"
        out[cid] = ch
    (OUT / "chunks.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(f"wrote {len(APNS)} assessments and {len(out)} chunks to {OUT}")


if __name__ == "__main__":
    main()
