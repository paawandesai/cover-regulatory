"""Links that open the cited passage itself where the publisher allows it, instead of a document's front page.

Built from the stored URL and section id only; nothing is fetched. The code publisher (amlegal) has no stable
section anchors we can derive without crawling it, so LAMC links stay as stored."""

import re

_GOV = re.compile(r"^Gov\. Code (\d{5}(?:\.\d+)?)")
LEGINFO_SECTION = "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=GOV&sectionNum={}"


def deep_link(source_url: str | None, section_id: str | None, page: int | None = None) -> str | None:
    if not source_url:
        return None
    m = _GOV.match(section_id or "")
    if m and "leginfo.legislature.ca.gov" in source_url:
        return LEGINFO_SECTION.format(m.group(1))
    if page and source_url.lower().split("?")[0].endswith(".pdf") and "#" not in source_url:
        return f"{source_url}#page={page}"
    return source_url
