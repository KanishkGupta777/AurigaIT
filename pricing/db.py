"""
Real persistent storage for bookings, using SQLite (Python's built-in
sqlite3 -- no extra dependency, works out of the box in Codespaces).

Note on "a database in GitHub": GitHub itself isn't a database host.
What this gives you is a real local database file (data/bookings.db)
that persists on disk across server restarts within the same Codespace/
machine. If you want it visible in your repo too, you can commit that
file, but a SQLite file under active git version control is not how real
systems store live transactional data (concurrent writes + git merges
don't mix) -- treat committing it as a snapshot for evaluators to
inspect, not as the live store.
"""
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

_lock = threading.Lock()

_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bookings.db"
)
_db_path = _DEFAULT_DB_PATH


def configure(path: str):
    """Override the DB file path (used by tests to isolate state)."""
    global _db_path
    _db_path = path
    init_db()


def current_path() -> str:
    return _db_path


@contextmanager
def _get_conn():
    os.makedirs(os.path.dirname(_db_path), exist_ok=True)
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id TEXT NOT NULL,
                show_title TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                tickets_json TEXT NOT NULL,
                is_member INTEGER NOT NULL,
                festival_applied INTEGER NOT NULL,
                subtotal_paisa INTEGER NOT NULL,
                festival_discount_paisa INTEGER NOT NULL,
                member_discount_paisa INTEGER NOT NULL,
                convenience_fee_paisa INTEGER NOT NULL,
                convenience_fee_gst_paisa INTEGER NOT NULL,
                grand_total_paisa INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


def insert_booking(
    show_id, show_title, customer_name, phone, tickets_json,
    is_member, festival_applied, subtotal_paisa, festival_discount_paisa,
    member_discount_paisa, convenience_fee_paisa, convenience_fee_gst_paisa,
    grand_total_paisa,
) -> int:
    with _lock, _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO bookings (
                show_id, show_title, customer_name, phone, tickets_json,
                is_member, festival_applied, subtotal_paisa,
                festival_discount_paisa, member_discount_paisa,
                convenience_fee_paisa, convenience_fee_gst_paisa,
                grand_total_paisa, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                show_id, show_title, customer_name, phone, tickets_json,
                int(is_member), int(festival_applied), subtotal_paisa,
                festival_discount_paisa, member_discount_paisa,
                convenience_fee_paisa, convenience_fee_gst_paisa,
                grand_total_paisa, datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid


def list_bookings():
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bookings ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


init_db()
