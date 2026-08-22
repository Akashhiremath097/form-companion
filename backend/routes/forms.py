"""
Upload a fillable PDF, fill it conversationally, download the result.

Only PDFs with an AcroForm layer are supported. A scanned form is an image of a
form with no named fields and no dependable coordinates, so rather than guess
and hand someone a wrongly filled bank document, we detect that case and say so.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from services import llm_service, pdf_service, session_store

router = APIRouter(prefix="/api", tags=["forms"])

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB


class UploadResponse(BaseModel):
    session_id: str
    language: str
    form_title: str
    field_count: int
    message: str
    current_field: Optional[Dict[str, Any]]
    preview: List[Dict[str, Any]]
    progress: Dict[str, int]


def _public_field(field: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Strip internal prompt hints and PDF plumbing before sending to the client."""
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


@router.post("/forms/upload", response_model=UploadResponse)
async def upload_form(
    file: UploadFile = File(...),
    language: str = "en",
) -> UploadResponse:
    if language not in ("en", "kn"):
        language = "en"

    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail="That file is larger than 8 MB. Please upload a smaller PDF.",
        )
    if not data:
        raise HTTPException(status_code=400, detail="That file appears to be empty.")

    try:
        raw_fields, title = pdf_service.extract_fields(data)
    except pdf_service.UnsupportedPdf as exc:
        # 422 rather than 400: the file is a valid upload, it just cannot be used.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    schema = pdf_service.infer_schema(raw_fields, title)
    if not schema["fields"]:
        raise HTTPException(
            status_code=422,
            detail="No usable fields were found in that form.",
        )

    session_id = session_store.create_session(language, schema=schema, pdf_bytes=data)
    first_field = session_store.next_unfilled_field(session_id)

    greetings = {
        "en": (
            f"I have read your form: {schema['title']}. "
            f"It has {len(schema['fields'])} fields. "
            "I will ask about them one at a time, and you can download the "
            "completed form when we are done."
        ),
        "kn": (
            f"ನಿಮ್ಮ ಅರ್ಜಿಯನ್ನು ಓದಿದ್ದೇನೆ: {schema['title']}. "
            f"ಇದರಲ್ಲಿ {len(schema['fields'])} ಪ್ರಶ್ನೆಗಳಿವೆ. "
            "ಒಂದೊಂದಾಗಿ ಕೇಳುತ್ತೇನೆ. ಮುಗಿದ ನಂತರ ಭರ್ತಿ ಮಾಡಿದ ಅರ್ಜಿಯನ್ನು "
            "ಡೌನ್\u200cಲೋಡ್ ಮಾಡಬಹುದು."
        ),
    }

    question = llm_service.generate_question(
        first_field, is_first=True, answered_count=0, language=language
    )
    message = f"{greetings.get(language, greetings['en'])}\n\n{question}"
    session_store.append_history(session_id, "assistant", message)

    return UploadResponse(
        session_id=session_id,
        language=language,
        form_title=schema["title"],
        field_count=len(schema["fields"]),
        message=message,
        current_field=_public_field(first_field),
        preview=session_store.build_preview(session_id),
        progress=session_store.progress(session_id),
    )


@router.get("/sessions/{session_id}/download")
def download_filled_form(session_id: str) -> Response:
    """Return the uploaded PDF with the collected answers written into it."""
    if not session_store.exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    pdf_bytes = session_store.get_pdf_bytes(session_id)
    if pdf_bytes is None:
        raise HTTPException(
            status_code=400,
            detail="This session is not based on an uploaded PDF, so there is "
            "nothing to download.",
        )

    filled = pdf_service.fill_pdf(
        pdf_bytes,
        session_store.session_schema(session_id),
        session_store.get_answers(session_id),
    )

    return Response(
        content=filled,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="completed-form.pdf"'},
    )
