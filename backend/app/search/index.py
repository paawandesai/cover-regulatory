"""Embed every chunk whose embedding is missing or came from a different model.

Run: uv run python -m app.search.index
"""

import time

from app.db.connection import connect
from app.search.embed import embed_documents, model_name


def vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def chunk_input(section_id: str, heading: str | None, text: str) -> str:
    # The section id and heading carry most of the meaning of short code sections, so they lead.
    return "\n".join(s for s in (section_id, heading, text) if s)


def run(batch: int = 64) -> dict:
    model = model_name()
    started = time.monotonic()
    done = 0
    with connect() as conn:
        while True:
            rows = conn.execute(
                """SELECT id, section_id, heading, text FROM reg_chunk
                   WHERE embedding IS NULL OR embedding_model IS DISTINCT FROM %s
                   ORDER BY length(text), id LIMIT %s""",
                (model, batch),
            ).fetchall()
            if not rows:
                break
            # Rows come shortest first, so each batch pads to a similar length (padding dominates CPU time).
            vectors = embed_documents(
                (chunk_input(r["section_id"], r["heading"], r["text"]) for r in rows), batch_size=16
            )
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE reg_chunk SET embedding = %s::vector, embedding_model = %s WHERE id = %s",
                    [(vector_literal(v), model, r["id"]) for r, v in zip(rows, vectors, strict=True)],
                )
            conn.commit()
            done += len(rows)
    return {"embedded": done, "model": model, "seconds": round(time.monotonic() - started, 1)}


if __name__ == "__main__":
    print(run())
