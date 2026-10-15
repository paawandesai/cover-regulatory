from app.ingest.regtext.chunk import Page, chunk_lamc, indent_marker

L2, L3, L7 = indent_marker(2), indent_marker(3), indent_marker(7)

SAMPLE = "\n".join(
    [
        "SEC. 12.08. R1 ONE-FAMILY ZONE.",
        "A. Use. No building shall be used except for the following:",
        f"{L2} 1. One-family dwelling.",
        f"{L2} 2. Accessory buildings, including accessory living quarters,",
        "C. and Sec. 12.22 C. (Amended by Ord. No. 107,884.)",  # wrapped cross-reference, not a subsection
        f"{L2} 3. Accessory uses and home occupations.",
        "B. Restriction. Text.",
        "C. Area (Development Standards). No building shall be erected unless:",
        f"{L2} 1. Front Yard. There shall be a front yard.",
        f"{L3} (a) For a main building not more than two stories.",
        f"{L3} 3. Rear Yard. There shall be a rear yard of not less than 15 feet.",
        f"{L7} A. That the use will enhance the built environment;",  # nested findings list
        "SEC. 14.00. OUT OF SCOPE.",
        "A. Ignored.",
    ]
)


def ids():
    return [c.section_id for c in chunk_lamc([Page(1, SAMPLE)])]


def test_lamc_ids_follow_subsection_sequence():
    assert ids() == [
        "LAMC 12.08",
        "LAMC 12.08 A",
        "LAMC 12.08 A.1",
        "LAMC 12.08 A.2",
        "LAMC 12.08 A.3",
        "LAMC 12.08 B",
        "LAMC 12.08 C",
        "LAMC 12.08 C.1",
        "LAMC 12.08 C.3",
    ]


def test_cross_reference_and_nested_lists_stay_in_parent():
    chunks = {c.section_id: c.text for c in chunk_lamc([Page(1, SAMPLE)])}
    assert "C. and Sec. 12.22 C." in chunks["LAMC 12.08 A.2"]
    assert "That the use will enhance" in chunks["LAMC 12.08 C.3"]
    assert all("" not in t for t in chunks.values())
