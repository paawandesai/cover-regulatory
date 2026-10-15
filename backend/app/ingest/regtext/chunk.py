"""Split regulatory documents into citable chunks that keep the document's own section numbering.

Ordinances are split at "Sec. N." and each section is labeled with the LAMC provision it amends
(e.g. "Subdivision 2 of Subsection C of Section 12.08" -> "LAMC 12.08 C.2"). Long sections are split
again at lettered paragraphs "(a)", "(b)" ... Memos, guidance and statutes are split at their headings.
No text is rewritten; figure labels and page numbers are the only lines dropped.
"""

import hashlib
import re
from dataclasses import dataclass

MAX_CHARS = 2400


@dataclass
class Page:
    number: int
    text: str


@dataclass
class Chunk:
    section_id: str
    heading: str | None
    text: str
    page_start: int
    page_end: int

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


_ORD_SECTION = re.compile(r"^\s*(?:Section|Sec)\.?\s*(\d+)\.\s+(.*)$", re.M)
_SECTION_NUM = re.compile(r"Section\s+(\d+\.\d+(?:\.\d+)?)")
_SUBSECTION = re.compile(r"Subsection\s+([A-Z]{1,2})\b")
_SUBDIVISION = re.compile(r"Subdivision\s+(\d+)")
_PARAGRAPH = re.compile(r"Paragraph\s+\(([a-z]{1,2})\)", re.I)
_SUBPARAGRAPH = re.compile(r"Subparagraph\s+\((\d+)\)")
_LETTER_PARA = re.compile(r"^\s*\(([a-z])\)\s+", re.M)
_ROMAN_HEADING = re.compile(r"^\s*([IVX]{1,5})\.\s+(\S.*)$", re.M)
_STATUTE_SECTION = re.compile(r"^\s*(\d{5}(?:\.\d+)?)\.\s", re.M)


def clean_page_text(text: str) -> str:
    keep = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            keep.append("")
            continue
        letters = sum(c.isalpha() for c in s)
        if re.fullmatch(r"\d{5}(\.\d+)?\.", s):  # statute section number on its own line
            keep.append(s)
            continue
        if re.fullmatch(r"\d{1,3}", s):  # page number
            continue
        if letters < 3 and not re.search(r"\d+\s*(feet|ft|%|percent)", s, re.I):
            continue  # figure fragments such as "/", "5 FT", "• •"
        keep.append(s)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()


def lamc_target(sentence: str) -> str | None:
    """'Subdivision 2 of Subsection C of Section 12.08 ...' -> 'LAMC 12.08 C.2'."""
    head = sentence[:400]
    sec = _SECTION_NUM.search(head)
    if not sec:
        return None
    ref = sec.group(1)
    if m := _SUBSECTION.search(head):
        ref += f" {m.group(1)}"
        if d := _SUBDIVISION.search(head):
            ref += f".{d.group(1)}"
            if p := _PARAGRAPH.search(head):
                ref += f"({p.group(1).lower()})"
                if sp := _SUBPARAGRAPH.search(head):
                    ref += f"({sp.group(1)})"
    return f"LAMC {ref}"


def _joined(pages: list[Page]) -> tuple[str, list[tuple[int, int]]]:
    """Concatenate pages and remember where each starts, so chunks can report page ranges."""
    parts, offsets, pos = [], [], 0
    for p in pages:
        t = clean_page_text(p.text) + "\n\n"
        offsets.append((pos, p.number))
        parts.append(t)
        pos += len(t)
    return "".join(parts), offsets


def _page_at(offsets: list[tuple[int, int]], pos: int) -> int:
    page = offsets[0][1]
    for start, num in offsets:
        if start <= pos:
            page = num
        else:
            break
    return page


