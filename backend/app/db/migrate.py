"""Applies numbered SQL files in backend/migrations once each, in order."""

from pathlib import Path

from app.db.connection import connect

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def migrate() -> list[str]:
    applied: list[str] = []
    with connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            applied.append(path.name)
        conn.commit()
    return applied


if __name__ == "__main__":
    for name in migrate():
        print(f"applied {name}")
