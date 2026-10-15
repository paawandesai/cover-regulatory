"""Los Angeles County Assessor parcel numbers (APN / AIN): 10 digits, displayed as ####-###-###."""

import re

_DIGITS = re.compile(r"\D")


class InvalidAPN(ValueError):
    pass


def normalize_apn(raw: str) -> str:
    """Return the 10-digit APN, accepting dashes, spaces or other separators."""
    digits = _DIGITS.sub("", raw or "")
    if len(digits) != 10:
        raise InvalidAPN("An APN has 10 digits, e.g. 2004-001-003.")
    return digits


def format_apn(apn: str) -> str:
    d = normalize_apn(apn)
    return f"{d[:4]}-{d[4:7]}-{d[7:]}"


def looks_like_apn(text: str) -> bool:
    stripped = (text or "").strip()
    return bool(re.fullmatch(r"[\d\s\-]+", stripped)) and len(_DIGITS.sub("", stripped)) == 10
