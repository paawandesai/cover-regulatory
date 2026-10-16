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


_ORD_SECTION = re.compile(r"^\s*(?:Section|Sec)\.?\s*(\d+)\.\s+(.*)$", re.MULTILINE)
_SECTION_NUM = re.compile(r"Section\s+(\d+\.\d+(?:\.\d+)?)")
_SUBSECTION = re.compile(r"Subsection\s+([A-Z]{1,2})\b")
_SUBDIVISION = re.compile(r"Subdivision\s+(\d+)")
_PARAGRAPH = re.compile(r"Paragraph\s+\(([a-z]{1,2})\)", re.IGNORECASE)
_SUBPARAGRAPH = re.compile(r"Subparagraph\s+\((\d+)\)")
# "(b) Text" or "(j)(1) Text": a subdivision may open straight into its first numbered paragraph.
_LETTER_PARA = re.compile(r"^\s*\(([a-z])\)(?:\s+|(?=\(\d))", re.MULTILINE)
_ROMAN_HEADING = re.compile(r"^\s*([IVX]{1,5})\.\s+(\S.*)$", re.MULTILINE)
# FAQ documents: "Q11. Can I build an Accessory Dwelling Unit ...?"
FAQ_HEADING = re.compile(r"^\s*(Q\d{1,3})\.\s+(\S.*)$", re.MULTILINE)
# Executive orders: top-level lettered paragraphs ("B. Rebuilding"), or numbered ones in a short order.
ORDER_LETTER = re.compile(r"^\s*([A-H])\.\s+([A-Z]\S*(?: \S+){0,8})\s*$", re.MULTILINE)
ORDER_NUMBER = re.compile(r"^\s*(\d{1,2})\.\s+(\S.*)$", re.MULTILINE)
_STATUTE_SECTION = re.compile(r"^\s*(\d{5}(?:\.\d+)?)\.\s", re.MULTILINE)


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
        if letters < 3 and not re.search(r"\d+\s*(feet|ft|%|percent)", s, re.IGNORECASE):
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


def _bounded_parts(seg: str) -> list[str]:
    """Blank-line parts; a part still over MAX_CHARS is cut at line ends, then at sentence ends."""
    out: list[str] = []
    for para in re.split(r"(\n\n)", seg):
        if len(para) <= MAX_CHARS:
            out.append(para)
            continue
        for line in re.split(r"(\n)", para):
            if len(line) <= MAX_CHARS:
                out.append(line)
            else:
                out += re.split(r"(?<=\.) (?=[A-Z(])", line)
    return out


def _split_long(text: str, start: int, section_id: str, heading: str | None, offsets) -> list[Chunk]:
    """Split at lettered paragraphs, then at blank lines, so no chunk exceeds MAX_CHARS."""
    if len(text) <= MAX_CHARS:
        return [
            Chunk(section_id, heading, text.strip(), _page_at(offsets, start), _page_at(offsets, start + len(text)))
        ]
    # Keep only markers that continue (a), (b), (c) ...; a roman "(i)" after "(c)" stays in its parent.
    marks, prev = [], None
    for m in _LETTER_PARA.finditer(text):
        if (prev is None and m.group(1) == "a") or (prev and ord(m.group(1)) - ord(prev) == 1):
            marks.append(m)
            prev = m.group(1)
    pieces: list[tuple[str, int, str]] = []
    if len(marks) >= 2:
        bounds = [0] + [m.start() for m in marks] + [len(text)]
        labels = [""] + [f"({m.group(1)})" for m in marks]
        for i in range(len(bounds) - 1):
            seg = text[bounds[i] : bounds[i + 1]]
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
        for para in _bounded_parts(seg):
            if len(buf) + len(para) > MAX_CHARS and buf.strip():
                out.append(
                    Chunk(
                        sid,
                        heading,
                        buf.strip(),
                        _page_at(offsets, start + buf_off),
                        _page_at(offsets, start + buf_off + len(buf)),
                    )
                )
                buf_off += len(buf)
                buf = ""
            buf += para
        if buf.strip():
            out.append(
                Chunk(
                    sid,
                    heading,
                    buf.strip(),
                    _page_at(offsets, start + buf_off),
                    _page_at(offsets, start + buf_off + len(buf)),
                )
            )
    return out


def chunk_ordinance(pages: list[Page], ordinance_label: str) -> list[Chunk]:
    text, offsets = _joined(pages)
    marks = list(_ORD_SECTION.finditer(text))
    chunks: list[Chunk] = []
    if marks and marks[0].start() > 0:
        chunks += _split_long(text[: marks[0].start()], 0, f"{ordinance_label} preamble", "Preamble", offsets)
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.start() : end]
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
        chunks += _split_long(text[m.start() : end], m.start(), f"{label} {m.group(1)}", heading, offsets)
    return chunks


_TITLE_WORD = r"(?:[A-Z][\w'’-]*|of|and|for|the|to|in|on|or)"
_ORDER_TITLED = re.compile(rf"^\s*(\d{{1,2}})\.\s+([A-Z][\w'’-]*(?: {_TITLE_WORD}){{0,8}}):", re.MULTILINE)


