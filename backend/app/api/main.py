"""HTTP API. Run: uv run uvicorn app.api.main:app --no-access-log

The default access log is off because it prints query strings (addresses, questions). The middleware below
logs only the route template, status code and an opaque request id."""

import hashlib
import hmac
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api import ratelimit, reviewers
from app.api.auth import require_admin
from app.api.chat import router as chat_router
from app.api.reports import router as reports_router
from app.config import get_settings
from app.db.connection import connect

log = logging.getLogger("app.api")
app = FastAPI(
    title="Home Building Regulatory Engine (PoC)", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None
)
app.include_router(reports_router)
app.include_router(chat_router)


INVITE_COOKIE = "demo_invite"
_OPEN_PATHS = {"/api/health", "/api/invite"}


def _invite_token(code: str) -> str:
    # The cookie holds a keyed hash of the code, never the code itself.
    return hmac.new(code.encode(), b"regengine-demo-invite", hashlib.sha256).hexdigest()


@app.middleware("http")
async def invite_gate(request: Request, call_next):
    """Hosted demo only: with DEMO_INVITE_CODE set, API routes need the invite cookie."""
    code = get_settings().demo_invite_code
    # The raw ASGI path: request.url is rebuilt from the Host header, which a client controls.
    path = request.scope["path"]
    # A signed client report opens by its unguessable link without the invite, so the client can read it.
    report_link = request.method == "GET" and path.startswith("/api/reports/")
    if code and path.startswith("/api/") and path not in _OPEN_PATHS and not report_link:
        cookie = request.cookies.get(INVITE_COOKIE, "")
        if not hmac.compare_digest(cookie, _invite_token(code.get_secret_value())):
            return JSONResponse({"detail": "invite_required"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def privacy_and_headers(request: Request, call_next):
    rid = uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    log.info(
        "rid=%s %s %s %s %.0fms",
        rid,
        request.method,
        getattr(route, "path", "unmatched"),
        response.status_code,
        (time.perf_counter() - t0) * 1000,
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["X-Request-Id"] = rid
    response.headers["Cache-Control"] = "no-store"
    return response


# --- health -----------------------------------------------------------------------------------------------


@app.get("/api/health")
def health():
    """Configuration and last-success timestamps only. Never calls the model provider or reads secrets."""
    s = get_settings()
    with connect() as conn:
        row = conn.execute(
            """SELECT (SELECT max(ran_at) FROM ingest_run) AS last_ingest,
                      (SELECT max(finished_at) FROM extraction_run WHERE status = 'ok') AS last_extraction,
                      (SELECT count(*) FROM reg_chunk) AS chunks,
                      (SELECT count(*) FROM reg_chunk WHERE embedding IS NULL) AS chunks_unembedded,
                      (SELECT count(*) FROM rule_fragment WHERE status = 'approved') AS approved_rules,
                      (SELECT count(*) FROM rule_fragment WHERE status = 'pending') AS pending_rules,
                      (SELECT max(retrieved_at) FROM source) AS last_dataset_fetch"""
        ).fetchone()
    return {
        "status": "ok",
        "checked_at": datetime.now(UTC).isoformat(),
        "llm_provider": s.llm_provider,
        "llm_model_id": s.llm_model_id,
        "llm_key_configured": s.anthropic_api_key is not None,
        "embedding_model": s.embedding_model,
        "admin_configured": bool(s.admin_username and s.admin_password_scrypt),
        **{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()},
    }


class InviteIn(BaseModel):
    code: str = Field(max_length=200)


@app.get("/api/invite")
def invite_status(request: Request):
    code = get_settings().demo_invite_code
    if code is None:
        return {"required": False, "ok": True}
    ok = hmac.compare_digest(request.cookies.get(INVITE_COOKIE, ""), _invite_token(code.get_secret_value()))
    return {"required": True, "ok": ok}


@app.post("/api/invite")
def invite(body: InviteIn, request: Request, response: Response):
    code = get_settings().demo_invite_code
    if code is None:
        return {"ok": True}
    ratelimit.check(request, "invite_fail")
    if not hmac.compare_digest(body.code.strip().encode(), code.get_secret_value().encode()):
        ratelimit.record(request, "invite_fail")
        raise HTTPException(403, "wrong invite code")
    response.set_cookie(
        INVITE_COOKIE,
        _invite_token(code.get_secret_value()),
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
    )
    return {"ok": True}


# --- regulation text --------------------------------------------------------------------------------------


@app.get("/api/chunks/{chunk_id:path}")
def get_chunk(chunk_id: str):
    with connect() as conn:
        row = conn.execute(
            """SELECT c.id, c.section_id, c.heading, c.text, c.source_url, c.retrieved_at, c.effective_date,
                      c.code_chapter, c.content_hash, c.mock, d.title AS document_title, d.publisher,
                      d.manual_retrieval, d.effective_note
               FROM reg_chunk c JOIN reg_document d ON d.id = c.document_id WHERE c.id = %s""",
            (chunk_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "no such chunk")
    from app.engine.links import deep_link

    return row | {"source_url": deep_link(row["source_url"], row["section_id"])}


@app.get("/api/search")
def search_chunks(
    q: str = Query(min_length=2, max_length=300),
    k: int = Query(8, ge=1, le=25),
    jurisdiction: str | None = Query(None, pattern="^(city|county)$"),
):
    from app.search.search import search  # loads the embedding model on first use

    return [h.__dict__ for h in search(q, k=k, jurisdiction=jurisdiction)]


# --- assessment -------------------------------------------------------------------------------------------


@app.get("/api/assess")
def assess_parcel(
    q: str = Query(min_length=3, max_length=200, description="APN or street address"),
    height_ft: float | None = Query(None, gt=0, le=100, description="Proposed house height"),
    floor_area_sqft: float | None = Query(None, gt=0, le=100_000, description="Proposed residential floor area"),
    second_unit: Literal["detached", "attached", "jadu", "guest_house"] | None = Query(None),
    second_unit_sqft: float | None = Query(None, gt=0, le=10_000),
    second_unit_bedrooms: int | None = Query(None, ge=0, le=10),
    covered_parking_sqft: float | None = Query(None, gt=0, le=5_000, description="Required covered parking area"),
    parking_in_rear: bool | None = Query(None, description="All covered parking in the rear half or 55 ft back"),
    accessory_sqft: float | None = Query(
        None, gt=0, le=5_000, description="Detached accessory buildings under 200 sq ft"
    ),
    tall_ceiling_sqft: float | None = Query(None, gt=0, le=50_000, description="Floor area under ceilings over 14 ft"),
    side_wall_ft: float | None = Query(None, gt=0, le=500, description="Longest continuous side wall over 14 ft high"),
):
    """Project inputs are optional; they only change which limits are checked and the side yard's design height."""
    from app.engine.assess import assess
    from app.engine.project import ProjectInputs
    from app.parcel.resolve import ParcelNotFound

    project = ProjectInputs(
        height_ft,
        floor_area_sqft,
        second_unit,
        second_unit_sqft,
        second_unit_bedrooms,
        covered_parking_sqft,
        parking_in_rear,
        accessory_sqft,
        tall_ceiling_sqft,
        side_wall_ft,
    )
    try:
        return assess(q, project)
    except ParcelNotFound as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/parcels/{apn}/nearby")
def nearby_parcels(apn: str = Path(pattern=r"^[0-9]{10}$"), radius_m: float = Query(60, ge=10, le=150)):
    """Outlines of neighbouring parcels for map context. Geometry and APN only, no situs or assessor fields."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT n.apn, ST_AsGeoJSON(n.geom, 7)::json AS geometry
               FROM parcel p JOIN parcel n
                 ON n.apn <> p.apn AND ST_DWithin(n.geom::geography, p.geom::geography, %s)
               WHERE p.apn = %s LIMIT 400""",
            (radius_m, apn),
        ).fetchall()
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"apn": r["apn"]}, "geometry": r["geometry"]} for r in rows],
    }


