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


class CreateSessionRequest(BaseModel):
    language: str = Field(default="en", pattern="^(en|kn)$")


class SetLanguageRequest(BaseModel):
    language: str = Field(..., pattern="^(en|kn)$")


class SessionCreated(BaseModel):
    session_id: str
    language: str
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


class PrefillItem(BaseModel):
    field_id: str
    value: str


class PrefillRequest(BaseModel):
    values: List[PrefillItem]


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


# Fixed phrases the assistant says outside of an LLM call. These have to be
# translated here rather than generated, because they wrap or replace LLM output
# and must appear even when the model is unavailable.
PHRASES = {
    "en": {
        "got_it": "Got it.",
        "left_blank": "No problem, I have left that blank.",
        "redo": "Let us redo your {label}.",
        "required": (
            "I understand, but the form does need your {label} before it can be "
            "submitted. Could you share it?"
        ),
        "done": (
            "All done. Every field is filled in. Check the form on the right, and "
            "tell me if you want to change anything."
        ),
        "done_partial": (
            "All done. I have filled in {answered} fields and left {skipped} blank. "
            "Check the form on the right, and tell me if you want to change anything."
        ),
    },
    "kn": {
        "got_it": "\u0cb8\u0cb0\u0cbf.",
        "left_blank": "\u0caa\u0cb0\u0cb5\u0cbe\u0c97\u0cbf\u0cb2\u0ccd\u0cb2, \u0c85\u0ca6\u0ca8\u0ccd\u0ca8\u0cc1 \u0c96\u0cbe\u0cb2\u0cbf \u0cac\u0cbf\u0c9f\u0ccd\u0c9f\u0cbf\u0ca6\u0ccd\u0ca6\u0cc7\u0ca8\u0cc6.",
        "redo": "\u0ca8\u0cbf\u0cae\u0ccd\u0cae {label} \u0cae\u0ca4\u0ccd\u0ca4\u0cc6 \u0ca8\u0cae\u0cc2\u0ca6\u0cbf\u0cb8\u0acb\u0ca3.",
        "required": (
            "\u0ca4\u0cbf\u0cb3\u0cbf\u0caf\u0cbf\u0ca4\u0cc1, \u0c86\u0ca6\u0cb0\u0cc6 \u0c85\u0cb0\u0ccd\u0c9c\u0cbf\u0c97\u0cc6 \u0ca8\u0cbf\u0cae\u0ccd\u0cae {label} \u0c85\u0c97\u0ca4\u0ccd\u0caf\u0cb5\u0cbf\u0ca6\u0cc6. \u0ca6\u0caf\u0cb5\u0cbf\u0c9f\u0ccd\u0c9f\u0cc1 \u0ca4\u0cbf\u0cb3\u0cbf\u0cb8\u0cbf."
        ),
        "done": (
            "\u0cae\u0cc1\u0c97\u0cbf\u0caf\u0cbf\u0ca4\u0cc1. \u0c8e\u0cb2\u0ccd\u0cb2\u0cbe \u0cb5\u0cbf\u0cb5\u0cb0\u0c97\u0cb3\u0ca8\u0ccd\u0ca8\u0cc2 \u0cad\u0cb0\u0ccd\u0ca4\u0cbf \u0cae\u0cbe\u0ca1\u0cb2\u0cbe\u0c97\u0cbf\u0ca6\u0cc6. "
            "\u0cac\u0cb2\u0c97\u0ca1\u0cc6 \u0c87\u0cb0\u0cc1\u0cb5 \u0c85\u0cb0\u0ccd\u0c9c\u0cbf\u0caf\u0ca8\u0ccd\u0ca8\u0cc1 \u0ca8\u0ccb\u0ca1\u0cbf, \u0cac\u0ca6\u0cb2\u0cbf\u0cb8\u0cac\u0cc7\u0c95\u0cbe\u0ca6\u0cb0\u0cc6 \u0ca4\u0cbf\u0cb3\u0cbf\u0cb8\u0cbf."
        ),
        "done_partial": (
            "\u0cae\u0cc1\u0c97\u0cbf\u0caf\u0cbf\u0ca4\u0cc1. {answered} \u0cb5\u0cbf\u0cb5\u0cb0\u0c97\u0cb3\u0ca8\u0ccd\u0ca8\u0cc1 \u0cad\u0cb0\u0ccd\u0ca4\u0cbf \u0cae\u0cbe\u0ca1\u0cbf, {skipped} \u0c96\u0cbe\u0cb2\u0cbf \u0cac\u0cbf\u0c9f\u0ccd\u0c9f\u0cbf\u0ca6\u0ccd\u0ca6\u0cc7\u0ca8\u0cc6. "
            "\u0cac\u0cb2\u0c97\u0ca1\u0cc6 \u0c87\u0cb0\u0cc1\u0cb5 \u0c85\u0cb0\u0ccd\u0c9c\u0cbf\u0caf\u0ca8\u0ccd\u0ca8\u0cc1 \u0ca8\u0ccb\u0ca1\u0cbf, \u0cac\u0ca6\u0cb2\u0cbf\u0cb8\u0cac\u0cc7\u0c95\u0cbe\u0ca6\u0cb0\u0cc6 \u0ca4\u0cbf\u0cb3\u0cbf\u0cb8\u0cbf."
        ),
    },
}


