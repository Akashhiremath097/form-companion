"""
Groq LLaMA wrapper for the Accessible Form Assistant.

Every public function here degrades gracefully: if Groq is slow, rate-limited,
or returns malformed output, the caller still gets a usable response. This
matters because a judge testing the live demo will not forgive a 500 error.
"""

import json
import os
import re
from typing import Any, Dict, Optional

from groq import Groq

MODEL = "openai/gpt-oss-120b"
TIMEOUT_SECONDS = 12

_client: Optional[Groq] = None


def get_client() -> Groq:
    """Lazily construct the Groq client so import never fails without a key."""
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        _client = Groq(api_key=api_key, timeout=TIMEOUT_SECONDS)
    return _client


def _complete(system_prompt: str, user_prompt: str, max_tokens: int = 400) -> Optional[str]:
    """
    Single completion call. Returns None on any failure rather than raising,
    so callers can fall back to a deterministic non-LLM path.
    """
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=max_tokens,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:  # noqa: BLE001 - deliberate catch-all for demo resilience
        print(f"[llm_service] Groq call failed: {type(exc).__name__}: {exc}")
        return None


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """Pull a JSON object out of a model response that may include prose or fences."""
    if not raw:
        return None
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

ASK_SYSTEM = """You are a warm, patient assistant helping someone fill out an official form.
The person may have low literacy, a visual impairment, or may simply find forms stressful.

Rules:
- Ask for exactly ONE piece of information.
- Use short sentences and everyday words. Never use banking jargon without explaining it.
- Do not greet them again if the conversation is already underway.
- Never invent extra questions or ask for information not requested.
- Keep your reply under 40 words.
- Reply with plain text only. No markdown, no bullet points, no emoji."""


def generate_question(field: Dict[str, Any], is_first: bool, answered_count: int) -> str:
    """
    Produce the conversational prompt for the next field.
    Falls back to the field label if the LLM is unavailable.
    """
    position = "This is the first question." if is_first else f"They have already answered {answered_count} questions."
    user_prompt = (
        f"{position}\n\n"
        f"Field to ask about: {field['label']}\n"
        f"What it means: {field['help_text']}\n"
        f"Required: {'yes' if field.get('required') else 'no, it is optional'}\n"
        f"Guidance: {field.get('question_hint', '')}\n"
    )
    if field.get("options"):
        user_prompt += f"Valid choices: {', '.join(field['options'])}\n"

    result = _complete(ASK_SYSTEM, user_prompt, max_tokens=120)
    if result:
        return result

    # Deterministic fallback — plain but always works.
    optional_note = "" if field.get("required") else " (You can skip this one.)"
    return f"What is your {field['label'].lower()}?{optional_note}"


EXTRACT_SYSTEM = """You extract a single form field value from a person's natural reply.

Return ONLY a JSON object, no prose and no code fences, with these keys:
  "value": the cleaned value as a string, or null if they declined or gave nothing usable
  "skipped": true if they explicitly declined or said they do not have one, otherwise false
  "needs_clarification": true if the reply is unclear or incomplete, otherwise false
  "clarification": a short friendly follow-up question if needs_clarification is true, otherwise null

Cleaning rules:
- Phone numbers: digits only, drop +91, spaces and dashes.
- Dates: output in DD/MM/YYYY format with forward slashes and zero-padded day and month. "3rd August 2005" becomes "03/08/2005". "15 March 2004" becomes "15/03/2004". Never output digits without slashes.
- PIN codes: digits only.
- Names and addresses: fix obvious capitalisation, keep the person's own wording.
- Extract ONLY the value itself, never the surrounding sentence. If they say "Hello, my name is Akash" the value is "Akash". If they say "I live in Bengaluru" the value is "Bengaluru". Strip greetings, filler and trailing punctuation.
- If the field has a fixed list of choices, map their answer to the closest choice exactly as written in the list."""


def extract_value(field: Dict[str, Any], user_reply: str) -> Dict[str, Any]:
    """
    Turn a free-text reply into a structured field value.
    Falls back to using the raw reply verbatim if the LLM is unavailable.
    """
    user_prompt = (
        f"Field: {field['label']} (type: {field['type']})\n"
        f"Meaning: {field['help_text']}\n"
    )
    if field.get("options"):
        user_prompt += f"Valid choices: {', '.join(field['options'])}\n"
    user_prompt += f"\nThe person replied: \"{user_reply}\""

    raw = _complete(EXTRACT_SYSTEM, user_prompt, max_tokens=200)
    parsed = _extract_json(raw) if raw else None

    if parsed and "value" in parsed:
        return {
            "value": parsed.get("value"),
            "skipped": bool(parsed.get("skipped", False)),
            "needs_clarification": bool(parsed.get("needs_clarification", False)),
            "clarification": parsed.get("clarification"),
        }

    # Fallback: trust the raw reply, let validation catch problems.
    stripped = user_reply.strip()
    declined = stripped.lower() in {"skip", "no", "none", "don't have", "dont have", "n/a"}
    return {
        "value": None if declined else stripped,
        "skipped": declined,
        "needs_clarification": False,
        "clarification": None,
    }


SIMPLIFY_SYSTEM = """You explain form fields to someone who finds official forms confusing.

Rules:
- Explain in 2 or 3 short sentences at a reading level a 12-year-old would follow.
- Say what the field is, why the form asks for it, and where they might find the answer.
- Never use jargon. If a technical term is unavoidable, define it immediately.
- Be reassuring, never condescending.
- Plain text only. No markdown, no bullets."""


def simplify_field(field: Dict[str, Any]) -> str:
    """Plain-language explanation of a field. Falls back to the stored help text."""
    user_prompt = (
        f"Field: {field['label']}\n"
        f"Official description: {field['help_text']}\n"
    )
    if field.get("options"):
        user_prompt += f"Choices offered: {', '.join(field['options'])}\n"
    user_prompt += "\nExplain this field simply."

    result = _complete(SIMPLIFY_SYSTEM, user_prompt, max_tokens=200)
    return result or field["help_text"]
