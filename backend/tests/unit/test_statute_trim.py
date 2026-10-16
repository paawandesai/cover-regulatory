from app.ingest.regtext.chunk import MAX_CHARS, Page, chunk_statute
from app.ingest.regtext.ingest import _trim


def test_trim_keeps_only_the_law_across_pages():
    pages = [
        Page(1, "Site menu\nFind a Lawyer\n(a) Except as provided, the rule.\n"),
        Page(2, "(b) More rule. This section is repealed.\nWas this helpful? Yes No"),
        Page(3, "Footer links"),
    ]
    out = _trim(pages, start="(a) Except", end="is repealed.", prefix="65913.4.\n")
    assert [p.number for p in out] == [1, 2]
    assert out[0].text.startswith("65913.4.\n(a) Except") and out[1].text.endswith("is repealed.")


def test_subdivision_opening_with_a_paragraph_still_splits():
    filler = "word " * (MAX_CHARS // 10)
    text = f"65913.4.\n(a) First {filler}\n(b) Second {filler}\n(c)(1) Third {filler}\n(d) Fourth {filler}\n"
    ids = [c.section_id for c in chunk_statute([Page(1, text)], "Gov. Code")]
    assert {"Gov. Code 65913.4(a)", "Gov. Code 65913.4(c)", "Gov. Code 65913.4(d)"} <= set(ids)
