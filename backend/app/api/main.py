"""HTTP API. Run: uv run uvicorn app.api.main:app --no-access-log

The default access log is off because it prints query strings (addresses, questions). The middleware below
logs only the route template, status code and an opaque request id."""

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.auth import require_admin
from app.config import get_settings
from app.db.connection import connect

log = logging.getLogger("app.api")
app = FastAPI(title="Home Building Regulatory Engine (PoC)", docs_url="/api/docs", openapi_url="/api/openapi.json")


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
    return row


@app.get("/api/search")
def search_chunks(q: str = Query(min_length=2, max_length=300), k: int = Query(8, ge=1, le=25)):
    from app.search.search import search  # loads the embedding model on first use

    return [h.__dict__ for h in search(q, k=k)]


# --- assessment -------------------------------------------------------------------------------------------


@app.get("/api/assess")
def assess_parcel(q: str = Query(min_length=3, max_length=200, description="APN or street address")):
    from app.engine.assess import assess
    from app.parcel.resolve import ParcelNotFound

    try:
        return assess(q)
    except ParcelNotFound as e:
        raise HTTPException(404, str(e)) from e


class FeedbackIn(BaseModel):
    apn: str | None = Field(default=None, max_length=20, pattern=r"^[0-9-]+$")
    item_id: str | None = Field(default=None, max_length=60)
    kind: Literal["wrong_value", "missing_rule", "bad_citation", "other"]
    comment: str | None = Field(default=None, max_length=2000)


@app.post("/api/feedback", status_code=202)
def feedback(body: FeedbackIn):
    """Queued for a reviewer. Feedback never edits rules, prompts or retrieval."""
    with connect() as conn:
        fid = conn.execute(
            "INSERT INTO feedback (apn, item_id, kind, comment) VALUES (%s,%s,%s,%s) RETURNING id",
            (body.apn, body.item_id, body.kind, body.comment),
        ).fetchone()["id"]
        conn.commit()
    return {"id": fid, "status": "queued for review"}


@app.get("/api/admin/feedback")
def list_feedback(_admin: Annotated[str, Depends(require_admin)]):
    with connect() as conn:
        return conn.execute("SELECT * FROM feedback WHERE status = 'new' ORDER BY id").fetchall()


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
                      c.source_url, r.served_model, r.prompt_version
               FROM rule_fragment f JOIN reg_chunk c ON c.id = f.chunk_id JOIN extraction_run r ON r.id = f.run_id
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
        conn.commit()
    return {"id": fragment_id, "status": body.decision, "reviewed_by": admin}
