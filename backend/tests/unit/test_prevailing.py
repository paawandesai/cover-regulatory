"""The prevailing front yard's group rule (LAMC 12.08 C.1) on hand-made lots."""

from app.engine.prevailing import Lot, shallowest_group


def lots(*pairs):
    """(front yard, frontage) pairs laid out side by side."""
    out, a = [], 0.0
    for k, (yard, width) in enumerate(pairs):
        out.append(Lot(f"L{k}", a, a + width, 0.0, 120.0, "R1-1", yard=yard))
        a += width
    return out


def test_group_within_ten_feet_with_forty_percent():
    face = lots((20, 50), (24, 50), (28, 50), (45, 50), (50, 50))
    best = shallowest_group(face, 250)
    assert best["lots"] == ["L0", "L1", "L2"] and best["average_ft"] == 24.0 and best["share"] == 0.6


def test_shallowest_of_two_qualifying_groups():
    face = lots((10, 50), (15, 50), (30, 50), (35, 50), (38, 50))
    # 10/15 is 40% of 250 ft; 30/35/38 is 60%. The shallower average wins.
    assert shallowest_group(face, 250)["average_ft"] == 12.5


def test_no_group_reaches_forty_percent():
    face = lots((10, 50), (25, 50), (40, 50), (55, 50), (70, 50))
    assert shallowest_group(face, 250) is None


def test_vacant_frontage_still_counts():
    # Two developed lots of 50 ft on a 300 ft frontage are 33%: not enough.
    face = lots((20, 50), (22, 50))
    assert shallowest_group(face, 300) is None
