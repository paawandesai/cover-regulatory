"""Assessment items and the two ways they cite text: through rule fragments, or a chunk looked up by section id."""

from dataclasses import dataclass, field

from app.engine import rules as R
from app.engine.links import deep_link

LABEL_TEXT = {
    "verified": "Verified parcel data",
    "derived": "Derived from rule {rule}",
    "interpretive": "Interpretation, confirm with the jurisdiction",
    "uncited": "No cited source found",
    "withheld": "Not modeled here",
    "approximate": "Approximate",
    "flag": "Flag, not evaluated",
    "mock": "MOCK data",
}


@dataclass
class Item:
    id: str
    family: str  # parcel | r1_envelope | guest_house | adu | jadu | flag
    title: str
    value: float | str | bool | None
    unit: str | None
    label: str
    rule_id: str | None = None
    coverage: float | None = None
    explanation: str | None = None
    citations: list[dict] = field(default_factory=list)
    source: dict | None = None

    @property
    def label_text(self) -> str:
        return LABEL_TEXT[self.label].format(rule=self.rule_id)


def rule_item(item_id, family, title, ri: R.RuleInputs, value, unit, explanation) -> Item:
    label = ri.label if value is not None else "uncited"
    return Item(
        item_id,
        family,
        title,
        value,
        unit,
        label,
        rule_id=ri.rule_id,
        coverage=ri.coverage if label == "interpretive" else None,
        explanation=explanation,
        citations=ri.citations(),
    )


def chunk_citation(conn, section_id: str, contains: str | None = None) -> list[dict]:
    """Cite a chunk by its section id (looked up in code, never emitted by a model)."""
    row = conn.execute(
        """SELECT id, section_id, code_chapter, source_url, page_start, retrieved_at::text AS retrieved_at, text
           FROM reg_chunk WHERE section_id = %s AND (%s::text IS NULL OR text ILIKE '%%' || %s || '%%')
           ORDER BY id LIMIT 1""",
        (section_id, contains, contains),
    ).fetchone()
    if row is None:
        return []
    # Quote from the phrase that made this the right chunk (or the start), so the panel highlights it.
    start = max(row["text"].lower().find(contains.lower()), 0) if contains else 0
    end = min(len(row["text"]), start + 400)
    return [
        {
            "chunk_id": row["id"],
            "section_id": row["section_id"],
            "code_chapter": row["code_chapter"],
            "quote": row["text"][start:end],
            "quote_start": start,
            "quote_end": end,
            "source_url": deep_link(row["source_url"], row["section_id"], row["page_start"]),
            "retrieved_at": row["retrieved_at"],
            "review_status": "code-cited",
        }
    ]