def phrase(session_id: str, key: str, **kwargs) -> str:
    language = session_store.get_language(session_id)
    table = PHRASES.get(language, PHRASES["en"])
    return table.get(key, PHRASES["en"][key]).format(**kwargs)


def _translate_error(session_id: str, message: str) -> str:
    """
    Validation errors are generated in Python and so are always English.
    Rather than maintain a parallel Kannada string for every rule, we translate
    the finished message. If the translation call fails the English text still
    goes out, which is far better than no explanation at all.
    """
    language = session_store.get_language(session_id)
    if language == "en":
        return message

    translated = llm_service.translate_message(message, language)
    return translated or message


def _completion_message(session_id: str) -> str:
    progress = session_store.progress(session_id)
    if progress["skipped"]:
        return phrase(
            session_id,
            "done_partial",
            answered=progress["answered"],
            skipped=progress["skipped"],
        )
    return phrase(session_id, "done")


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
        language=session_store.get_language(session_id),
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


GREETINGS = {
    "en": (
        "Hello. I am going to help you fill in the {title}. "
        "I will ask one thing at a time, and you can answer however feels natural. "
        "If any question is confusing, ask me to explain it. "
        "The form itself will be filled in English."
    ),
    "kn": (
        "ನಮಸ್ಕಾರ. ನಾನು ನಿಮಗೆ {title} ಭರ್ತಿ ಮಾಡಲು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. "
        "ಒಂದೊಂದೇ ಪ್ರಶ್ನೆ ಕೇಳುತ್ತೇನೆ, ನೀವು ನಿಮ್ಮ ಸ್ವಂತ ಮಾತಿನಲ್ಲಿ ಉತ್ತರಿಸಬಹುದು. "
        "ಯಾವುದೇ ಪ್ರಶ್ನೆ ಗೊಂದಲವಾದರೆ ವಿವರಿಸಲು ಕೇಳಿ. "
        "ಅರ್ಜಿಯನ್ನು ಇಂಗ್ಲಿಷ್\u200cನಲ್ಲಿ ಭರ್ತಿ ಮಾಡಲಾಗುತ್ತದೆ."
    ),
}


