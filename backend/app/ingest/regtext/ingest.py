"""Fetch, extract, chunk and store regulatory documents.

    uv run python -m app.ingest.regtext.ingest              # all documents available locally or by URL
    uv run python -m app.ingest.regtext.ingest za_memo_143

Re-ingestion compares each chunk's content hash with what is stored and records added / changed /
removed counts in `ingest_run`. Manual documents are skipped (with a message) until their file exists.
"""

import hashlib
import os
import re
import sys
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar

import httpx
import pdfplumber
import yaml

from app.config import get_settings
from app.db.connection import connect
from app.ingest.regtext.chunk import (
    FAQ_HEADING,
    ORDER_NUMBER,
    PLAN_SECTION,
    Chunk,
    Page,
    chunk_by_headings,
    chunk_ch1a,
    chunk_lamc,
    chunk_order,
    chunk_ordinance,
    chunk_statute,
    chunk_title22,
    indent_marker,
)

HERE = Path(__file__).parent
REPO = HERE.parents[3]
# Downloaded PDFs; the scheduled refresh in the API image points this at a writable directory.
RAW = Path(os.environ.get("REGTEXT_RAW_DIR") or REPO / "data" / "raw" / "regtext")
NEVER_FETCH = ("amlegal.com", "municode.com", "upcodes.com", "iccsafe.org", "findlaw.com")


def fetch_allowed(url: str) -> httpx.Response:
    """GET an allowed source, following redirects only to allowed hosts (a redirect is checked like the first URL)."""
    s = get_settings()

    def check(req: httpx.Request) -> None:
        if any(h in req.url.host for h in NEVER_FETCH):
            raise ValueError(f"automated fetch from {req.url.host} is not allowed")

    with httpx.Client(
        headers={"User-Agent": s.http_user_agent}, timeout=120, follow_redirects=True, event_hooks={"request": [check]}
    ) as c:
        r = c.get(url)
    r.raise_for_status()
    return r


def load_registry() -> list[dict]:
    return yaml.safe_load((HERE / "documents.yaml").read_text())["documents"]


def _local_file(doc: dict) -> Path | None:
    if doc["fetch"] == "manual":
        p = REPO / doc["local_path"]
        return p if p.exists() else None
    if any(h in doc["url"] for h in NEVER_FETCH):
        raise ValueError(f"{doc['id']}: automated fetch from {doc['url']} is not allowed")
    RAW.mkdir(parents=True, exist_ok=True)
    p = RAW / f"{doc['id']}.pdf"
    if not p.exists():
        p.write_bytes(fetch_allowed(doc["url"]).content)
    return p


class _HTMLText(HTMLParser):
    """HTML to plain text with a line break at every block element; scripts and styles dropped."""

    BLOCK: ClassVar[set[str]] = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "table", "section"}

    def __init__(self, indent_markers: bool = False) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0
        self._indent_markers = indent_markers

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
            # The code publisher's HTML marks list depth with classes L2..L7; keep it for the LAMC chunker.
            cls = dict(attrs).get("class") or ""
            if self._indent_markers and (m := re.fullmatch(r"L(\d+)", cls)):
                self.parts.append(indent_marker(int(m.group(1))))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in raw.splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def strike_segments(page) -> list[tuple[float, float, float]]:
    """Thin horizontal lines and rects on a PDF page, as (x0, x1, y). Revised memos draw strikethrough this way."""
    return [
        (o["x0"], o["x1"], (o["top"] + o["bottom"]) / 2)
        for o in page.lines + page.rects
        if abs(o["bottom"] - o["top"]) <= 1.5 and o["x1"] - o["x0"] > 2
    ]


def not_struck(obj: dict, segments: list[tuple[float, float, float]]) -> bool:
    """False for a character crossed by a line through its middle (deleted text in a redlined document).
    Underlines sit below the middle, so added text is kept."""
    if obj.get("object_type") != "char":
        return True
    mid, height, cx = (obj["top"] + obj["bottom"]) / 2, obj["bottom"] - obj["top"], (obj["x0"] + obj["x1"]) / 2
    return not any(x0 <= cx <= x1 and abs(y - mid) < height * 0.25 for x0, x1, y in segments)


