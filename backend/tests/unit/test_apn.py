import pytest

from app.parcel.apn import InvalidAPN, format_apn, looks_like_apn, normalize_apn


def test_normalize_and_format():
    assert normalize_apn("2004-001-003") == "2004001003"
    assert format_apn("2004 001 003") == "2004-001-003"


def test_invalid():
    with pytest.raises(InvalidAPN):
        normalize_apn("2004-001")


def test_looks_like_apn():
    assert looks_like_apn("2004-001-003")
    assert not looks_like_apn("123 Main St")
