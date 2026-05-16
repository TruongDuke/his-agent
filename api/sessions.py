"""Session management — in-memory store + disk persistence."""

import uuid
import json as _json
from pathlib import Path
from datetime import datetime as _datetime

_sessions: dict[str, list] = {}          # session_id → messages
_doctor_current: dict[str, str] = {}     # doctor_id → active session_id
_SESSIONS_DIR = Path(__file__).parent.parent / "data" / "sessions"
_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _doctor_dir(doctor_id: str) -> Path:
    d = _SESSIONS_DIR / doctor_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_or_create_doctor_session(doctor_id: str) -> str:
    if doctor_id in _doctor_current:
        return _doctor_current[doctor_id]
    d = _SESSIONS_DIR / doctor_id
    if d.exists():
        files = sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if files:
            sid = f"doctor_{doctor_id}_{files[0].stem}"
            _doctor_current[doctor_id] = sid
            return sid
    return _new_doctor_session(doctor_id)


def _new_doctor_session(doctor_id: str) -> str:
    conv_uuid = str(uuid.uuid4())
    sid = f"doctor_{doctor_id}_{conv_uuid}"
    _doctor_current[doctor_id] = sid
    return sid


def _load_session(session_id: str) -> list:
    if session_id in _sessions:
        return _sessions[session_id]
    if session_id.startswith("doctor_"):
        parts = session_id[len("doctor_"):].rsplit("_", 1)
        if len(parts) == 2:
            p = _doctor_dir(parts[0]) / f"{parts[1]}.json"
            if p.exists():
                try:
                    raw = _json.loads(p.read_text(encoding="utf-8"))
                    msgs = raw["messages"] if isinstance(raw, dict) else raw
                    _sessions[session_id] = msgs
                    return msgs
                except Exception:
                    pass
    return []


def _save_session(session_id: str, history: list) -> None:
    _sessions[session_id] = history
    if not session_id.startswith("doctor_"):
        return
    parts = session_id[len("doctor_"):].rsplit("_", 1)
    if len(parts) != 2:
        return
    doctor_id, conv_file = parts
    p = _doctor_dir(doctor_id) / f"{conv_file}.json"
    now = _datetime.now().isoformat(timespec="seconds")
    conv = None
    if p.exists():
        try:
            raw = _json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                conv = raw
        except Exception:
            pass
    if conv is None:
        title = next(
            (m["content"][:45] for m in history
             if m.get("role") == "user" and isinstance(m.get("content"), str)),
            "Hội thoại mới",
        )
        conv = {"session_id": session_id, "title": title,
                "created_at": now, "updated_at": now, "messages": history}
    else:
        conv["messages"] = history
        conv["updated_at"] = now
    try:
        p.write_text(_json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _visible_messages(history: list) -> list:
    """Filter to only user + assistant text messages for display."""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str)
        and m.get("content", "").strip()
    ]
