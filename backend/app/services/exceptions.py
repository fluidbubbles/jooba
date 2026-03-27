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


class EnrollmentNotFound(DomainError):
    def __init__(self, enrollment_id: str | UUID) -> None:
        super().__init__(f"Enrollment not found: {enrollment_id}", "ENROLLMENT_NOT_FOUND")


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


class ProviderRateLimited(DomainError):
    def __init__(self, retry_after: int = 60) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s", "PROVIDER_RATE_LIMITED")


class TransientError(DomainError):
    def __init__(self, message: str = "Transient provider error") -> None:
        super().__init__(message, "TRANSIENT_ERROR")


class PermanentError(DomainError):
    def __init__(self, message: str = "Permanent provider error") -> None:
        super().__init__(message, "PERMANENT_ERROR")


class EmailEventNotFound(DomainError):
    def __init__(self, event_id: str | UUID) -> None:
        super().__init__(f"Email event not found: {event_id}", "EMAIL_EVENT_NOT_FOUND")
