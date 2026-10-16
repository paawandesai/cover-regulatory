from app.ingest.regtext.chunk import Page, chunk_order

TEXT = """EMERGENCY EXECUTIVE ORDER NO. 1
INTRODUCTION
Some recitals about the fires and the Governor's orders, long enough to keep.
A. Clean Up Efforts
1. Debris Removal: The Bureaus shall establish a task force for debris removal.
B. Rebuilding
3. Review Rules for Eligible Projects:
a. Definitions.
1. The project is to repair, restore, demolish, or replace property:
4. The project involves one or more of the following:
a. Primary structures that do not exceed 110% of the footprint and height.
5. Tolling of Permits: Permits are tolled for the length of the emergency.
"""


def test_order_splits_at_titled_paragraphs_only():
    chunks = chunk_order([Page(1, TEXT)], "EO 1")
    ids = [c.section_id for c in chunks]
    assert ids == ["EO 1 introduction", "EO 1 A.1", "EO 1 B.3", "EO 1 B.5"]
    # Untitled numbered items ("4. The project involves ...") stay inside their paragraph.
    assert "110% of the footprint" in chunks[2].text
