"""Search over ingested regulation chunks.

1. A section reference in the query ("12.22 A.33", "Gov Code 66323") is looked up exactly and ranks first.
2. pgvector cosine search on local nomic embeddings ranks the rest. When the query names a zone ("R1", "RE15"),
   that zone's own LAMC section joins the fusion as a second ranked list, so the zone sections that read alike
   (RW1, RS, RU, RZ next to R1) don't crowd it out.
3. Postgres full-text search can join through reciprocal-rank fusion (FTS_WEIGHT); it is off by default
   because it lowered accuracy on the labeled question set, and it is the fallback when embeddings are missing.

Everything runs locally; the query text is never sent to a model provider."""

import os
import re
from dataclasses import dataclass, field

from app.db.connection import connect
from app.search.embed import embed_query
from app.search.index import vector_literal

RRF_K = 60
CANDIDATES = 50
# Weight of full-text rank in fusion. On the 32-question set (no holdout) full text added no recall and lowered
# MRR at every weight tried (1.0, 0.5, 0.3), so it defaults to 0 and is used only when embeddings are missing.
FTS_WEIGHT = float(os.environ.get("SEARCH_FTS_WEIGHT", "0"))

# "LAMC 12.08 C.2(a)", "12.22 A.33", "Sec. 12.21 C.10", "Section 12.08"
_LAMC_REF = re.compile(
    r"\b(?:LAMC\s+|Sec(?:tion|\.)?\s+)?(1[0-9]\.\d{2}(?:\.\d+)?)(?:\s*([A-Z]{1,2})(?:\.(\d+))?((?:\([a-z0-9]+\))*))?",
)
# "Gov Code 66323", "Government Code Section 66314(d)", or a bare 66xxx / 65852.21 number
_GOV_REF = re.compile(r"\b(6[56]\d{3}(?:\.\d+)?)((?:\([a-z0-9]+\))*)")


# "SEC. 12.08. “R1” ONE-FAMILY ZONE." -> zone R1 is section 12.08
_ZONE_HEADING = re.compile(r"^SEC\. (1[0-9]\.\d{2}(?:\.\d+)?)\. [“\"]?([A-Z][A-Z0-9.]*?)[”\"]? ")
_zone_sections: dict[str, str] | None = None


def zone_sections(conn) -> dict[str, str]:
    """Zone symbol -> LAMC section, read from the section headings once per process."""
    global _zone_sections
    if _zone_sections is None:
        out: dict[str, str] = {}
        for r in conn.execute(
            "SELECT DISTINCT heading FROM reg_chunk WHERE document_id = 'lamc_chapter1' AND heading LIKE 'SEC. 12.%%'"
        ).fetchall():
            m = _ZONE_HEADING.match(r["heading"] or "")
            if m and "ZONE" in r["heading"].upper() and re.fullmatch(r"[A-Z]{1,3}\d?(?:\.5)?", m.group(2)):
                out.setdefault(m.group(2), f"LAMC {m.group(1)}")
        _zone_sections = out
    return _zone_sections


def named_zone_sections(query: str, conn) -> list[str]:
    """LAMC sections of the zones a query names: "R1" -> 12.08; "RE15" or "RE" -> 12.07.01."""
    zones = zone_sections(conn)
    found = []
    for m in re.finditer(r"\b([A-Z]{1,3}\d?(?:\.5)?)(?:-?\d+)?\b", query):
        sym = m.group(1).replace("-", "")
        for cand in (sym, re.sub(r"\d+$", "", sym)):
            if cand in zones and len(cand) >= 2:
                found.append(zones[cand])
                break
    return list(dict.fromkeys(found))


@dataclass
class Hit:
    chunk_id: str
    section_id: str
    heading: str | None
    text: str
    document_id: str
    source_url: str
    retrieved_at: str
    effective_date: str | None
    code_chapter: str | None
    mock: bool
    score: float
    matched_by: list[str] = field(default_factory=list)


def section_refs(query: str) -> list[str]:
    """Canonical section ids named in the query, e.g. ["LAMC 12.22 A.33", "Gov. Code 66323"]."""
    refs: list[str] = []
    for m in _LAMC_REF.finditer(query):
        ref = f"LAMC {m.group(1)}"
        if m.group(2):
            ref += f" {m.group(2)}"
            if m.group(3):
                ref += f".{m.group(3)}"
            ref += m.group(4) or ""
        refs.append(ref)
    for m in _GOV_REF.finditer(query):
        refs.append(f"Gov. Code {m.group(1)}{m.group(2) or ''}")
    return list(dict.fromkeys(refs))


def _ref_pattern(ref: str) -> str:
    # Match the ref itself or any child ("LAMC 12.08 C" matches "LAMC 12.08 C.2(a)"), and ordinance
    # chunks that amend it ("Ord. 184,802 Sec. 10 (LAMC 12.08 C.2)").
    return r"(^|\()" + re.escape(ref) + r"($|[ .(),])"


