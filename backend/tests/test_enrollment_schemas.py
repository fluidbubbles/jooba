import pytest
from pydantic import ValidationError

from app.schemas.enrollment import CandidateInput, EnrollRequest


def test_candidate_input_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CandidateInput(email="jane@example.com", unknown="value")


def test_candidate_input_rejects_overlong_first_name() -> None:
    with pytest.raises(ValidationError):
        CandidateInput(
            email="jane@example.com",
            first_name="x" * 101,
        )


def test_enroll_request_rejects_unknown_nested_candidate_fields() -> None:
    with pytest.raises(ValidationError):
        EnrollRequest(
            candidates=[
                {
                    "email": "jane@example.com",
                    "unexpected": "value",
                }
            ]
        )
