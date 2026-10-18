"""Writes the API responses the browser tests replay (frontend/e2e/fixtures/), from the local database.

    cd backend && .venv/bin/python ../scripts/e2e-fixtures.py

Parcels are identified by APN only, as in the golden cases. Regulation chunks are cut down to the quotes the
assessment already cites. Text from the two publisher copies (LAMC Chapter I from American Legal Publishing's viewer
and the Title 22 copy sourced from Municode) is never committed: their quotes are replaced by synthetic placeholders,
and the citations' offsets point at those placeholders.
"""

import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "frontend" / "e2e" / "fixtures"
APNS = ["2121005008", "4142004002", "4144001800", "4327028024"]
# Documents read from publisher sites whose terms bar reuse (README "Known constraints"): fixtures carry no text of them.
PUBLISHER_DOCS = ("lamc_chapter1#", "lacounty_title22#")


def _citations(x):
    if isinstance(x, dict):
        if "chunk_id" in x and "quote" in x:
            yield x
        for v in x.values():
            yield from _citations(v)
    elif isinstance(x, list):
        for v in x:
            yield from _citations(v)


def synthetic_publisher_text(bodies: list[dict], chunks: dict[str, dict]) -> None:
    """Replace publisher text with placeholders, in the chunks and in every citation that quotes them."""
    placeholder: dict[tuple[str, str], tuple[str, int, int]] = {}
    for cid in [c for c in chunks if c.startswith(PUBLISHER_DOCS)]:
        sec = cid.split("#")[1]
        text = f"Synthetic test text standing in for {sec}; it is not the code's wording."
        quotes = dict.fromkeys(c["quote"] for b in bodies for c in _citations(b) if c["chunk_id"] == cid)
        for n, q in enumerate(quotes, 1):
            s = f"Placeholder quote {n} for {sec}."
            placeholder[(cid, q)] = (s, len(text) + 1, len(text) + 1 + len(s))
            text += " " + s
        chunks[cid]["text"] = text
    for b in bodies:
        for c in _citations(b):
            if (c["chunk_id"], c["quote"]) in placeholder:
                c["quote"], c["quote_start"], c["quote_end"] = placeholder[(c["chunk_id"], c["quote"])]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    c = TestClient(app)
    chunks: dict[str, dict] = {}
    bodies: dict[str, dict] = {}
    for apn in APNS:
        r = c.get("/api/assess", params={"q": apn})
        r.raise_for_status()
        body = bodies[apn] = r.json()
        body["generated_at"] = "2026-10-17T00:00:00Z"
        n = c.get(f"/api/parcels/{apn}/nearby")
        if n.status_code == 200:
            (OUT / f"nearby-{apn}.json").write_text(json.dumps(n.json(), sort_keys=True) + "\n")
        for item in body["items"] + body["parcel"]["items"]:
            for cit in item.get("citations") or []:
                cid = cit.get("chunk_id")
                if not cid:
                    continue
                # Chunk ids contain "#", so they must be encoded as the app does (encodeURIComponent).
                full = c.get(f"/api/chunks/{urllib.parse.quote(cid, safe='')}").json()
                quotes = chunks.get(cid, {}).get("_quotes", [])
                quotes.append(cit.get("quote") or "")
                chunks[cid] = full | {"_quotes": quotes}
    out = {}
    for cid, ch in chunks.items():
        quotes = [q for q in dict.fromkeys(ch.pop("_quotes")) if q]
        ch["text"] = "\n\n".join(quotes) or "(fixture)"
        out[cid] = ch
    synthetic_publisher_text(list(bodies.values()), out)
    for apn, body in bodies.items():
        (OUT / f"assess-{apn}.json").write_text(json.dumps(body, indent=1, sort_keys=True) + "\n")
    (OUT / "chunks.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(f"wrote {len(APNS)} assessments and {len(out)} chunks to {OUT}")


if __name__ == "__main__":
    main()
