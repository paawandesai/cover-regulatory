"""Project inputs and the assessment summary. Deterministic: both only compare the user's numbers with the items the
assessment already computed, so every result inherits the label of the value it was checked against."""

from dataclasses import dataclass

ADU_TYPES = ("detached", "attached", "jadu", "guest_house")


@dataclass(frozen=True)
class ProjectInputs:
    height_ft: float | None = None  # proposed house height
    floor_area_sqft: float | None = None  # proposed residential floor area on the lot (house + anything counted)
    second_unit: str | None = None  # one of ADU_TYPES
    second_unit_sqft: float | None = None
    second_unit_bedrooms: int | None = None
    # Floor-area details (LAMC 12.03 "Floor Area, Residential"); floor_area_sqft is then the gross area inside the
    # exterior walls of every building on the lot, and the exemptions below are taken off.
    covered_parking_sqft: float | None = None  # required covered parking (garage or carport)
    parking_in_rear: bool | None = (
        None  # all of it in the rear half, or 55 ft+ from the front (40 ft+ on a through lot)
    )
    accessory_sqft: float | None = None  # detached accessory buildings of 200 sq ft or less, combined
    tall_ceiling_sqft: float | None = None  # floor area under a ceiling over 14 ft, counted twice
    side_wall_ft: float | None = None  # longest continuous side wall over 14 ft high

    @property
    def empty(self) -> bool:
        return all(v is None for v in self.__dict__.values())


def _by_id(items) -> dict:
    return {i.id: i for i in items}


def _num(item) -> float | None:
    return (
        float(item.value)
        if item is not None and isinstance(item.value, int | float) and not isinstance(item.value, bool)
        else None
    )


def _check(cid: str, title: str, basis, fits: bool | None, detail: str) -> dict:
    """fits=None means the limit is not determined here. A fit against an interpretive value still needs checking."""
    if fits is None:
        status = "not_determined"
    elif not fits:
        status = "exceeds"
    else:
        status = "fits" if basis is not None and basis.label == "derived" else "confirm"
    return {
        "id": cid,
        "title": title,
        "status": status,
        "detail": detail,
        "based_on": basis.id if basis is not None else None,
        "label": basis.label if basis is not None else None,
    }


def counted_floor_area(p: ProjectInputs, ex: dict | None, through_lot: bool = False) -> tuple[float, list[str]]:
    """Residential floor area as 12.03 counts it: tall-ceiling area twice, minus the parking and small accessory
    building exemptions. ex holds the reviewed numbers (RFA_EXEMPTIONS); without them nothing is adjusted."""
    total, steps = p.floor_area_sqft, []
    if not ex:
        return total, steps
    if p.tall_ceiling_sqft and ex.get("double_ceiling_ft") is not None:
        total += p.tall_ceiling_sqft
        steps.append(f"+{p.tall_ceiling_sqft:,.0f} counted twice (ceiling over {ex['double_ceiling_ft']:g} ft)")
    if p.covered_parking_sqft and None not in (ex.get("parking_max_sqft"), ex.get("parking_fallback_sqft")):
        cap = ex["parking_max_sqft"] if p.parking_in_rear else ex["parking_fallback_sqft"]
        off = min(p.covered_parking_sqft, cap)
        total -= off
        where = (
            (
                f"at least {ex['parking_through_ft']:g} ft from both fronts"
                if through_lot and ex.get("parking_through_ft")
                else f"in the rear half or at least {ex['parking_front_ft']:g} ft from the front"
            )
            if p.parking_in_rear
            else "nearer the front, so only the lower exemption"
            if p.parking_in_rear is False
            else "location not given, so only the lower exemption"
        )
        steps.append(f"-{off:,.0f} required covered parking ({where}; 200 sq ft per required space)")
    if p.accessory_sqft and ex.get("accessory_total_sqft") is not None:
        off = min(p.accessory_sqft, ex["accessory_total_sqft"])
        total -= off
        steps.append(
            f"-{off:,.0f} detached accessory buildings of {ex.get('accessory_each_sqft') or 200:g} sq ft or less"
        )
    return max(total, 0.0), steps