def _pages(path: Path, indent_markers: bool = False, drop_struck: bool = False) -> list[Page]:
    if path.suffix.lower() == ".txt":  # text already extracted from a PDF by the person who saved it
        return [Page(1, path.read_text(encoding="utf-8", errors="ignore"))]
    if path.suffix.lower() in (".html", ".htm"):
        parser = _HTMLText(indent_markers)
        parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
        return [Page(1, parser.text())]
    with pdfplumber.open(path) as pdf:
        out = []
        for i, page in enumerate(pdf.pages):
            if drop_struck:
                segs = strike_segments(page)
                page = page.filter(lambda o, segs=segs: not_struck(o, segs))
            out.append(Page(i + 1, page.extract_text() or ""))
        return out


def _trim(pages: list[Page], start: str, end: str, prefix: str = "") -> list[Page]:
    """Keep the law text of a page printed from a web site: drop what comes before `start` (replaced by `prefix`,
    e.g. the section number the chunker splits on) and everything after `end`, across pages."""
    out, started, done = [], False, False
    for p in pages:
        text = p.text
        if not started:
            i = text.find(start)
            if i < 0:
                continue
            text, started = prefix + text[i:], True
        j = text.find(end)
        if j >= 0:
            text, done = text[: j + len(end)], True
        out.append(Page(p.number, text))
        if done:
            break
    return out


def _label(doc: dict) -> str:
    return {
        "ord_184802_bmo": "Ord. 184,802",
        "ord_186481_adu": "Ord. 186,481",
        "za_memo_143": "ZA Memo 143",
        "palisades_rebuild_faq": "Palisades Rebuild FAQ",
        "eo1_revised": "EO 1",
        "eo8": "EO 8",
        "eo9": "EO 9",
        "sp_wla_timp": "WLA TIMP",
        "ch1a_art1": "Ch. 1A",
        "ch1a_art6": "Ch. 1A",
        "lacounty_title22": "LACC",
        "lacounty_adu_ord_2025": "LACC",
        "lacounty_south_bay_pasd": "LACC",
        "hcd_lacounty_adu_2025": "HCD letter",
    }.get(doc["id"], "Gov. Code" if doc["doc_type"] == "statute" else doc["title"])


def chunk_document(doc: dict, pages: list[Page]) -> list[Chunk]:
    # A County ordinance restating whole Title 22 sections is chunked as Title 22, so its ids match the code's.
    if doc.get("headings") == "title22_nested":
        return chunk_title22(pages, _label(doc), nested=True)
    if doc["doc_type"] == "ordinance":
        return chunk_ordinance(pages, _label(doc))
    if doc["doc_type"] == "code_section":
        return chunk_lamc(pages)
    if doc["doc_type"] == "statute":
        return chunk_statute(pages, _label(doc))
    if doc.get("headings") == "faq":
        return chunk_by_headings(pages, _label(doc), pattern=FAQ_HEADING)
    if doc.get("headings") == "letters":
        return chunk_order(pages, _label(doc))
    if doc.get("headings") == "title22":
        return chunk_title22(pages, _label(doc))
    if doc.get("headings") == "ch1a":
        return chunk_ch1a(pages, _label(doc))
    if doc.get("headings") == "plan":
        return chunk_by_headings(pages, _label(doc), pattern=PLAN_SECTION)
    if doc.get("headings") == "numbers":
        return chunk_by_headings(pages, _label(doc), pattern=ORDER_NUMBER)
    return chunk_by_headings(pages, _label(doc))


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")[:80]


