import pytest

from app.parcel.zone import parse_zone


def test_plain_r1():
    z = parse_zone("R1-1")
    assert z.base_zone == "R1" and z.height_district == "1"
    assert z.is_plain_r1 and z.regime_hint == "I"


@pytest.mark.parametrize("raw,height", [("R1-1VL", "1VL"), ("R1-1XL", "1XL"), ("R1-2", "2"), ("R1-1L", "1L")])
def test_height_district_suffixes(raw, height):
    z = parse_zone(raw)
    assert z.height_district == height and z.is_plain_r1


def test_qualifiers_and_supplemental_are_flagged():
    z = parse_zone("(T)(Q)R1-1-RFA")
    assert z.prefixes == ("T", "Q")
    assert z.supplemental == ("RFA",)
    assert z.is_r1_family and not z.is_plain_r1
    assert any("RFA" in u for u in z.unmodeled)


def test_bracket_q_and_d_limitation():
    z = parse_zone("[Q]R1-1D-HCR")
    assert z.prefixes == ("Q",) and z.development_limitation
    assert z.supplemental == ("HCR",)
    assert not z.is_plain_r1


def test_unbracketed_q_prefix():
    z = parse_zone("QR1P-1VL")
    assert z.prefixes == ("Q",) and z.base_zone == "R1P"
    assert not z.is_r1_family


def test_r1_variation():
    z = parse_zone("R1V2-1")
    assert z.base_zone == "R1V2" and z.is_r1_family and z.is_modeled and not z.is_plain_r1
    assert not parse_zone("R1V2-HPOZ").is_modeled  # no height district, and an HPOZ
    assert parse_zone("R1H1-1").is_modeled  # Hillside variation: the Table 12.21 C.10-2b column
    assert not parse_zone("R1H1").is_modeled  # "1" is the variation number; no height district


def test_footnote_marker():
    z = parse_zone("R1-1XL-O#-CUGU")
    assert z.supplemental == ("O", "CUGU") and any("#" in u for u in z.unmodeled)


def test_chapter_1a_string():
    z = parse_zone("[VN1-CR1-4][RG2-8][CPIO]")
    assert z.regime_hint == "1A" and z.base_zone is None and not z.is_r1_family


def test_manufacturing_mr1_is_not_r1():
    assert not parse_zone("MR1-1").is_r1_family


def test_r2_and_re_families():
    assert parse_zone("R2-1").family == "R2" and parse_zone("R2-1").is_modeled
    assert parse_zone("RE15-1").family == "RE" and parse_zone("RE40-1-H").family == "RE"
    assert not parse_zone("RE40-1-H").is_modeled  # -H supplemental district is listed as unmodeled
    assert parse_zone("RD2-1").family is None and not parse_zone("RD2-1").is_modeled
    assert parse_zone("RE12-1").family is None  # not an RE designation in 12.07.01 C.4


def test_condition_notes_name_each_condition():
    from app.engine.assess import _condition_notes

    assert "can only lower the height" in _condition_notes(parse_zone("R2-2D"))
    notes = _condition_notes(parse_zone("[Q]R2-1"))
    assert "Q (Qualified)" in notes and "Tentative" not in notes
    assert _condition_notes(parse_zone("R1-1")) == ""


def test_chapter_1a_zone_string_parts():
    from app.parcel.zone import parse_ch1a

    z = parse_ch1a("[H3-MU3-3][RX2-2L][CPIO]")
    assert (z.form, z.frontage, z.standards, z.use, z.density, z.supplemental) == (
        "H3",
        "MU3",
        "3",
        "RX2",
        "2L",
        ("CPIO",),
    )
    assert parse_ch1a("[VF2-WH1-4][P1-FA]").density == "FA"
    assert parse_ch1a("R1-1") is None
