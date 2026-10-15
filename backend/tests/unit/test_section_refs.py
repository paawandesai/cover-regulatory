from app.search.search import _ancestors, section_refs


def test_section_refs():
    assert section_refs("what does 12.22 A.33 say") == ["LAMC 12.22 A.33"]
    assert section_refs("LAMC 12.08 C.2(a) side yard") == ["LAMC 12.08 C.2(a)"]
    assert section_refs("Gov Code 66314(d)(7)") == ["Gov. Code 66314(d)(7)"]
    assert section_refs("rear yard in R1") == []


def test_ancestors_walk_up():
    assert _ancestors("LAMC 12.08 C.2(a)") == ["LAMC 12.08 C.2(a)", "LAMC 12.08 C.2", "LAMC 12.08 C", "LAMC 12.08"]