def ingest(doc: dict) -> dict | None:
    path = _local_file(doc)
    if path is None:
        print(f"{doc['id']}: manual file not present at {doc['local_path']}; skipped")
        return None
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    pages = _pages(path, indent_markers=doc.get("doc_type") == "code_section", drop_struck=bool(doc.get("drop_struck")))
    for pat in doc.get("drop_patterns") or []:
        pages = [Page(p.number, re.sub(pat, "", p.text)) for p in pages]
    if doc.get("trim"):
        pages = _trim(pages, **doc["trim"])
    chunks = chunk_document(doc, pages)
    if doc.get("section_prefixes"):
        # "LACC 22.18." keeps that chapter's sections; an entry without the trailing dot ("LACC 22.14") keeps that
        # id only, so it does not also keep 22.140.
        keep = doc["section_prefixes"]
        chunks = [
            c for c in chunks if any(c.section_id.startswith(p) if p.endswith(".") else c.section_id == p for p in keep)
        ]
    retrieved = datetime.fromtimestamp(path.stat().st_mtime, UTC)

    # Stable ids: section slug plus ordinal within that section.
    seen: dict[str, int] = {}
    rows = []
    for c in chunks:
        key = _slug(c.section_id)
        seen[key] = seen.get(key, 0) + 1
        rows.append((f"{doc['id']}#{key}#{seen[key]}", c))

    with connect() as conn:
        conn.execute(
            """INSERT INTO reg_document (id, title, publisher, doc_type, jurisdiction, code_chapter, source_url,
                   retrieved_at, effective_date, effective_note, manual_retrieval, ocr_text, mock, file_sha256, pages)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,%s,%s)
               ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, publisher=EXCLUDED.publisher,
                   doc_type=EXCLUDED.doc_type, jurisdiction=EXCLUDED.jurisdiction, code_chapter=EXCLUDED.code_chapter,
                   source_url=EXCLUDED.source_url, retrieved_at=EXCLUDED.retrieved_at,
                   effective_date=EXCLUDED.effective_date, effective_note=EXCLUDED.effective_note,
                   manual_retrieval=EXCLUDED.manual_retrieval, ocr_text=EXCLUDED.ocr_text,
                   file_sha256=EXCLUDED.file_sha256, pages=EXCLUDED.pages""",
            (
                doc["id"],
                doc["title"],
                doc["publisher"],
                doc["doc_type"],
                doc["jurisdiction"],
                doc.get("code_chapter"),
                doc["url"],
                retrieved,
                doc.get("effective_date"),
                doc.get("effective_note"),
                doc["fetch"] == "manual",
                bool(doc.get("ocr_text")),
                sha,
                len(pages),
            ),
        )
        existing = {
            r["id"]: r["content_hash"]
            for r in conn.execute("SELECT id, content_hash FROM reg_chunk WHERE document_id=%s", (doc["id"],))
        }
        new_ids = {cid for cid, _ in rows}
        added = changed = unchanged = 0
        for cid, c in rows:
            h = c.content_hash
            if cid not in existing:
                added += 1
            elif existing[cid] != h:
                changed += 1
            else:
                # Same text, but the document may now come from another source (a new URL or date): keep the
                # provenance current without touching the text, its embedding or the rules read from it.
                unchanged += 1
                conn.execute(
                    """UPDATE reg_chunk SET source_url = %s, retrieved_at = %s, effective_date = %s, code_chapter = %s
                       WHERE id = %s""",
                    (doc["url"], retrieved, doc.get("effective_date"), doc.get("code_chapter"), cid),
                )
                continue
            conn.execute(
                """INSERT INTO reg_chunk (id, document_id, section_id, heading, text, page_start, page_end, source_url,
                       retrieved_at, effective_date, code_chapter, content_hash, mock, embedding)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,NULL)
                   ON CONFLICT (id) DO UPDATE SET section_id=EXCLUDED.section_id, heading=EXCLUDED.heading,
                       text=EXCLUDED.text, page_start=EXCLUDED.page_start, page_end=EXCLUDED.page_end,
                       retrieved_at=EXCLUDED.retrieved_at, effective_date=EXCLUDED.effective_date,
                       code_chapter=EXCLUDED.code_chapter, source_url=EXCLUDED.source_url,
                       content_hash=EXCLUDED.content_hash, embedding=NULL""",
                (
                    cid,
                    doc["id"],
                    c.section_id,
                    c.heading,
                    c.text,
                    c.page_start,
                    c.page_end,
                    doc["url"],
                    retrieved,
                    doc.get("effective_date"),
                    doc.get("code_chapter"),
                    h,
                ),
            )
        removed = [cid for cid in existing if cid not in new_ids]
        if removed:
            conn.execute("DELETE FROM reg_chunk WHERE id = ANY(%s)", (removed,))
        conn.execute(
            "INSERT INTO ingest_run (document_id, file_sha256, added, changed, removed, unchanged) VALUES (%s,%s,%s,%s,%s,%s)",
            (doc["id"], sha, added, changed, len(removed), unchanged),
        )
        conn.commit()
    return {
        "doc": doc["id"],
        "chunks": len(rows),
        "added": added,
        "changed": changed,
        "removed": len(removed),
        "unchanged": unchanged,
    }


def main(argv: list[str]) -> None:
    wanted = set(argv)
    for doc in load_registry():
        if wanted and doc["id"] not in wanted:
            continue
        result = ingest(doc)
        if result:
            print(result)


if __name__ == "__main__":
    main(sys.argv[1:])
