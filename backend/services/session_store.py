"""
In-memory session store.

Deliberately simple for the hackathon build: a dict keyed by session UUID.
The interface is narrow on purpose so swapping in Postgres or Redis later
means rewriting this file only, with no changes to the routes.

Note: form answers may contain personal data, so nothing here is logged.
"""

import json
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "data" / "bank_form_schema.json"

_sessions: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
_schema_cache: Optional[Dict[str, Any]] = None


def load_schema() -> Dict[str, Any]:
    """Load and cache the form schema from disk."""
    global _schema_cache
    if _schema_cache is None:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
            _schema_cache = json.load(handle)
    return _schema_cache


def get_fields() -> List[Dict[str, Any]]:
    return load_schema()["fields"]


def get_field(field_id: str) -> Optional[Dict[str, Any]]:
    return next((f for f in get_fields() if f["id"] == field_id), None)


def create_session() -> str:
    """Start a new form session and return its id."""
    session_id = str(uuid.uuid4())
    with _lock:
        _sessions[session_id] = {
            "answers": {},
            "skipped": set(),
            "history": [],
        }
    return session_id


def _require(session_id: str) -> Dict[str, Any]:
    session = _sessions.get(session_id)
    if session is None:
        raise KeyError(f"Unknown session: {session_id}")
    return session


def exists(session_id: str) -> bool:
    return session_id in _sessions


def record_answer(session_id: str, field_id: str, value: Any, skipped: bool = False) -> None:
    session = _require(session_id)
    with _lock:
        if skipped:
            session["skipped"].add(field_id)
            session["answers"].pop(field_id, None)
        else:
            session["answers"][field_id] = value
            session["skipped"].discard(field_id)


def append_history(session_id: str, role: str, content: str) -> None:
    session = _require(session_id)
    with _lock:
        session["history"].append({"role": role, "content": content})


def get_history(session_id: str) -> List[Dict[str, str]]:
    return list(_require(session_id)["history"])


def get_answers(session_id: str) -> Dict[str, Any]:
    return dict(_require(session_id)["answers"])


def next_unfilled_field(session_id: str) -> Optional[Dict[str, Any]]:
    """The first field in schema order that is neither answered nor skipped."""
    session = _require(session_id)
    answered = set(session["answers"].keys()) | session["skipped"]
    return next((f for f in get_fields() if f["id"] not in answered), None)


def progress(session_id: str) -> Dict[str, int]:
    session = _require(session_id)
    fields = get_fields()
    resolved = len(session["answers"]) + len(session["skipped"])
    return {
        "answered": len(session["answers"]),
        "skipped": len(session["skipped"]),
        "total": len(fields),
        "remaining": len(fields) - resolved,
    }


def build_preview(session_id: str) -> List[Dict[str, Any]]:
    """Full form state for the live preview panel, in schema order."""
    session = _require(session_id)
    preview = []
    for field in get_fields():
        field_id = field["id"]
        if field_id in session["answers"]:
            status = "filled"
        elif field_id in session["skipped"]:
            status = "skipped"
        else:
            status = "pending"
        preview.append(
            {
                "id": field_id,
                "label": field["label"],
                "value": session["answers"].get(field_id),
                "status": status,
                "required": field.get("required", False),
            }
        )
    return preview


def is_complete(session_id: str) -> bool:
    return next_unfilled_field(session_id) is None


def reset_field(session_id: str, field_id: str) -> None:
    """Clear one field so the user can correct an earlier answer."""
    session = _require(session_id)
    with _lock:
        session["answers"].pop(field_id, None)
        session["skipped"].discard(field_id)
