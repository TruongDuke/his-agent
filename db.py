"""SQLite user store for phone + password authentication."""

import sqlite3
import bcrypt
from pathlib import Path

DB_PATH = Path(__file__).parent / "his_users.db"


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                phone       TEXT PRIMARY KEY,
                password    TEXT NOT NULL,
                fhir_id     TEXT NOT NULL,
                role        TEXT NOT NULL,
                name        TEXT NOT NULL
            )
        """)


def get_user(phone: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        return dict(row) if row else None


def create_user(phone: str, password: str, fhir_id: str, role: str, name: str):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with _conn() as con:
        con.execute(
            "INSERT INTO users (phone, password, fhir_id, role, name) VALUES (?,?,?,?,?)",
            (phone, hashed, fhir_id, role, name),
        )


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


init_db()
