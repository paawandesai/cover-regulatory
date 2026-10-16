from app.engine.links import deep_link


def test_gov_code_links_to_the_section():
    url = "https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=GOV&division=1."
    assert deep_link(url, "Gov. Code 66323(a)").endswith("sectionNum=66323")


def test_pdf_links_to_the_page():
    assert deep_link("https://cityclerk.lacity.org/x/ORD_186481.pdf", "LAMC 12.22 A.33(d)", 7).endswith("#page=7")


def test_other_links_are_unchanged():
    assert deep_link("https://codelibrary.amlegal.com/codes/los_angeles", "LAMC 12.08 C.2", 3) == (
        "https://codelibrary.amlegal.com/codes/los_angeles"
    )
    assert deep_link(None, "LAMC 12.08") is None