@router.post("/sessions", response_model=SessionCreated)
def create_session(request: CreateSessionRequest | None = None) -> SessionCreated:
    language = request.language if request else "en"
    session_id = session_store.create_session(language)
    schema = session_store.session_schema(session_id)
    first_field = session_store.next_unfilled_field(session_id)

    greeting = GREETINGS.get(language, GREETINGS["en"]).format(title=schema["title"])
    question = llm_service.generate_question(
        first_field, is_first=True, answered_count=0, language=language
    )
    message = f"{greeting}\n\n{question}"

    session_store.append_history(session_id, "assistant", message)

    return SessionCreated(
        session_id=session_id,
        language=language,
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
    extracted = llm_service.extract_value(
        field, request.reply, language=session_store.get_language(session_id)
    )

    # 2. Explicit skip on an optional field
    if extracted["skipped"]:
        if field.get("required"):
            message = phrase(session_id, "required", label=field["label"].lower())
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
        return _advance(session_id, prefix=phrase(session_id, "left_blank"))

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
        error = _translate_error(session_id, error)
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

    return _advance(session_id, prefix=phrase(session_id, "got_it"))


@router.post("/sessions/{session_id}/simplify", response_model=SimplifyResponse)
def simplify_current_field(session_id: str) -> SimplifyResponse:
    _guard(session_id)

    field = session_store.next_unfilled_field(session_id)
    if field is None:
        raise HTTPException(status_code=400, detail="The form is already complete.")

    explanation = llm_service.simplify_field(
        field, language=session_store.get_language(session_id)
    )
    session_store.append_history(session_id, "assistant", explanation)

    return SimplifyResponse(field_id=field["id"], explanation=explanation)


@router.get("/sessions/{session_id}/preview")
def get_preview(session_id: str) -> Dict[str, Any]:
    _guard(session_id)
    return {
        "form_title": session_store.session_schema(session_id)["title"],
        "preview": session_store.build_preview(session_id),
        "progress": session_store.progress(session_id),
        "complete": session_store.is_complete(session_id),
    }


@router.post("/sessions/{session_id}/reset-field", response_model=AnswerResponse)
def reset_field(session_id: str, request: ResetFieldRequest) -> AnswerResponse:
    _guard(session_id)

    field = session_store.session_field(session_id, request.field_id)
    if field is None:
        raise HTTPException(status_code=404, detail="No such field on this form.")

    session_store.reset_field(session_id, request.field_id)
    return _advance(session_id, prefix=phrase(session_id, "redo", label=field["label"].lower()))


@router.post("/sessions/{session_id}/language", response_model=AnswerResponse)
def set_language(session_id: str, request: SetLanguageRequest) -> AnswerResponse:
    """Switch languages mid-session and re-ask the current question."""
    _guard(session_id)
    session_store.set_language(session_id, request.language)
    return _advance(session_id)


@router.post("/sessions/{session_id}/prefill", response_model=AnswerResponse)
def prefill(session_id: str, request: PrefillRequest) -> AnswerResponse:
    """
    Accept values read off a scanned ID document.

    Every value still goes through the same validation as a typed answer. OCR is
    unreliable, and a wrong date of birth is no more acceptable because a camera
    produced it than because someone mistyped it. Values that fail validation are
    dropped rather than reported: the person is then simply asked for that field
    in the normal way.
    """
    _guard(session_id)

    accepted = 0
    for item in request.values:
        field = session_store.session_field(session_id, item.field_id)
        if field is None:
            continue

        is_valid, _, normalised = validation.validate_field(field, item.value)
        if not is_valid or normalised is None:
            continue

        session_store.record_answer(session_id, field["id"], normalised)
        accepted += 1

    if accepted == 0:
        return AnswerResponse(
            accepted=False,
            message=_translate_error(
                session_id,
                "I could not read anything usable from that image. Let us carry on "
                "and I will ask you directly.",
            ),
            current_field=_public_field(session_store.next_unfilled_field(session_id)),
            preview=session_store.build_preview(session_id),
            progress=session_store.progress(session_id),
            complete=session_store.is_complete(session_id),
        )

    prefix = _translate_error(
        session_id,
        f"I have filled in {accepted} field{'s' if accepted != 1 else ''} from your "
        "document. Please check them on the right and change anything that is wrong.",
    )
    return _advance(session_id, prefix=prefix)


@router.get("/sessions/{session_id}/history")
def get_history(session_id: str) -> Dict[str, Any]:
    _guard(session_id)
    return {"history": session_store.get_history(session_id)}