def check_project(items, p: ProjectInputs, rfa_exemptions: dict | None = None, through_lot: bool = False) -> dict:
    by = _by_id(items)
    checks: list[dict] = []
    if p.height_ft is not None:
        h = by.get("max_height")
        limit = _num(h)
        checks.append(
            _check(
                "height",
                f"House height {p.height_ft:g} ft",
                h,
                None if limit is None else p.height_ft <= limit,
                f"Maximum {limit:g} ft." if limit is not None else "The height limit is not modeled for this lot.",
            )
        )
        side = by.get("side_yard")
        if _num(side) is not None:
            checks.append(
                _check(
                    "side_yard",
                    f"Side yards for a {min(p.height_ft, limit or p.height_ft):g} ft house",
                    side,
                    True,
                    f"At least {_num(side):g} ft each side; the drawn buildable area uses this.",
                )
            )
    if p.floor_area_sqft is not None:
        rfa = by.get("max_rfa")
        limit = _num(rfa)
        counted, steps = counted_floor_area(p, rfa_exemptions, through_lot)
        extra = " A guest house counts toward this total." if p.second_unit == "guest_house" else ""
        how = (
            f" Counted: {p.floor_area_sqft:,.0f} {' '.join(steps)} = {counted:,.0f} sq ft (LAMC 12.03)."
            if steps
            else ""
        )
        checks.append(
            _check(
                "floor_area",
                f"Floor area {counted:,.0f} sq ft counted" if steps else f"Floor area {p.floor_area_sqft:,.0f} sq ft",
                rfa,
                None if limit is None else counted <= limit,
                (
                    f"Maximum {limit:,.0f} sq ft of residential floor area."
                    if limit is not None
                    else "The floor area limit is not modeled for this lot."
                )
                + how
                + extra,
            )
        )
    if p.side_wall_ft is not None:
        side = by.get("side_yard")
        long_wall = p.side_wall_ft > 45 and (p.height_ft is None or p.height_ft > 14)
        checks.append(
            {
                "id": "plane_break",
                "title": f"Side wall {p.side_wall_ft:g} ft long" + (": needs a plane break" if long_wall else ""),
                "status": "confirm"
                if long_wall
                else "fits"
                if side is not None and side.label == "derived"
                else "confirm",
                "detail": (
                    "Over 45 ft long and over 14 ft high, so it needs an offset (plane break) at least 5 ft deep beyond "
                    "the required side yard and at least 10 ft long (LAMC 12.08 C.2(a)). Show it on the plans."
                    if long_wall
                    else "No plane break needed: walls need one only when over 14 ft high and over 45 ft long "
                    "(LAMC 12.08 C.2(a))."
                ),
                "based_on": side.id if side is not None else None,
                "label": side.label if side is not None else None,
            }
        )
    if p.second_unit:
        checks.extend(_second_unit(by, p))
    return {
        "inputs": {k: v for k, v in p.__dict__.items() if v is not None},
        "checks": checks,
    }