def chunk_order(pages: list[Page], label: str) -> list[Chunk]:
    """An executive order split at its lettered paragraphs ("B. Rebuilding") and their titled numbered
    paragraphs ("3. Review Rules for Eligible Projects:"), as "EO 1 B.3". Untitled numbered items stay inside."""
    text, offsets = _joined(pages)
    marks: list[tuple[int, str, str]] = []
    for m in ORDER_LETTER.finditer(text):
        marks.append((m.start(), m.group(1), m.group(2).strip()))
    letters = sorted(marks)
    for m in _ORDER_TITLED.finditer(text):
        parent = next((lt for lt in reversed(letters) if lt[0] < m.start()), None)
        if parent:
            marks.append((m.start(), f"{parent[1]}.{m.group(1)}", m.group(2).strip()))
    marks.sort()
    chunks: list[Chunk] = []
    first = marks[0][0] if marks else len(text)
    if text[:first].strip():
        chunks += _split_long(text[:first], 0, f"{label} introduction", "Introduction", offsets)
    for i, (start, key, heading) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        if end - start < 40:
            continue  # a lettered heading straight followed by its first numbered paragraph
        chunks += _split_long(text[start:end], start, f"{label} {key}", heading[:160], offsets)
    return chunks


def chunk_statute(pages: list[Page], code_label: str) -> list[Chunk]:
    # Text before the first section is site navigation and headings, not law.
    return chunk_by_headings(pages, code_label, _STATUTE_SECTION, keep_intro=False)


_LAMC_SEC = re.compile(r"^SEC\. ?(\d+\.\d+(?:\.\d+)*)\.\s*(.*)$")
_LAMC_SUBSEC = re.compile(r"^([A-Z]{1,2})\.\s+[A-Z(\"“]")
_LAMC_SUBDIV = re.compile(r"^(\d{1,3})\.\s+\S")


_INDENT = re.compile("\ue000L(\\d+)\ue000")


def indent_marker(depth: int) -> str:
    """Private-use marker the HTML reader puts before a list item, so the chunker knows its depth."""
    return f"\ue000L{depth}\ue000"


def _letter_value(s: str) -> int:
    # "A".."Z" then "AA", "BB" ... as the LAMC numbers long subsection runs.
    return (ord(s[0]) - 64) + (26 * (len(s) - 1))


def _next_letter(prev: str | None, cand: str) -> bool:
    if prev is None:
        return cand == "A"
    return 1 <= _letter_value(cand) - _letter_value(prev) <= 2


def _next_number(prev: str | None, cand: str) -> bool:
    if prev is None:
        return cand == "1"
    return 1 <= int(cand) - int(prev) <= 2


def chunk_lamc(pages: list[Page], keep_prefixes: tuple[str, ...] = ("12.", "13.")) -> list[Chunk]:
    """Consolidated LAMC text: split at "SEC. 12.08." headings, then at subsections ("C.") and
    subdivisions ("2."), labeling each chunk like "LAMC 12.08 C.2". Long subdivisions are split again at
    lettered paragraphs. Only sections whose number starts with one of `keep_prefixes` are kept."""
    lines = "\n".join(p.text for p in pages).splitlines()
    groups: list[tuple[str, str | None, list[str]]] = []  # (section_id, heading, lines)
    sec = subsec = subdiv = None
    sec_title = None
    current: list[str] = []
    current_id: str | None = None

    def flush():
        if current_id and any(s.strip() for s in current):
            groups.append((current_id, sec_title, list(current)))

    has_depth = any(_INDENT.search(ln) for ln in lines)
    for raw in lines:
        # Depth 0 is a top-level block (subsection headings); subdivisions sit at L2 or L3; deeper lists
        # ("A. That the ..." findings inside a subdivision) never open a new subsection or subdivision.
        depth = int(d.group(1)) if (d := _INDENT.search(raw)) else 0
        line = _INDENT.sub("", raw).strip()
        if not line:
            continue
        if m := _LAMC_SEC.match(line):
            flush()
            sec, subsec, subdiv = m.group(1), None, None
            sec_title = f"SEC. {sec}. {m.group(2)}".strip()
            current, current_id = [line], (f"LAMC {sec}" if sec.startswith(keep_prefixes) else None)
            continue
        if sec is None or not sec.startswith(keep_prefixes):
            continue
        # Markers must continue the sequence (A, B, C ... / 1, 2, 3 ...), so a cross-reference that
        # happens to start a line ("C. and Sec. 12.22 C.") is not mistaken for a new subsection.
        if (not has_depth or depth == 0) and (m := _LAMC_SUBSEC.match(line)) and _next_letter(subsec, m.group(1)):
            flush()
            subsec, subdiv = m.group(1), None
            current, current_id = [line], f"LAMC {sec} {subsec}"
            continue
        if (
            subsec
            and (not has_depth or depth <= 3)
            and (m := _LAMC_SUBDIV.match(line))
            and _next_number(subdiv, m.group(1))
        ):
            flush()
            subdiv = m.group(1)
            current, current_id = [line], f"LAMC {sec} {subsec}.{subdiv}"
            continue
        current.append(line)
    flush()

    chunks: list[Chunk] = []
    for sid, heading, body in groups:
        text = "\n\n".join(body)
        offsets = [(0, 1)]
        chunks += _split_long(text, 0, sid, heading, offsets)
    return chunks