def _split_long(text: str, start: int, section_id: str, heading: str | None, offsets) -> list[Chunk]:
    """Split at lettered paragraphs, then at blank lines, so no chunk exceeds MAX_CHARS."""
    if len(text) <= MAX_CHARS:
        return [Chunk(section_id, heading, text.strip(), _page_at(offsets, start), _page_at(offsets, start + len(text)))]
    marks = [m for m in _LETTER_PARA.finditer(text)]
    pieces: list[tuple[str, int, str]] = []
    if len(marks) >= 2:
        bounds = [0] + [m.start() for m in marks] + [len(text)]
        labels = [""] + [f"({m.group(1)})" for m in marks]
        for i in range(len(bounds) - 1):
            seg = text[bounds[i]:bounds[i + 1]]
            if seg.strip():
                pieces.append((seg, bounds[i], labels[i]))
    else:
        pieces = [(text, 0, "")]
    # A bare section number before the first lettered paragraph ("66317.") joins the next piece.
    merged: list[tuple[str, int, str]] = []
    carry, carry_off = "", None
    for seg, off, label in pieces:
        if len(seg.strip()) < 20 and not label:
            carry, carry_off = carry + seg, off if carry_off is None else carry_off
            continue
        if carry:
            seg, off, carry, carry_off = carry + seg, carry_off, "", None
        merged.append((seg, off, label))
    if carry:
        merged.append((carry, carry_off or 0, ""))
    out: list[Chunk] = []
    for seg, off, label in merged:
        sid = f"{section_id}{label}" if label and not section_id.endswith(label) else section_id
        buf, buf_off = "", off
        for para in re.split(r"(\n\n)", seg):
            if len(buf) + len(para) > MAX_CHARS and buf.strip():
                out.append(Chunk(sid, heading, buf.strip(), _page_at(offsets, start + buf_off),
                                 _page_at(offsets, start + buf_off + len(buf))))
                buf_off += len(buf)
                buf = ""
            buf += para
        if buf.strip():
            out.append(Chunk(sid, heading, buf.strip(), _page_at(offsets, start + buf_off),
                             _page_at(offsets, start + buf_off + len(buf))))
    return out


def chunk_ordinance(pages: list[Page], ordinance_label: str) -> list[Chunk]:
    text, offsets = _joined(pages)
    marks = list(_ORD_SECTION.finditer(text))
    chunks: list[Chunk] = []
    if marks and marks[0].start() > 0:
        chunks += _split_long(text[: marks[0].start()], 0, f"{ordinance_label} preamble", "Preamble", offsets)
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.start():end]
        target = lamc_target(m.group(2) + " " + body[:400])
        sid = f"{ordinance_label} Sec. {m.group(1)}" + (f" ({target})" if target else "")
        heading = target or f"Sec. {m.group(1)}"
        chunks += _split_long(body, m.start(), sid, heading, offsets)
    return chunks


def chunk_by_headings(
    pages: list[Page], label: str, pattern: re.Pattern = _ROMAN_HEADING, keep_intro: bool = True
) -> list[Chunk]:
    text, offsets = _joined(pages)
    marks = list(pattern.finditer(text))
    # A table of contents repeats the headings; keep the last occurrence of each heading key.
    last: dict[str, re.Match] = {}
    for m in marks:
        last[m.group(1)] = m
    marks = sorted(last.values(), key=lambda m: m.start())
    chunks: list[Chunk] = []
    first = marks[0].start() if marks else len(text)
    if keep_intro and text[:first].strip():
        chunks += _split_long(text[:first], 0, f"{label} introduction", "Introduction", offsets)
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        heading = m.group(2).strip()[:160] if m.lastindex and m.lastindex >= 2 else None
        chunks += _split_long(text[m.start():end], m.start(), f"{label} {m.group(1)}", heading, offsets)
    return chunks


def chunk_statute(pages: list[Page], code_label: str) -> list[Chunk]:
    # Text before the first section is site navigation and headings, not law.
    return chunk_by_headings(pages, code_label, _STATUTE_SECTION, keep_intro=False)