class FeedbackIn(BaseModel):
    apn: str | None = Field(default=None, max_length=20, pattern=r"^[0-9-]+$")
    item_id: str | None = Field(default=None, max_length=60)
    kind: Literal["wrong_value", "missing_rule", "bad_citation", "other"]
    comment: str | None = Field(default=None, max_length=2000)


@app.post("/api/feedback", status_code=202)
def feedback(body: FeedbackIn, request: Request):
    """Queued for a reviewer. Feedback never edits rules, prompts or retrieval."""
    ratelimit.hit(request, "feedback")
    with connect() as conn:
        fid = conn.execute(
            "INSERT INTO feedback (apn, item_id, kind, comment) VALUES (%s,%s,%s,%s) RETURNING id",
            (body.apn, body.item_id, body.kind, body.comment),
        ).fetchone()["id"]
        conn.commit()
    return {"id": fid, "status": "queued for review"}


@app.get("/api/admin/feedback")
def list_feedback(
    _admin: Annotated[str, Depends(require_admin)],
    status: Literal["new", "reviewed", "dismissed"] = "new",
):
    with connect() as conn:
        return conn.execute("SELECT * FROM feedback WHERE status = %s ORDER BY id DESC LIMIT 500", (status,)).fetchall()


class FeedbackDecision(BaseModel):
    status: Literal["reviewed", "dismissed"]


@app.post("/api/admin/feedback/{fid}")
def decide_feedback(fid: int, body: FeedbackDecision, admin: Annotated[str, Depends(require_admin)]):
    """Marks a note as handled. It never touches a rule: rules change only through a fragment review decision."""
    with connect() as conn:
        row = conn.execute(
            "UPDATE feedback SET status = %s, reviewed_by = %s, reviewed_at = now() WHERE id = %s RETURNING id, status",
            (body.status, admin, fid),
        ).fetchone()
        if row:
            reviewers.record(conn, admin, f"feedback_{body.status}", "feedback", fid)
        conn.commit()
    if not row:
        raise HTTPException(404, "feedback not found")
    return row


# --- admin review -----------------------------------------------------------------------------------------


