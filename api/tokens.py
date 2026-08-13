"""Session token store — persisted to SQLite so tokens survive backend restart.

Trước đây token lưu trong dict RAM → mỗi lần restart (uvicorn --reload) là mất
sạch phiên đăng nhập, khiến agent coi người dùng như khách và hỏi lại tên.
Giờ lưu xuống cùng file his_users.db.
"""
import secrets

from db import _conn


def _init():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token       TEXT PRIMARY KEY,
                fhir_id     TEXT NOT NULL,
                name        TEXT NOT NULL,
                role        TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)


_init()


def create_token(fhir_id: str, name: str, role: str) -> str:
    token = secrets.token_urlsafe(32)
    with _conn() as con:
        con.execute(
            "INSERT INTO tokens (token, fhir_id, name, role) VALUES (?,?,?,?)",
            (token, fhir_id, name, role),
        )
    return token


def resolve_token(token: str) -> dict | None:
    if not token:
        return None
    with _conn() as con:
        row = con.execute(
            "SELECT fhir_id, name, role FROM tokens WHERE token = ?", (token,)
        ).fetchone()
    return dict(row) if row else None


def revoke_token(token: str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM tokens WHERE token = ?", (token,))
