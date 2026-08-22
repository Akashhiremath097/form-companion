"""
Conversational form-fill routes.

Flow:
  POST /api/sessions              -> create session, get opening question
  POST /api/sessions/{id}/answer  -> submit reply, get next question
  POST /api/sessions/{id}/simplify-> plain-language explanation of current field
  GET  /api/sessions/{id}/preview -> live form state
  POST /api/sessions/{id}/reset-field -> correct an earlier answer
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import llm_service, session_store, validation

router = APIRouter(prefix="/api", tags=["chat"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class SessionCreated(BaseModel):
    session_id: str
    form_title: str
    message: str
    current_field: Optional[Dict[str, Any]]
    progress: Dict[str, int]


class AnswerRequest(BaseModel):
    reply: str = Field(..., min_length=1, max_length=1000)


class AnswerResponse(BaseModel):
    accepted: bool
    message: str
    current_field: Optional[Dict[str, Any]]
    preview: List[Dict[str, Any]]
    progress: Dict[str, int]
    complete: bool


class SimplifyResponse(BaseModel):
    field_id: str
    explanation: str


class ResetFieldRequest(BaseModel):
    field_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _public_field(field: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Strip internal prompt-engineering hints before sending to the client."""
    if field is None:
        return None
    return {
        "id": field["id"],
        "label": field["label"],
        "type": field["type"],
        "required": field.get("required", False),
        "options": field.get("options"),
        "help_text": field["help_text"],
    }


def _guard(session_id: str) -> None:
    if not session_store.exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found or expired.")


def _completion_message(session_id: str) -> str:
    progress = session_store.progress(session_id)
    if progress["skipped"]:
        return (
            f"All done. I have filled in {progress['answered']} fields and left "
            f"{progress['skipped']} blank. Check the form on the right, and tell me "
            "if you want to change anything."
        )
    return (
        "All done. Every field is filled in. Check the form on the right, and tell me "
        "if you want to change anything."
    )


def _advance(session_id: str, prefix: str = "") -> AnswerResponse:
    """Move to the next field and build the response payload."""
    next_field = session_store.next_unfilled_field(session_id)

    if next_field is None:
        message = _completion_message(session_id)
        session_store.append_history(session_id, "assistant", message)
        return AnswerResponse(
            accepted=True,
            message=(prefix + " " + message).strip(),
            current_field=None,
            preview=session_store.build_preview(session_id),
            progress=session_store.progress(session_id),
            complete=True,
        )

    progress = session_store.progress(session_id)
    question = llm_service.generate_question(
        next_field,
        is_first=(progress["answered"] + progress["skipped"] == 0),
        answered_count=progress["answered"],
    )
    session_store.append_history(session_id, "assistant", question)

    return AnswerResponse(
        accepted=True,
        message=(prefix + " " + question).strip(),
        current_field=_public_field(next_field),
        preview=session_store.build_preview(session_id),
        progress=progress,
        complete=False,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=SessionCreated)
def create_session() -> SessionCreated:
    session_id = session_store.create_session()
    schema = session_store.load_schema()
    first_field = session_store.next_unfilled_field(session_id)

    greeting = (
        f"Hello. I am going to help you fill in the {schema['title']}. "
        "I will ask one thing at a time, and you can answer however feels natural. "
        "If any question is confusing, ask me to explain it."
    )
    question = llm_service.generate_question(first_field, is_first=True, answered_count=0)
    message = f"{greeting}\n\n{question}"

    session_store.append_history(session_id, "assistant", message)

    return SessionCreated(
        session_id=session_id,
        form_title=schema["title"],
        message=message,
        current_field=_public_field(first_field),
        progress=session_store.progress(session_id),
    )


@router.post("/sessions/{session_id}/answer", response_model=AnswerResponse)
def submit_answer(session_id: str, request: AnswerRequest) -> AnswerResponse:
    _guard(session_id)

    field = session_store.next_unfilled_field(session_id)
    if field is None:
        return AnswerResponse(
            accepted=True,
            message=_completion_message(session_id),
            current_field=None,
            preview=session_store.build_preview(session_id),
            progress=session_store.progress(session_id),
            complete=True,
        )

    session_store.append_history(session_id, "user", request.reply)

    # 1. LLM extracts a clean value from natural language
    extracted = llm_service.extract_value(field, request.reply)

    # 2. Explicit skip on an optional field
    if extracted["skipped"]:
        if field.get("required"):
            message = (
                f"I understand, but the bank does need your {field['label'].lower()} "
                "before it can open the account. Could you share it?"
            )
            session_store.append_history(session_id, "assistant", message)
            return AnswerResponse(
                accepted=False,
                message=message,
                current_field=_public_field(field),
                preview=session_store.build_preview(session_id),
                progress=session_store.progress(session_id),
                complete=False,
            )
        session_store.record_answer(session_id, field["id"], None, skipped=True)
        return _advance(session_id, prefix="No problem, I have left that blank.")

    # 3. LLM flagged the reply as unclear
    if extracted["needs_clarification"] and extracted["clarification"]:
        session_store.append_history(session_id, "assistant", extracted["clarification"])
        return AnswerResponse(
            accepted=False,
            message=extracted["clarification"],
            current_field=_public_field(field),
            preview=session_store.build_preview(session_id),
            progress=session_store.progress(session_id),
            complete=False,
        )

    # 4. Deterministic validation — the real gatekeeper
    is_valid, error, normalised = validation.validate_field(field, extracted["value"])
    if not is_valid:
        session_store.append_history(session_id, "assistant", error)
        return AnswerResponse(
            accepted=False,
            message=error,
            current_field=_public_field(field),
            preview=session_store.build_preview(session_id),
            progress=session_store.progress(session_id),
            complete=False,
        )

    # 5. Accept and move on
    if normalised is None and not field.get("required"):
        session_store.record_answer(session_id, field["id"], None, skipped=True)
    else:
        session_store.record_answer(session_id, field["id"], normalised)

    return _advance(session_id, prefix="Got it.")


@router.post("/sessions/{session_id}/simplify", response_model=SimplifyResponse)
def simplify_current_field(session_id: str) -> SimplifyResponse:
    _guard(session_id)

    field = session_store.next_unfilled_field(session_id)
    if field is None:
        raise HTTPException(status_code=400, detail="The form is already complete.")

    explanation = llm_service.simplify_field(field)
    session_store.append_history(session_id, "assistant", explanation)

    return SimplifyResponse(field_id=field["id"], explanation=explanation)


@router.get("/sessions/{session_id}/preview")
def get_preview(session_id: str) -> Dict[str, Any]:
    _guard(session_id)
    return {
        "form_title": session_store.load_schema()["title"],
        "preview": session_store.build_preview(session_id),
        "progress": session_store.progress(session_id),
        "complete": session_store.is_complete(session_id),
    }


@router.post("/sessions/{session_id}/reset-field", response_model=AnswerResponse)
def reset_field(session_id: str, request: ResetFieldRequest) -> AnswerResponse:
    _guard(session_id)

    field = session_store.get_field(request.field_id)
    if field is None:
        raise HTTPException(status_code=404, detail="No such field on this form.")

    session_store.reset_field(session_id, request.field_id)
    return _advance(session_id, prefix=f"Let us redo your {field['label'].lower()}.")


@router.get("/sessions/{session_id}/history")
def get_history(session_id: str) -> Dict[str, Any]:
    _guard(session_id)
    return {"history": session_store.get_history(session_id)}
