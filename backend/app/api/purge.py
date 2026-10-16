"""Delete feedback and client reports older than FEEDBACK_RETENTION_DAYS. Run on a schedule in the hosted demo:
python -m app.api.purge"""

from app.config import get_settings
from app.db.connection import connect


def purge() -> int:
    days = get_settings().feedback_retention_days
    with connect() as conn:
        n = conn.execute("DELETE FROM feedback WHERE created_at < now() - make_interval(days => %s)", (days,)).rowcount
        n += conn.execute("DELETE FROM report WHERE created_at < now() - make_interval(days => %s)", (days,)).rowcount
        conn.commit()
    return n


if __name__ == "__main__":
    print(f"deleted {purge()} feedback and report rows")
