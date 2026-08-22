"""
Deterministic field validation.

Runs after LLM extraction, never instead of it. The LLM cleans the shape of the
answer; this module decides whether the cleaned answer is actually acceptable.
Keeping these separate means a bad LLM day cannot let garbage into the form.
"""

import re
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple


def _friendly_length_error(label: str, value: str, rules: Dict[str, Any]) -> Optional[str]:
    min_len = rules.get("min_length")
    max_len = rules.get("max_length")
    exact = rules.get("length")

    if exact and len(value) != exact:
        return f"Your {label.lower()} should be {exact} characters long. I counted {len(value)}."
    if min_len and len(value) < min_len:
        return f"That seems a little short for your {label.lower()}. Could you give me a bit more?"
    if max_len and len(value) > max_len:
        return f"That is longer than the form allows for {label.lower()}. Could you shorten it?"
    return None


def _validate_date(value: str, rules: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    """Returns (is_valid, error_message, normalised_value)."""
    parsed = None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            parsed = datetime.strptime(value.strip(), fmt).date()
            break
        except ValueError:
            continue

    if parsed is None:
        return False, "I could not read that as a date. Could you tell me the day, month and year?", None

    if parsed > date.today():
        return False, "That date is in the future. Could you check it for me?", None

    min_age = rules.get("min_age")
    if min_age:
        today = date.today()
        age = today.year - parsed.year - ((today.month, today.day) < (parsed.month, parsed.day))
        if age < min_age:
            return False, f"You need to be at least {min_age} to open this account on your own.", None

    return True, None, parsed.strftime("%d/%m/%Y")


PATTERN_MESSAGES = {
    "mobile_number": "That does not look like a valid Indian mobile number. It should be 10 digits starting with 6, 7, 8 or 9.",
    "pincode": "That does not look like a valid PIN code. It should be six digits.",
    "email": "That does not look like a complete email address. It needs an @ symbol and a domain, like name@example.com.",
    "full_name": "Please use only letters for your name, without numbers or symbols.",
}


def validate_field(field: Dict[str, Any], value: Any) -> Tuple[bool, Optional[str], Any]:
    """
    Validate a single field value.

    Returns (is_valid, error_message, normalised_value).
    A None value on an optional field is always valid.
    """
    label = field["label"]
    rules = field.get("validation", {}) or {}

    # Empty handling
    if value is None or (isinstance(value, str) and not value.strip()):
        if field.get("required"):
            return False, f"I do need your {label.lower()} to complete the form. Could you tell me?", None
        return True, None, None

    value = str(value).strip()

    # Select fields must match one of the options
    if field["type"] == "select":
        options = field.get("options", [])
        for option in options:
            if value.lower() == option.lower():
                return True, None, option
        readable = ", ".join(options[:-1]) + f" or {options[-1]}" if len(options) > 1 else options[0]
        return False, f"Please choose one of these: {readable}.", None

    # Dates get their own parser
    if field["type"] == "date":
        return _validate_date(value, rules)

    # Length checks
    length_error = _friendly_length_error(label, value, rules)
    if length_error:
        return False, length_error, None

    # Regex checks
    pattern = rules.get("pattern")
    if pattern and not re.match(pattern, value):
        message = PATTERN_MESSAGES.get(
            field["id"], f"That does not look quite right for {label.lower()}. Could you check it?"
        )
        return False, message, None

    return True, None, value
