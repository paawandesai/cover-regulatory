"""Parse City of Los Angeles zone strings into parts the rule engine can reason about.

Chapter I strings look like "[Q]R1-1VL-O-CUGU": optional prefixes for tentative (T), qualified (Q)
or (F) classifications, a base zone, a height district (number plus optional L/VL/XL/SS and a "D"
development limitation), then supplemental-use district suffixes.

Chapter 1A strings are bracketed groups such as "[VN1-CR1-4][RG2-8][CPIO]". We only detect those;
we do not model them.

The parser never drops information silently: anything that changes the rules and is not modeled is
listed in `unmodeled`.
"""

import re
from dataclasses import dataclass, field

_CH1A = re.compile(r"^\[[A-Z0-9]+-[A-Z0-9.]+-[A-Z0-9.]+\](\[[^\]]+\])+$")
_PREFIX = re.compile(r"^(\(T\)|\[T\]|\(Q\)|\[Q\]|\(F\)|\[F\]|Q(?=[A-Z])|T(?=[A-Z]))")
_HEIGHT = re.compile(r"^(?P<num>\d)(?P<suffix>XL|VL|SS|L)?(?P<d>D)?$")

R1_VARIATION = re.compile(r"^R1(?P<kind>[VFRH])(?P<num>\d)$")
RE_ZONE = re.compile(r"^RE(?P<size>9|11|15|20|40)$")

# Supplemental districts that change development standards on R1 lots. Detected and flagged, not modeled.
SUPPLEMENTAL_DESCRIPTIONS = {
    "HCR": "Hillside Construction Regulation District",
    "RFA": "Residential Floor Area District",
    "HPOZ": "Historic Preservation Overlay Zone",
    "CDO": "Community Design Overlay District",
    "CPIO": "Community Plan Implementation Overlay District",
    "RIO": "River Improvement Overlay District",
    "O": "Oil Drilling District",
    "K": "Equinekeeping District",
    "CUGU": "Clean Up Green Up District",
    "G": "Surface Mining District",
    "RG": "Rear Detached Garage District",
    "CA": "Commercial and Artcraft District",
    "SP": "Specific Plan",
    "TCN": "Transit Core District",
}


@dataclass(frozen=True)
class ParsedZone:
    raw: str
    regime_hint: str  # "I" or "1A", from the shape of the string alone
    prefixes: tuple[str, ...] = ()
    base_zone: str | None = None
    height_district: str | None = None  # e.g. "1", "1VL"
    development_limitation: bool = False  # the "D" in e.g. "R1-1D"
    supplemental: tuple[str, ...] = ()
    unmodeled: tuple[str, ...] = field(default=())

    @property
    def is_r1_family(self) -> bool:
        return self.base_zone is not None and (self.base_zone == "R1" or bool(R1_VARIATION.match(self.base_zone)))

    @property
    def family(self) -> str | None:
        """The modeled zone family: "R1" (with its variations), "R2" or "RE"; None for any other zone."""
        if self.is_r1_family:
            return "R1"
        if self.base_zone == "R2":
            return "R2"
        if RE_ZONE.match(self.base_zone or ""):
            return "RE"
        return None

    @property
    def is_modeled(self) -> bool:
        """A modeled zone (R1 and its variations, R2, RE9-RE40) with no qualifier, condition or supplemental district."""
        return self.family is not None and not self.unmodeled

    @property
    def is_plain_r1(self) -> bool:
        """Base R1 with no qualifier, condition, variation or supplemental district: what this PoC models fully."""
        return self.base_zone == "R1" and not self.unmodeled


def parse_zone(raw: str) -> ParsedZone:
    s = (raw or "").strip().upper()
    if _CH1A.match(s):
        return ParsedZone(raw=raw, regime_hint="1A", unmodeled=("Chapter 1A zone string",))

    prefixes: list[str] = []
    while True:
        m = _PREFIX.match(s)
        if not m:
            break
        prefixes.append(m.group(1).strip("()[]"))
        s = s[m.end() :]

    parts = s.split("-") if s else []
    base = parts[0] if parts else None
    rest = parts[1:]

    height = None
    d_limit = False
    if rest and _HEIGHT.match(rest[0]):
        hm = _HEIGHT.match(rest[0])
        height = hm.group("num") + (hm.group("suffix") or "")
        d_limit = bool(hm.group("d"))
        rest = rest[1:]
    supplemental = tuple(p.rstrip("#") for p in rest if p)

    unmodeled: list[str] = []
    if "T" in prefixes:
        unmodeled.append("Tentative [T] classification: conditions in the zone change ordinance apply")
    if "Q" in prefixes:
        unmodeled.append("Qualified [Q] condition: parcel-specific ordinance not modeled")
    if "F" in prefixes:
        unmodeled.append("(F) funded improvement classification not modeled")
    if d_limit:
        unmodeled.append("D development limitation: parcel-specific ordinance not modeled")
    modeled_base = bool(base and (base in ("R1", "R2") or R1_VARIATION.match(base) or RE_ZONE.match(base)))
    if base and not modeled_base:
        unmodeled.append(f"Zone {base} is not modeled (only R1, R2 and RE)")
    if modeled_base and height is None:
        unmodeled.append("No height district in zone string")
    for sup in supplemental:
        desc = SUPPLEMENTAL_DESCRIPTIONS.get(sup, "supplemental district")
        unmodeled.append(f"-{sup} ({desc}) not modeled")
    if any("#" in p for p in parts):
        unmodeled.append("Footnote marker (#) in zone string")

    return ParsedZone(
        raw=raw,
        regime_hint="I",
        prefixes=tuple(prefixes),
        base_zone=base,
        height_district=height,
        development_limitation=d_limit,
        supplemental=supplemental,
        unmodeled=tuple(unmodeled),
    )


_CH1A_BRACKETS = re.compile(r"\[([^\]]+)\]")


@dataclass(frozen=True)
class Ch1aZone:
    """A Chapter 1A zone string, [FORM-FRONTAGE-STANDARDS][USE-DENSITY][supplemental...] (LAMC Ch. 1A Sec. 1.3.1)."""

    raw: str
    form: str
    frontage: str
    standards: str
    use: str
    density: str
    supplemental: tuple[str, ...] = ()


def parse_ch1a(raw: str) -> Ch1aZone | None:
    groups = _CH1A_BRACKETS.findall((raw or "").strip().upper())
    if len(groups) < 2:
        return None
    built, activity = groups[0].split("-"), groups[1].split("-")
    if len(built) != 3 or len(activity) != 2:
        return None
    supplemental = tuple(p for g in groups[2:] for p in g.split("-") if p)
    return Ch1aZone(raw, *built, *activity, supplemental)