def _ancestors(ref: str) -> list[str]:
    """ "LAMC 12.08 C.2(a)" -> itself, "LAMC 12.08 C.2", "LAMC 12.08 C", "LAMC 12.08"."""
    out = [ref]
    while True:
        cur = out[-1]
        nxt = re.sub(r"\([a-z0-9]+\)$", "", cur)
        if nxt == cur:
            nxt = (
                re.sub(r"\.\d+$", "", cur) if re.search(r" [A-Z]{1,2}\.\d+$", cur) else re.sub(r" [A-Z]{1,2}$", "", cur)
            )
        if nxt == cur:
            return out
        out.append(nxt)


_COLUMNS = """c.id, c.section_id, c.heading, c.text, c.document_id, c.source_url, c.retrieved_at::text,
              c.effective_date::text, c.code_chapter, c.mock"""


JURISDICTION_FILTERS = {
    # State law applies in both; Title 22 is the County's code, everything else loaded is the City's.
    "city": "AND c.code_chapter IS DISTINCT FROM 'T22' ",
    "county": "AND (c.code_chapter = 'T22' OR c.document_id LIKE 'gov\\_%%') ",
}


def search(
    query: str,
    k: int = 10,
    document_ids: list[str] | None = None,
    mode: str = "hybrid",
    jurisdiction: str | None = None,
) -> list[Hit]:
    """mode "full_text" or "embedding" runs one retriever alone (plus the section-id lookup), for evaluation.
    jurisdiction "city" or "county" keeps to the text that governs there."""
    doc_filter = (
        ("AND c.document_id = ANY(%(docs)s) " if document_ids else "")
        + JURISDICTION_FILTERS.get(jurisdiction or "", "")
        + "AND NOT c.mock"
    )
    params: dict = {"q": query, "n": CANDIDATES, "docs": document_ids}
    rows: dict[str, dict] = {}
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}

    def add(ranked: list[dict], how: str, weight: float = 1.0):
        for rank, r in enumerate(ranked, start=1):
            rows.setdefault(r["id"], r)
            scores[r["id"]] = scores.get(r["id"], 0.0) + weight / (RRF_K + rank)
            matched.setdefault(r["id"], []).append(how)

    with connect() as conn:
        refs = section_refs(query)
        exact: list[dict] = []
        for ref in refs:
            # "66314(d)(7)" may be stored as part of "Gov. Code 66314(d)": walk up until something matches.
            for candidate in _ancestors(ref):
                found = conn.execute(
                    f"""SELECT {_COLUMNS} FROM reg_chunk c
                        WHERE c.section_id ~* %(pat)s {doc_filter}
                        ORDER BY (c.document_id LIKE 'ord_%%'), length(c.section_id), c.id LIMIT %(n)s""",
                    {**params, "pat": _ref_pattern(candidate)},
                ).fetchall()
                if found:
                    exact += found
                    break
        # A named section outranks anything fusion can produce.
        add(exact, "section_id", weight=float(RRF_K))
        fts = conn.execute(
            f"""SELECT {_COLUMNS} FROM reg_chunk c, websearch_to_tsquery('english', %(q)s) q
                WHERE c.tsv @@ q {doc_filter}
                ORDER BY ts_rank_cd(c.tsv, q, 32) DESC LIMIT %(n)s""",
            params,
        ).fetchall()
        if mode == "embedding":
            fts = []
        elif not fts:
            # websearch_to_tsquery ANDs every term; fall back to OR so long questions still match.
            fts = conn.execute(
                f"""SELECT {_COLUMNS} FROM reg_chunk c,
                       to_tsquery('english', array_to_string(tsvector_to_array(to_tsvector('english', %(q)s)), ' | ')) q
                    WHERE c.tsv @@ q {doc_filter}
                    ORDER BY ts_rank_cd(c.tsv, q, 32) DESC LIMIT %(n)s""",
                params,
            ).fetchall()
        vec = (
            []
            if mode == "full_text"
            else conn.execute(
                f"""SELECT {_COLUMNS} FROM reg_chunk c
                WHERE c.embedding IS NOT NULL {doc_filter}
                ORDER BY c.embedding <=> %(v)s::vector LIMIT %(n)s""",
                {**params, "v": vector_literal(embed_query(query))},
            ).fetchall()
        )
        add(vec, "embedding")
        zone_secs = named_zone_sections(query, conn)
        if zone_secs and vec:
            pat = re.compile(r"^(?:" + "|".join(re.escape(z) for z in zone_secs) + r")($| )")
            add([r for r in vec if pat.match(r["section_id"])], "zone")
        # Full text joins the fusion when it is weighted, when it is the only retriever asked for, or when no
        # chunk has an embedding yet (e.g. right after an ingest, before the indexer has run).
        if mode == "full_text":
            add(fts, "full_text")
        elif FTS_WEIGHT > 0 or not vec:
            add(fts, "full_text", weight=FTS_WEIGHT or 1.0)

    best = sorted(scores, key=lambda i: scores[i], reverse=True)[:k]
    return [
        Hit(
            chunk_id=i,
            section_id=rows[i]["section_id"],
            heading=rows[i]["heading"],
            text=rows[i]["text"],
            document_id=rows[i]["document_id"],
            source_url=rows[i]["source_url"],
            retrieved_at=rows[i]["retrieved_at"],
            effective_date=rows[i]["effective_date"],
            code_chapter=rows[i]["code_chapter"],
            mock=rows[i]["mock"],
            score=round(scores[i], 6),
            matched_by=matched[i],
        )
        for i in best
    ]
