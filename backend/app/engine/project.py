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

    @property
    def empty(self) -> bool:
        return all(v is None for v in (self.height_ft, self.floor_area_sqft, self.second_unit, self.second_unit_sqft))


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


def check_project(items, p: ProjectInputs) -> dict:
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
        extra = " A guest house counts toward this total." if p.second_unit == "guest_house" else ""
        checks.append(
            _check(
                "floor_area",
                f"Floor area {p.floor_area_sqft:,.0f} sq ft",
                rfa,
                None if limit is None else p.floor_area_sqft <= limit,
                (
                    f"Maximum {limit:,.0f} sq ft of residential floor area."
                    if limit is not None
                    else "The floor area limit is not modeled for this lot."
                )
                + extra,
            )
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


def summarize(items, ctx) -> dict:
    """Counts by label, a one-paragraph answer, and the decision paths an architect would weigh."""
    by = _by_id(items)
    counts: dict[str, int] = {}
    for i in items:
        counts[i.label] = counts.get(i.label, 0) + 1
    kinds = {o["kind"] for o in ctx.overlays}

    rfa, h = _num(by.get("max_rfa")), _num(by.get("max_height"))
    yards = [_num(by.get(k)) for k in ("front_yard", "side_yard", "rear_yard")]
    if rfa is not None and h is not None and None not in yards:
        house = (
            f"A single-family home of up to {rfa:,.0f} sq ft and {h:g} ft, with yards of {yards[0]:g} ft front, "
            f"{yards[1]:g} ft each side and {yards[2]:g} ft rear."
        )
    else:
        names = {"max_rfa": "floor area", "max_height": "height", "front_yard": "yard"}
        missing = [n for k, n in names.items() if k in by and by[k].value is None]
        joined = ", ".join(missing[:-1]) + " and " + missing[-1] if len(missing) > 1 else "".join(missing)
        house = "A single-family home. " + (
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
                        f"State ADU: up to {st:,.0f} sq ft, 4 ft side and rear setbacks, 16 ft. The City must approve it, "
                        "and the floor area limit can't stop it."
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
                        "Rebuild under the emergency orders: like-for-like (EO 1), or EO 8 in the Coastal Zone. Only for a "
                        "building damaged or destroyed by the fire."
                    ),
                    "Build new under the standard rules shown here.",
                ],
            }
        )
    return {"answer": answer, "confidence": confidence, "counts": counts, "paths": paths}
