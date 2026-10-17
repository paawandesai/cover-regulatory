"""Specific plans the engine has read. A plan listed here is applied; any other specific plan or HPOZ on the lot is
flagged and turns the zone's values into interpretations, because its standards can override the zone's.

Each entry records what the plan does to a residential lot, from the plan's loaded text, and the text it cites. The
reading was done by Claude Opus 5.5 (via Claude Code) on 2026-10-17 on Paawan's instruction; it is an AI reading, so
the item it produces is labelled Interpretation.
"""

from app.engine.item import Item, chunk_citation

WLA_TIMP = "WEST LOS ANGELES TRANSPORTATION IMPROVEMENT AND MITIGATION"


def _wla_timp(conn) -> Item:
    cites = (
        chunk_citation(conn, "WLA TIMP Section 2", "The regulations of the Specific Plan are in addition")
        + chunk_citation(conn, "WLA TIMP Section 5", "No permit shall be issued by LADBS")
        + chunk_citation(conn, "WLA TIMP Section 5", "Exemptions. The following Projects")
        + chunk_citation(conn, "WLA TIMP SEC. 19.19", "Single family detached homes")
        + chunk_citation(conn, "WLA TIMP SEC. 19.19", "Accessory dwelling units to single family homes")
    )
    return Item(
        "plan_wla_timp",
        "plan",
        "West LA Transportation Improvement and Mitigation Specific Plan",
        "Transportation fee; no envelope rules",
        None,
        "interpretive" if cites else "uncited",
        rule_id="PLAN_WLA_TIMP",
        coverage=1.0 if cites else None,
        explanation=(
            "This specific plan is a transportation fee program. Its 13 sections set no yard, height or floor area "
            "standards, so the zone's values above apply; its rules are in addition to the zoning code (Section 2). "
            "Before LADBS issues a permit for a new home, the applicant files with LADOT and pays the Transportation "
            "Impact Assessment fee (Section 5.A, fee table in LAMC 19.19; $8,847 per single-family home in the 2019 "
            "copy loaded here, indexed every year and amended in 2026, so check the current amount). Exempt: work "
            "that adds no floor area or change of use, additions and alterations to a home that add no dwelling unit, "
            "and demolitions (Section 5.B), and ADUs to single-family homes (LAMC 19.19 D.1.e)."
        ),
        citations=cites,
    )


KNOWN = {WLA_TIMP: _wla_timp}


def unmodeled_plans(ctx) -> list[str]:
    """Names of the specific plans and HPOZs on the lot that are not in KNOWN."""
    return sorted(
        {o["name"] for o in ctx.overlays if o["kind"] in ("specific_plan", "hpoz") and o["name"] not in KNOWN}
    )


def plan_items(conn, ctx) -> list[Item]:
    names = sorted({o["name"] for o in ctx.overlays if o["kind"] == "specific_plan" and o["name"] in KNOWN})
    return [KNOWN[n](conn) for n in names]
