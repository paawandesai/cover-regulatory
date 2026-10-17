"""Client reports: a frozen copy of one assessment, readable by link only after a licensed reviewer signs it.

Anyone with the demo invite can ask for a report; it is stored as "awaiting sign-off" and its link shows nothing
but that status. A reviewer (admin login) previews it, then signs with their name and license number, which
unlocks the link. The report keeps the assessment exactly as it was when created, with the date, every value's
label and citations, the disclaimers and the AI disclosure. Only the APN is stored, never a typed address."""

import json
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field

from app.api import ratelimit, reviewers
from app.api.auth import require_admin
from app.db.connection import connect

router = APIRouter()
TOKEN = Path(pattern=r"^[A-Za-z0-9_-]{16,64}$")
SIGN_STATEMENT = (
    "I have reviewed this assessment against the cited regulations and the parcel, and I take professional "
    "responsibility for sharing it with the client."
)


class ProjectIn(BaseModel):
    height_ft: float | None = Field(None, gt=0, le=100)
    floor_area_sqft: float | None = Field(None, gt=0, le=100_000)
    second_unit: Literal["detached", "attached", "jadu", "guest_house"] | None = None
    second_unit_sqft: float | None = Field(None, gt=0, le=10_000)
    second_unit_bedrooms: int | None = Field(None, ge=0, le=10)
    covered_parking_sqft: float | None = Field(None, gt=0, le=5_000)
    parking_in_rear: bool | None = None
    accessory_sqft: float | None = Field(None, gt=0, le=5_000)
    tall_ceiling_sqft: float | None = Field(None, gt=0, le=50_000)
    side_wall_ft: float | None = Field(None, gt=0, le=500)


class ReportIn(BaseModel):
    apn: str = Field(pattern=r"^[0-9]{10}$", description="The APN of an assessed parcel (not an address)")
    project: ProjectIn = ProjectIn()


class SignIn(BaseModel):
    signer_name: str = Field(min_length=3, max_length=120)
    signer_license: str = Field(min_length=3, max_length=60, description="License type and number")
    note: str | None = Field(None, max_length=2000)
    statement_accepted: bool


def _full(row: dict) -> dict:
    return {
        "token": row["token"],
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "apn": row["apn"],
        "project": row["project"],
        "snapshot": row["snapshot"],
        "statement": SIGN_STATEMENT,
        "signed": {
            "name": row["signer_name"],
            "license": row["signer_license"],
            "note": row["signer_note"],
            "at": row["signed_at"].isoformat(),
        }
        if row["status"] == "signed"
        else None,
    }


def _public(row: dict) -> dict:
    """Before sign-off the link shows only that it is waiting; nothing of the assessment."""
    if row["status"] == "signed":
        return _full(row)
    return {"token": row["token"], "status": row["status"], "created_at": row["created_at"].isoformat()}


@router.post("/api/reports", status_code=201)
def create_report(body: ReportIn, request: Request):
    from app.engine.assess import assess
    from app.engine.project import ProjectInputs
    from app.parcel.resolve import ParcelNotFound

    ratelimit.hit(request, "report")
    project = body.project.model_dump()
    try:
        result = assess(body.apn, ProjectInputs(**project))
    except ParcelNotFound as e:
        raise HTTPException(404, str(e)) from e
    if result["status"] != "ok":
        raise HTTPException(422, "only an assessed R1 parcel can be reported")
    token = secrets.token_urlsafe(18)
    with connect() as conn:
        conn.execute(
            "INSERT INTO report (token, apn, project, snapshot) VALUES (%s, %s, %s, %s)",
            (token, result["parcel"]["apn"], json.dumps(project), json.dumps(result, default=str)),
        )
        conn.commit()
    return {"token": token, "status": "awaiting_signoff"}


@router.get("/api/reports/{token}")
def get_report(token: Annotated[str, TOKEN]):
    with connect() as conn:
        row = conn.execute("SELECT * FROM report WHERE token = %s", (token,)).fetchone()
    if row is None or row["status"] == "withdrawn":
        raise HTTPException(404, "report not found")
    return _public(row)


@router.get("/api/admin/reports")
def list_reports(
    _admin: Annotated[str, Depends(require_admin)],
    status: Literal["awaiting_signoff", "signed", "withdrawn"] = "awaiting_signoff",
):
    with connect() as conn:
        return conn.execute(
            """SELECT token, created_at, apn, project, status, signer_name, signer_license, signed_by, signed_at,
                      snapshot->'summary'->>'answer' AS answer
               FROM report WHERE status = %s ORDER BY created_at DESC LIMIT 200""",
            (status,),
        ).fetchall()


@router.get("/api/admin/reports/{token}")
def preview_report(token: Annotated[str, TOKEN], _admin: Annotated[str, Depends(require_admin)]):
    """The reviewer sees the full report before signing."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM report WHERE token = %s", (token,)).fetchone()
    if row is None:
        raise HTTPException(404, "report not found")
    return _full(row)


@router.post("/api/admin/reports/{token}/sign")
def sign_report(token: Annotated[str, TOKEN], body: SignIn, admin: Annotated[str, Depends(require_admin)]):
    if not body.statement_accepted:
        raise HTTPException(422, "the sign-off statement must be accepted")
    with connect() as conn:
        row = conn.execute(
            """UPDATE report SET status = 'signed', signer_name = %s, signer_license = %s, signer_note = %s,
                      signed_by = %s, signed_at = now()
               WHERE token = %s AND status = 'awaiting_signoff' RETURNING token, status""",
            (body.signer_name.strip(), body.signer_license.strip(), body.note, admin, token),
        ).fetchone()
        if row:
            reviewers.record(
                conn,
                admin,
                "report_signed",
                "report",
                reviewers.token_ref(token),
                {"license": body.signer_license.strip()},
            )
        conn.commit()
    if row is None:
        raise HTTPException(409, "report is not awaiting sign-off")
    return row


@router.post("/api/admin/reports/{token}/withdraw")
def withdraw_report(token: Annotated[str, TOKEN], admin: Annotated[str, Depends(require_admin)]):
    with connect() as conn:
        row = conn.execute(
            "UPDATE report SET status = 'withdrawn' WHERE token = %s AND status <> 'withdrawn' RETURNING token, status",
            (token,),
        ).fetchone()
        if row:
            reviewers.record(conn, admin, "report_withdrawn", "report", reviewers.token_ref(token))
        conn.commit()
    if row is None:
        raise HTTPException(404, "report not found")
    return row
