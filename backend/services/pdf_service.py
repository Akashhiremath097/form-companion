"""
Turn an uploaded PDF into a fillable conversational form.

Only PDFs with a real AcroForm layer can be handled: those carry named fields we
can both read and write back. A scanned form is just an image of a form, with no
field names and no reliable coordinates, so we detect that case and say so
plainly rather than guessing and producing a wrong document.

Pipeline:
    extract_fields()   raw AcroForm field names and types
    infer_schema()     LLM turns those into human labels, help text and hints
    fill_pdf()         writes answers back into the original document
"""

import io
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader, PdfWriter

from services import llm_service

MAX_FIELDS = 25


class UnsupportedPdf(Exception):
    """Raised when a PDF has no machine-readable form fields."""


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

FIELD_TYPES = {
    "/Tx": "text",
    "/Btn": "checkbox",
    "/Ch": "select",
}


def extract_fields(data: bytes) -> Tuple[List[Dict[str, Any]], str]:
    """
    Pull the AcroForm fields out of a PDF.

    Returns (fields, document_title). Raises UnsupportedPdf when the document
    has no form layer, which is the common case for scanned forms.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - any parse failure is the same to the user
        raise UnsupportedPdf("That file could not be read as a PDF.") from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise UnsupportedPdf("That PDF is password protected.") from exc

    raw = reader.get_fields()
    if not raw:
        raise UnsupportedPdf(
            "This PDF does not have fillable form fields. It is most likely a "
            "scan or a printout, which cannot be filled in automatically."
        )

    fields: List[Dict[str, Any]] = []
    for name, spec in raw.items():
        ft = spec.get("/FT")
        kind = FIELD_TYPES.get(str(ft), "text")

        options = None
        if kind == "select":
            opts = spec.get("/Opt") or []
            options = [str(o[1]) if isinstance(o, list) else str(o) for o in opts]

        fields.append(
            {
                "pdf_name": str(name),
                "kind": kind,
                "options": options,
                "tooltip": str(spec.get("/TU")) if spec.get("/TU") else None,
            }
        )

    if len(fields) > MAX_FIELDS:
        fields = fields[:MAX_FIELDS]

    title = _document_title(reader)
    return fields, title


def _document_title(reader: PdfReader) -> str:
    """Best-effort title: PDF metadata first, then the first line of page one."""
    meta = reader.metadata
    if meta and meta.title and meta.title.strip():
        # Generators often write a placeholder title; prefer the page text then.
        if meta.title.strip().lower() not in ("untitled", "unnamed", "document"):
            return meta.title.strip()[:80]

    try:
        text = (reader.pages[0].extract_text() or "").strip()
        for line in text.split("\n"):
            line = line.strip()
            if len(line) > 8:
                return line[:80]
    except Exception:  # noqa: BLE001
        pass

    return "Uploaded Form"


# ---------------------------------------------------------------------------
# Schema inference
# ---------------------------------------------------------------------------

SCHEMA_SYSTEM = """You convert raw PDF form field names into a friendly, fillable form schema.

You receive a list of internal field names from a PDF (things like
"applicant_full_name" or "dob_ddmmyyyy"). For each one, work out what a person
is actually being asked for, and describe it in plain language.

Return ONLY a JSON array, no prose and no code fences. One object per input
field, in the same order, with these keys:
  "pdf_name": copy the input name exactly, unchanged
  "label": a short human label, e.g. "Full Name" or "Date of Birth"
  "type": one of "text", "date", "tel", "email", "textarea", "select", "checkbox"
  "required": true for identity and contact essentials, false for optional extras
  "help_text": one or two plain sentences saying what this is and where to find it
  "question_hint": how to ask for it conversationally
  "validation": an object, which may be empty. Use "pattern" for a regex,
     "min_length"/"max_length" for text, "length" for fixed-length values,
     and "min_age" for a date of birth.

