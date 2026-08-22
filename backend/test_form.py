"""
Tests for the deterministic layers: validation and session state.

The LLM layer is deliberately not tested against the live API — these tests must
pass offline and without a Groq key, so CI never depends on an external service.
"""

import pytest

from services import session_store, validation


@pytest.fixture
def session():
    return session_store.create_session()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_id,value,expected_valid",
    [
        ("full_name", "Akash Hiremath", True),
        ("full_name", "A", False),               # too short
        ("full_name", "Akash123", False),        # digits not allowed
        ("mobile_number", "9876543210", True),
        ("mobile_number", "1234567890", False),  # must start 6-9
        ("mobile_number", "98765", False),       # wrong length
        ("pincode", "560059", True),
        ("pincode", "060059", False),            # cannot start with 0
        ("email", "akash@example.com", True),
        ("email", "not-an-email", False),
        ("email", None, True),                   # optional field
        ("occupation", "Student", True),
        ("occupation", "astronaut", False),      # not in options
    ],
)
def test_validate_field(field_id, value, expected_valid):
    field = session_store.get_field(field_id)
    is_valid, error, _ = validation.validate_field(field, value)
    assert is_valid is expected_valid
    if not is_valid:
        assert error, "A rejection must always explain itself to the user"


def test_required_field_rejects_empty():
    field = session_store.get_field("full_name")
    is_valid, error, _ = validation.validate_field(field, "")
    assert is_valid is False
    assert "full name" in error.lower()


def test_select_normalises_case():
    field = session_store.get_field("occupation")
    _, _, normalised = validation.validate_field(field, "student")
    assert normalised == "Student"


def test_date_normalises_to_ddmmyyyy():
    field = session_store.get_field("date_of_birth")
    for raw in ["15/03/2004", "15-03-2004", "2004-03-15"]:
        is_valid, _, normalised = validation.validate_field(field, raw)
        assert is_valid
        assert normalised == "15/03/2004"


def test_date_rejects_under_18():
    field = session_store.get_field("date_of_birth")
    is_valid, error, _ = validation.validate_field(field, "15/03/2020")
    assert is_valid is False
    assert "18" in error


def test_date_rejects_future():
    field = session_store.get_field("date_of_birth")
    is_valid, error, _ = validation.validate_field(field, "01/01/2099")
    assert is_valid is False
    assert "future" in error.lower()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def test_schema_has_expected_shape():
    fields = session_store.get_fields()
    assert len(fields) == 10
    for field in fields:
        assert {"id", "label", "type", "help_text"} <= field.keys()


def test_fields_are_served_in_schema_order(session):
    order = [f["id"] for f in session_store.get_fields()]
    served = []
    while not session_store.is_complete(session):
        field = session_store.next_unfilled_field(session)
        served.append(field["id"])
        session_store.record_answer(session, field["id"], "x")
    assert served == order


def test_skipped_field_does_not_reappear(session):
    session_store.record_answer(session, "full_name", None, skipped=True)
    assert session_store.next_unfilled_field(session)["id"] != "full_name"
    assert session_store.progress(session)["skipped"] == 1


def test_reset_field_reopens_it(session):
    session_store.record_answer(session, "full_name", "Akash Hiremath")
    session_store.record_answer(session, "date_of_birth", "15/03/2004")
    session_store.reset_field(session, "full_name")
    assert session_store.next_unfilled_field(session)["id"] == "full_name"


def test_preview_reports_three_statuses(session):
    session_store.record_answer(session, "full_name", "Akash Hiremath")
    session_store.record_answer(session, "email", None, skipped=True)
    statuses = {row["id"]: row["status"] for row in session_store.build_preview(session)}
    assert statuses["full_name"] == "filled"
    assert statuses["email"] == "skipped"
    assert statuses["city"] == "pending"


def test_sessions_are_isolated():
    first = session_store.create_session()
    second = session_store.create_session()
    session_store.record_answer(first, "full_name", "Akash Hiremath")
    assert session_store.get_answers(second) == {}
