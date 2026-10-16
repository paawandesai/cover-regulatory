"""Struck-through text in a redlined PDF is dropped; underlined (added) text is kept."""

from app.ingest.regtext.ingest import not_struck


def char(x0, x1, top=100.0, bottom=110.0):
    return {"object_type": "char", "x0": x0, "x1": x1, "top": top, "bottom": bottom}


def test_line_through_the_middle_drops_the_character():
    segs = [(10.0, 50.0, 105.0)]
    assert not not_struck(char(20, 26), segs)


def test_underline_and_unrelated_lines_keep_the_character():
    underline = [(10.0, 50.0, 110.5)]
    assert not_struck(char(20, 26), underline)
    elsewhere = [(60.0, 90.0, 105.0)]
    assert not_struck(char(20, 26), elsewhere)


def test_non_characters_are_kept():
    assert not_struck({"object_type": "line"}, [(0.0, 100.0, 105.0)])
