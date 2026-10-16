"""Fetch, extract, chunk and store regulatory documents.

    uv run python -m app.ingest.regtext.ingest              # all documents available locally or by URL
    uv run python -m app.ingest.regtext.ingest za_memo_143

Re-ingestion compares each chunk's content hash with what is stored and records added / changed /
removed counts in `ingest_run`. Manual documents are skipped (with a message) until their file exists.
"""

import hashlib
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
    Chunk,
    Page,
    chunk_by_headings,
    chunk_lamc,
    chunk_ordinance,
    chunk_statute,
    indent_marker,
)

HERE = Path(__file__).parent
REPO = HERE.parents[3]
RAW = REPO / "data" / "raw" / "regtext"
NEVER_FETCH = ("amlegal.com", "municode.com", "upcodes.com", "iccsafe.org")


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
        s = get_settings()
        r = httpx.get(doc["url"], headers={"User-Agent": s.http_user_agent}, timeout=120, follow_redirects=True)
        r.raise_for_status()
        p.write_bytes(r.content)
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


def _pages(path: Path, indent_markers: bool = False) -> list[Page]:
    if path.suffix.lower() in (".html", ".htm"):
        parser = _HTMLText(indent_markers)
        parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
        return [Page(1, parser.text())]
    with pdfplumber.open(path) as pdf:
        return [Page(i + 1, page.extract_text() or "") for i, page in enumerate(pdf.pages)]


def _label(doc: dict) -> str:
    return {
        "ord_184802_bmo": "Ord. 184,802",
        "ord_186481_adu": "Ord. 186,481",
        "za_memo_143": "ZA Memo 143",
        "palisades_rebuild_faq": "Palisades Rebuild FAQ",
    }.get(doc["id"], "Gov. Code" if doc["doc_type"] == "statute" else doc["title"])


def chunk_document(doc: dict, pages: list[Page]) -> list[Chunk]:
    if doc["doc_type"] == "ordinance":
        return chunk_ordinance(pages, _label(doc))
    if doc["doc_type"] == "code_section":
        return chunk_lamc(pages)
    if doc["doc_type"] == "statute":
        return chunk_statute(pages, _label(doc))
    if doc.get("headings") == "faq":
        return chunk_by_headings(pages, _label(doc), pattern=FAQ_HEADING)
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
    pages = _pages(path, indent_markers=doc.get("doc_type") == "code_section")
    chunks = chunk_document(doc, pages)
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
                unchanged += 1
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