def _second_unit(by: dict, p: ProjectInputs) -> list[dict]:
    size = p.second_unit_sqft
    if p.second_unit == "guest_house":
        g = by.get("guest_house")
        allowed = None if g is None or g.value is None else bool(g.value)
        return [
            _check(
                "guest_house",
                "Guest house (no kitchen)",
                g,
                allowed,
                "Allowed on this lot. Guests only, not rented, at most two stories, and it counts toward the floor "
                "area limit."
                if allowed
                else "Not allowed on this lot (it is under 10,000 sq ft). With a kitchen it would be an ADU instead."
                if allowed is False
                else "Not determined.",
            )
        ]
    if p.second_unit == "jadu":
        j = by.get("jadu")
        limit = _num(j)
        return [
            _check(
                "jadu",
                f"Junior ADU{f' {size:,.0f} sq ft' if size else ''}",
                j,
                None if limit is None else (size or 0) <= limit,
                f"Up to {limit:,.0f} sq ft inside the home, with a deed restriction." if limit else "Not determined.",
            )
        ]
    if p.second_unit == "attached":
        a = by.get("adu_attached")
        limit = _num(a)
        if limit is not None and p.second_unit_bedrooms and p.second_unit_bedrooms > 1:
            limit = max(limit, 1000.0)
        return [
            _check(
                "adu_attached",
                f"Attached ADU{f' {size:,.0f} sq ft' if size else ''}",
                a,
                None if limit is None or size is None else size <= limit,
                f"Up to {limit:,.0f} sq ft can't be refused"
                + (" (more than one bedroom)" if p.second_unit_bedrooms and p.second_unit_bedrooms > 1 else "")
                + "; larger is limited by the lot's floor area."
                if limit is not None
                else "Not determined.",
            )
        ]
    # Detached: pick the path the size needs. The state path must be approved; the City path is larger.
    st, lo = by.get("adu_state_detached"), by.get("adu_local_detached")
    st_max, lo_max = _num(st), _num(lo)
    if size is None:
        return [_check("adu_detached", "Detached ADU", st, None, "Enter a size to pick a path.")]
    if st_max is not None and size <= st_max:
        return [
            _check(
                "adu_detached",
                f"Detached ADU {size:,.0f} sq ft",
                st,
                True,
                f"Fits the state ADU (up to {st_max:,.0f} sq ft), which the City must approve ministerially.",
            )
        ]
    if lo_max is not None:
        return [
            _check(
                "adu_detached",
                f"Detached ADU {size:,.0f} sq ft",
                lo,
                size <= lo_max,
                f"Above the state ADU's {st_max:,.0f} sq ft, so the City ordinance path applies (up to {lo_max:,.0f} "
                "sq ft, two stories, and the lot's floor area limit)."
                if st_max is not None
                else f"City ordinance path: up to {lo_max:,.0f} sq ft.",
            )
        ]
    return [_check("adu_detached", f"Detached ADU {size:,.0f} sq ft", st, None, "Not determined.")]


def _adu_height_text(by: dict) -> str:
    h = by.get("adu_height")
    v = _num(h)
    if v is None:
        return "16 ft"
    if h.label == "interpretive" and v > 16:
        return f"16 ft, or {v:g} ft (plus 2 ft for a matching roof pitch) if walking distance to transit is under half a mile"
    return f"{v:g} ft"


