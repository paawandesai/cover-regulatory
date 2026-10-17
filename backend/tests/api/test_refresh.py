"""Scheduled source check against the local database, on a throwaway document. Skipped without a database."""

import pytest

try:
    from app.db.connection import connect

    with connect() as _c:
        _c.execute("SELECT 1 FROM source_check LIMIT 1")
except Exception:  # noqa: BLE001
    pytest.skip("database not reachable", allow_module_level=True)

from app.ingest.regtext import refresh as R

DOC = "test_refresh_doc"
QUOTE = "The front yard shall be not less than 20 feet."


@pytest.fixture
def fragment():
    with connect() as conn:
        last = conn.execute("SELECT coalesce(max(id), 0) AS n FROM audit_log").fetchone()["n"]
        conn.execute(
            """INSERT INTO reg_document (id, title, publisher, doc_type, jurisdiction, source_url, retrieved_at,
                   file_sha256) VALUES (%s, 'Test', 'Test', 'ordinance', 'City of Los Angeles', 'https://example.org/t.pdf',
                   now(), 'old')""",
            (DOC,),
        )
        conn.execute(
            """INSERT INTO reg_chunk (id, document_id, section_id, text, source_url, retrieved_at, content_hash, mock)
               VALUES (%s, %s, 'Test 1', %s, 'https://example.org/t.pdf', now(), 'h1', false)""",
            (f"{DOC}#1", DOC, "Intro. " + QUOTE),
        )
        run = conn.execute(
            "INSERT INTO extraction_run (model_id, prompt_version, chunk_ids) VALUES ('test', 'test', '{}') RETURNING id"
        ).fetchone()["id"]
        fid = conn.execute(
            """INSERT INTO rule_fragment (run_id, chunk_id, chunk_hash, rule_family, parameter, source_quote, validation,
                   status, reviewed_by) VALUES (%s, %s, 'h1', 'r1', 'front_yard_min_ft', %s, 'ok', 'approved', 'test')
               RETURNING id""",
            (run, f"{DOC}#1", QUOTE),
        ).fetchone()["id"]
        conn.commit()
    yield fid
    with connect() as conn:
        conn.execute("DELETE FROM reg_document WHERE id = %s", (DOC,))
        conn.execute("DELETE FROM extraction_run WHERE id = %s", (run,))
        conn.execute("DELETE FROM source_check WHERE document_id = %s", (DOC,))
        conn.execute("SET LOCAL regengine.audit_maintenance = 'on'")
        conn.execute("DELETE FROM audit_log WHERE id > %s", (last,))
        conn.commit()


def _change_text(text: str, h: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE reg_chunk SET text = %s, content_hash = %s WHERE id = %s", (text, h, f"{DOC}#1"))
        conn.commit()


def _status(fid: int) -> str:
    with connect() as conn:
        return conn.execute("SELECT status FROM rule_fragment WHERE id = %s", (fid,)).fetchone()["status"]


def test_changed_text_with_the_quote_goes_back_to_pending(fragment):
    _change_text("A new intro sentence. " + QUOTE, "h2")
    with connect() as conn:
        assert R.send_back_to_review(conn, DOC) == {"to_pending": 1, "retired": 0}
        conn.commit()
        log = conn.execute("SELECT actor, action FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    assert _status(fragment) == "pending" and log == {"actor": "source-refresh", "action": "fragment_to_pending"}


def test_changed_text_without_the_quote_is_retired(fragment):
    _change_text("The front yard shall be not less than 25 feet.", "h3")
    with connect() as conn:
        assert R.send_back_to_review(conn, DOC) == {"to_pending": 0, "retired": 1}
        conn.commit()
    assert _status(fragment) == "invalid"


def test_unchanged_failed_and_manual_sources(fragment, monkeypatch):
    doc = {"id": DOC, "fetch": "url", "url": "https://example.org/t.pdf"}
    monkeypatch.setattr(R, "_download", lambda d: b"same")
    with connect() as conn:
        conn.execute(
            "UPDATE reg_document SET file_sha256 = %s WHERE id = %s", (R.hashlib.sha256(b"same").hexdigest(), DOC)
        )
        conn.commit()
    assert R.check_document(doc)[0] == "unchanged"

    def boom(d):
        raise R.httpx.ConnectError("no network")

    monkeypatch.setattr(R, "_download", boom)
    assert R.check_document(doc) == ("failed", {"error": "ConnectError"})
    assert R.check_document({**doc, "fetch": "manual"})[0] == "manual_ok"
    monkeypatch.setattr(R, "MANUAL_RECHECK_DAYS", 0)
    assert R.check_document({**doc, "fetch": "manual"})[0] == "manual_due"
    assert _status(fragment) == "approved"


def test_never_fetches_blocked_hosts():
    with pytest.raises(ValueError):
        R._download({"url": "https://codelibrary.amlegal.com/codes/los_angeles"})