@app.get("/api/admin/fragments")
def list_fragments(
    _admin: Annotated[str, Depends(require_admin)],
    status: Literal["pending", "approved", "rejected", "invalid"] = "pending",
    family: str | None = None,
):
    with connect() as conn:
        return conn.execute(
            """SELECT f.id, f.rule_family, f.parameter, f.applies_to, f.conditions, f.value_numeric, f.unit,
                      f.value_text, f.source_quote, f.quote_start, f.quote_end, f.validation, f.status,
                      f.reviewed_by, f.reviewed_at, f.review_note, f.chunk_id, c.section_id, c.text AS chunk_text,
                      c.source_url, r.served_model, r.prompt_version,
                      v.recommendation AS check_recommendation, v.note AS check_note, v.checks, v.checked_on
               FROM rule_fragment f JOIN reg_chunk c ON c.id = f.chunk_id JOIN extraction_run r ON r.id = f.run_id
               LEFT JOIN fragment_verification v ON v.fragment_id = f.id
               WHERE f.status = %s AND (%s::text IS NULL OR f.rule_family = %s)
               ORDER BY c.section_id, f.id""",
            (status, family, family),
        ).fetchall()


class Decision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=2000)


@app.post("/api/admin/fragments/{fragment_id}")
def decide(fragment_id: int, body: Decision, admin: Annotated[str, Depends(require_admin)]):
    """A reviewer's decision. Only pending fragments can be approved; invalid ones failed a deterministic check
    and can only be rejected. The chunk must still match the text the fragment was extracted from."""
    with connect() as conn:
        f = conn.execute(
            """SELECT f.status, f.chunk_hash, c.content_hash FROM rule_fragment f
               JOIN reg_chunk c ON c.id = f.chunk_id WHERE f.id = %s FOR UPDATE""",
            (fragment_id,),
        ).fetchone()
        if f is None:
            raise HTTPException(404, "no such fragment")
        if body.decision == "approved" and f["status"] != "pending":
            raise HTTPException(409, f"cannot approve a fragment with status {f['status']}")
        if body.decision == "approved" and f["chunk_hash"] != f["content_hash"]:
            raise HTTPException(409, "the source text changed since extraction; re-extract first")
        conn.execute(
            """UPDATE rule_fragment SET status=%s, reviewed_by=%s, reviewed_at=now(), review_note=%s
               WHERE id=%s""",
            (body.decision, admin, body.note, fragment_id),
        )
        reviewers.record(
            conn,
            admin,
            f"fragment_{body.decision}",
            "rule_fragment",
            fragment_id,
            {"from": f["status"], "note": body.note},
        )
        conn.commit()
    return {"id": fragment_id, "status": body.decision, "reviewed_by": admin}


# --- reviewers and audit ----------------------------------------------------------------------------------


@app.get("/api/admin/me")
def whoami(admin: Annotated[str, Depends(require_admin)]):
    with connect() as conn:
        r = conn.execute("SELECT display_name FROM reviewer WHERE username = %s", (admin,)).fetchone()
    return {"username": admin, "display_name": r["display_name"] if r else None, "named": r is not None}


@app.get("/api/admin/audit")
def audit(
    _admin: Annotated[str, Depends(require_admin)],
    object_type: Literal["rule_fragment", "feedback", "report", "reviewer"] | None = None,
    actor: str | None = Query(None, max_length=40),
    limit: int = Query(200, ge=1, le=1000),
):
    """Every review action, newest first. The log cannot be edited or deleted (a database trigger refuses)."""
    with connect() as conn:
        return conn.execute(
            """SELECT a.id, a.at, a.actor, r.display_name, a.action, a.object_type, a.object_id, a.detail
               FROM audit_log a LEFT JOIN reviewer r ON r.username = a.actor
               WHERE (%(t)s::text IS NULL OR a.object_type = %(t)s) AND (%(a)s::text IS NULL OR a.actor = %(a)s)
               ORDER BY a.id DESC LIMIT %(n)s""",
            {"t": object_type, "a": actor, "n": limit},
        ).fetchall()


@app.get("/api/admin/sources")
def sources(_admin: Annotated[str, Depends(require_admin)]):
    """The latest scheduled check of each regulation document, so a reviewer sees changed or stale sources."""
    with connect() as conn:
        return conn.execute(
            """SELECT d.id, d.title, d.source_url, d.retrieved_at, d.manual_retrieval,
                      s.checked_at, s.outcome, s.detail,
                      (SELECT count(*) FROM rule_fragment f JOIN reg_chunk c ON c.id = f.chunk_id
                        WHERE c.document_id = d.id AND f.status = 'pending') AS pending
               FROM reg_document d
               LEFT JOIN LATERAL (SELECT * FROM source_check s WHERE s.document_id = d.id
                                  ORDER BY s.checked_at DESC LIMIT 1) s ON true
               WHERE NOT d.mock
               ORDER BY (s.outcome IN ('changed', 'failed', 'manual_due')) DESC NULLS LAST, d.title"""
        ).fetchall()