def summarize(items, ctx) -> dict:
    """Counts by label, a one-paragraph answer, and the decision paths an architect would weigh."""
    by = _by_id(items)
    counts: dict[str, int] = {}
    for i in items:
        counts[i.label] = counts.get(i.label, 0) + 1
    kinds = {o["kind"] for o in ctx.overlays}

    rfa, h = _num(by.get("max_rfa")), _num(by.get("max_height"))
    units = _num(by.get("dwelling_units"))  # R2: one or two homes (LAMC 12.09)
    what = (
        f"Up to {units:g} home{'s' if units != 1 else ''}"
        + (" (a two-family dwelling or two houses)" if units == 2 else "")
        if units is not None
        else "A single-family home"
    )
    yards = [_num(by.get(k)) for k in ("front_yard", "side_yard", "rear_yard")]
    if rfa is not None and h is not None and None not in yards:
        house = (
            f"{what} of up to {rfa:,.0f} sq ft and {h:g} ft"
            if units is None
            else f"{what}, with up to {rfa:,.0f} sq ft of floor area in all, {h:g} ft high"
        ) + f", with yards of {yards[0]:g} ft front, {yards[1]:g} ft each side and {yards[2]:g} ft rear."
    else:
        names = {"max_rfa": "floor area", "max_height": "height", "front_yard": "yard"}
        missing = [n for k, n in names.items() if k in by and by[k].value is None]
        joined = ", ".join(missing[:-1]) + " and " + missing[-1] if len(missing) > 1 else "".join(missing)
        house = f"{what}. " + (
            f"The {joined} limits are not modeled for this lot (see each value)."
            if missing
            else "Some envelope values are not determined."
        )
    st, lo, j = _num(by.get("adu_state_detached")), _num(by.get("adu_local_detached")), _num(by.get("jadu"))
    at = _num(by.get("adu_attached"))
    kinds_of_adu = []
    if st is not None:
        kinds_of_adu.append(
            f"detached, {st:,.0f} sq ft that the City must approve"
            + (f" or up to {lo:,.0f} under the City ordinance" if lo else "")
        )
    if at is not None:
        kinds_of_adu.append(f"attached, at least {at:,.0f} sq ft")
    extras = []
    if kinds_of_adu:
        extras.append(f"one ADU ({'; or '.join(kinds_of_adu)})")
    if j is not None:
        extras.append(f"one JADU of up to {j:,.0f} sq ft inside the home")
    answer = house + (" Plus " + " and ".join(extras) + " (Gov. Code 66323)." if extras else "")
    g = by.get("guest_house")
    if g is not None and g.value is True:
        answer += " A guest house is also allowed on this lot."
    sb2, split = by.get("sb9_two_unit"), by.get("sb9_lot_split")
    if sb2 is not None and sb2.value:
        answer += (
            " SB 9 may also allow two homes" + (" or a lot split" if split and split.value else "") + ", to confirm."
        )
    elif sb2 is not None and sb2.value is False:
        answer += (
            " SB 9 does not apply in a two-family zone."
            if units is not None
            else " SB 9 is not available here (Executive Order 9)."
        )
    confirm, withheld = counts.get("interpretive", 0), counts.get("withheld", 0)
    parts = []
    if confirm:
        parts.append(f"{confirm} value{'s' if confirm != 1 else ''} to confirm with the City")
    if withheld:
        parts.append(f"{withheld} not modeled here")
    confidence = (
        "Every rule value is derived from reviewed text."
        if not parts
        else "; ".join(parts)[0].upper() + "; ".join(parts)[1:] + "."
    )

    paths: list[dict] = []
    if st is not None:
        lo_item = by.get("adu_local_detached")
        paths.append(
            {
                "id": "adu_path",
                "title": "State ADU or City ADU",
                "options": [
                    (
                        f"State ADU: up to {st:,.0f} sq ft, 4 ft side and rear setbacks, {_adu_height_text(by)}. The City "
                        "must approve it, and the floor area limit can't stop it."
                    ),
                    (
                        f"City ordinance ADU: up to {lo:,.0f} sq ft and two stories, within the lot's floor area limit."
                        + (
                            " Barred here unless exceptions apply (Hillside + fire zone)."
                            if lo_item and lo_item.label == "interpretive" and {"hillside", "vhfhsz"} <= kinds
                            else ""
                        )
                    )
                    if lo
                    else "City ordinance ADU: not determined.",
                ],
            }
        )
    if g is not None and g.value is not None:
        paths.append(
            {
                "id": "guest_or_adu",
                "title": "Guest house or ADU",
                "options": [
                    "Guest house: guests only, no kitchen, not rented, counts toward floor area."
                    if g.value
                    else "Guest house: not allowed on a lot under 10,000 sq ft.",
                    (
                        "ADU: a kitchen is allowed and it can be rented; the state ADU doesn't count against the floor "
                        "area limit."
                    ),
                ],
            }
        )
    if "fire_perimeter_2025" in kinds:
        paths.append(
            {
                "id": "rebuild_or_standard",
                "title": "Fire rebuild order or standard rules",
                "options": [
                    (
                        "Rebuild under the emergency orders: like-for-like (EO 1"
                        + (
                            f", up to about {by['eo1_footprint'].value:,.0f} sq ft of footprint"
                            if by.get("eo1_footprint") and by["eo1_footprint"].value
                            else ", up to 110% of the pre-fire footprint and height"
                        )
                        + ")"
                        + (
                            f", or EO 8 in the Coastal Zone (zoning-compliant, up to {by['eo8_height'].value:g} ft)"
                            if by.get("eo8_height") and by["eo8_height"].value
                            else ""
                        )
                        + ". Only for a building damaged or destroyed by the fire."
                    ),
                    "Build new under the standard rules shown here.",
                ],
            }
        )
    return {"answer": answer, "confidence": confidence, "counts": counts, "paths": paths}
