from uuid import UUID


class DomainError(Exception):
    """Base domain error with a stable machine code for API mapping."""

    def __init__(self, message: str, code: str) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class SequenceNotFound(DomainError):
    def __init__(self, sequence_id: str | UUID) -> None:
        super().__init__(f"Sequence not found: {sequence_id}", "SEQUENCE_NOT_FOUND")


class CandidateNotFound(DomainError):
    def __init__(self, identifier: str) -> None:
        super().__init__(f"Candidate not found: {identifier}", "CANDIDATE_NOT_FOUND")


class EnrollmentNotActive(DomainError):
    def __init__(self, enrollment_id: str | UUID) -> None:
        super().__init__(f"Enrollment is not active: {enrollment_id}", "ENROLLMENT_NOT_ACTIVE")


class InvalidStateTransition(DomainError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            f"Invalid state transition from {current!r} to {target!r}",
            "INVALID_STATE_TRANSITION",
        )


class InvalidSequenceData(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason, "INVALID_SEQUENCE_DATA")
