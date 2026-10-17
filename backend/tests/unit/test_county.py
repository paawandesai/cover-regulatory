from app.ingest.regtext.chunk import Page, chunk_title22
from app.parcel.zone import parse_county_zone

TEXT = """Chapter 22.18 Residential Zones
22.18.010 Purpose
22.18.040 Development Standards
22.18.010 Purpose
The residential zones are established to provide for housing, long enough to be kept as a chunk.
22.18.040 Development Standards
A. Required Yards. Table 22.18.040-A sets the yards for each zone.
R-1 20 5 10 5 15
1. A list item that is not a subsection.
C. A letter out of sequence, inside A.
B. Height. No building in Zone R-1 shall exceed a height of 35 feet above grade.
"""


def test_title22_splits_sections_and_lettered_subsections():
    chunks = chunk_title22([Page(1, TEXT)], "LACC")
    ids = [c.section_id for c in chunks]
    # The chapter's list of headings is skipped: the last occurrence of a number is the section itself.
    # The heading before subsection A is kept as the section's own chunk.
    assert ids == ["LACC 22.18.010", "LACC 22.18.040", "LACC 22.18.040 A", "LACC 22.18.040 B"]
    a = chunks[2].text
    assert "R-1 20 5 10 5 15" in a  # table rows survive
    assert "C. A letter out of sequence" in a


def test_county_zone_strings():
    z = parse_county_zone("R-1")
    assert (z.base, z.lot_area_sqft, z.unmodeled, z.family) == ("R-1", None, (), "COUNTY_R1")
    z = parse_county_zone("R-1-7500")
    assert z.lot_area_sqft == 7500 and not z.unmodeled
    z = parse_county_zone("R-1-10000-DP")
    assert z.lot_area_sqft == 10000 and z.combining == ("DP",) and z.unmodeled
    z = parse_county_zone("A-1-1")
    assert z.base == "A-1" and z.lot_acres == 1 and z.family != "COUNTY_R1"
    z = parse_county_zone("R-3-20U")
    assert z.units_per_acre == 20 and "not modeled" in z.unmodeled[0]


def test_title22_definitions_chapter_gets_its_own_id():
    text = """22.06.070 Zoning Map
D. The map is on file.
DIVISION 2: DEFINITIONS
Chapters:
Corner lot. A lot situated at the intersection of two or more streets.
Reversed corner lot. A corner lot whose street side lot line continues a front lot line.
DIVISION 3: ZONES
22.16.010 Purpose
Zones are established, with enough text here to make a chunk of its own.
"""
    ids = [c.section_id for c in chunk_title22([Page(1, text)], "LACC")]
    assert ids == ["LACC 22.06.070", "LACC 22.14", "LACC Division 3", "LACC 22.16.010"]
    defs = next(c for c in chunk_title22([Page(1, text)], "LACC") if c.section_id == "LACC 22.14")
    assert "Reversed corner lot" in defs.text and "22.16.010" not in defs.text


def test_title22_nested_splits_a_long_subsection_at_its_paragraphs():
    long = "x " * 1300
    text = (
        "22.140.640 Accessory Dwelling Units\nA. Purpose. Short.\n"
        f"B. Development Standards.\n1. Accessory Dwelling Units.\na. Floor Area. {long}\nb. Height. {long}\n"
        "C. Exempt Units. Short.\n"
    )
    ids = [c.section_id for c in chunk_title22([Page(1, text)], "LACC", nested=True)]
    assert "LACC 22.140.640 B.1.a" in ids and "LACC 22.140.640 B.1.b" in ids and "LACC 22.140.640 C" in ids
    # Without nested, the Volume I copy keeps its existing ids.
    flat = [c.section_id for c in chunk_title22([Page(1, text)], "LACC")]
    assert not any(".1." in i for i in flat)