Guidance:
- Indian mobile numbers: {"pattern": "^[6-9][0-9]{9}$", "length": 10}
- Indian PIN codes: {"pattern": "^[1-9][0-9]{5}$", "length": 6}
- Dates of birth: {"min_age": 18}
- Emails: {"pattern": "^[^@\\\\s]+@[^@\\\\s]+\\\\.[^@\\\\s]+$"} and required false
- Addresses: type "textarea", {"min_length": 10, "max_length": 250}
- If a field's purpose is genuinely unclear, use the field name itself as the
  label and leave validation empty. Never invent a meaning you are not sure of."""


def infer_schema(fields: List[Dict[str, Any]], title: str) -> Dict[str, Any]:
    """
    Ask the LLM to describe each PDF field in human terms.

    Falls back to a readable version of the raw field name when the LLM is
    unavailable, so an upload still produces a usable form.
    """
    listing = "\n".join(
        f"- {f['pdf_name']} (pdf type: {f['kind']}"
        + (f", options: {', '.join(f['options'])}" if f.get("options") else "")
        + (f", tooltip: {f['tooltip']}" if f.get("tooltip") else "")
        + ")"
        for f in fields
    )
    user_prompt = f"Form title: {title}\n\nFields:\n{listing}"

    raw = llm_service._complete(SCHEMA_SYSTEM, user_prompt, max_tokens=2400)
    parsed = _extract_json_array(raw) if raw else None

    by_name = {f["pdf_name"]: f for f in fields}
    described: List[Dict[str, Any]] = []

    if parsed:
        for item in parsed:
            pdf_name = item.get("pdf_name")
            if pdf_name not in by_name:
                continue
            described.append(_normalise(item, by_name[pdf_name]))

    # Anything the model dropped or mangled still gets a usable entry.
    covered = {d["pdf_name"] for d in described}
    for f in fields:
        if f["pdf_name"] not in covered:
            described.append(_fallback_field(f))

    described.sort(key=lambda d: [f["pdf_name"] for f in fields].index(d["pdf_name"]))

    return {
        "form_id": "uploaded",
        "title": title,
        "source": "upload",
        "fields": described,
    }


def _normalise(item: Dict[str, Any], raw_field: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce one LLM-described field into the shape the rest of the app expects."""
    pdf_name = raw_field["pdf_name"]
    kind = item.get("type", "text")
    if raw_field["kind"] == "select" and raw_field.get("options"):
        kind = "select"
    if raw_field["kind"] == "checkbox":
        kind = "select"

    field = {
        "id": _safe_id(pdf_name),
        "pdf_name": pdf_name,
        "label": str(item.get("label") or _humanise(pdf_name))[:80],
        "type": kind,
        "required": bool(item.get("required", False)),
        "help_text": str(item.get("help_text") or f"The {_humanise(pdf_name).lower()} asked for on this form."),
        "question_hint": str(item.get("question_hint") or ""),
        "validation": item.get("validation") if isinstance(item.get("validation"), dict) else {},
    }

    if raw_field.get("options"):
        field["options"] = raw_field["options"]
    elif raw_field["kind"] == "checkbox":
        field["options"] = ["Yes", "No"]
    elif kind == "select" and isinstance(item.get("options"), list):
        field["options"] = [str(o) for o in item["options"]]

    return field


def _fallback_field(raw_field: Dict[str, Any]) -> Dict[str, Any]:
    """A plain but working field description, used when the LLM gives us nothing."""
    label = _humanise(raw_field["pdf_name"])
    field = {
        "id": _safe_id(raw_field["pdf_name"]),
        "pdf_name": raw_field["pdf_name"],
        "label": label,
        "type": "select" if raw_field["kind"] in ("select", "checkbox") else "text",
        "required": False,
        "help_text": f"The {label.lower()} asked for on this form.",
        "question_hint": f"Ask for their {label.lower()}.",
        "validation": {},
    }
    if raw_field.get("options"):
        field["options"] = raw_field["options"]
    elif raw_field["kind"] == "checkbox":
        field["options"] = ["Yes", "No"]
    return field


def _humanise(name: str) -> str:
    """applicant_full_name -> Applicant Full Name"""
    text = re.sub(r"[_\-.]+", " ", name)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return " ".join(w.capitalize() for w in text.split())[:80] or "Field"


def _safe_id(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or "field"


def _extract_json_array(raw: str) -> Optional[List[Dict[str, Any]]]:
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Filling
# ---------------------------------------------------------------------------


def fill_pdf(data: bytes, schema: Dict[str, Any], answers: Dict[str, Any]) -> bytes:
    """Write the collected answers back into the original PDF and return bytes."""
    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter(clone_from=reader)
    # Without this, many viewers show the values as blank until the field is
    # clicked, because the PDF has no pre-rendered appearance for them.
    writer.set_need_appearances_writer(True)

    values: Dict[str, str] = {}
    for field in schema["fields"]:
        value = answers.get(field["id"])
        if value is None or value == "":
            continue
        values[field["pdf_name"]] = str(value)

    for page in writer.pages:
        try:
            writer.update_page_form_field_values(page, values)
        except Exception:  # noqa: BLE001 - a page with no fields is not an error
            continue

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
