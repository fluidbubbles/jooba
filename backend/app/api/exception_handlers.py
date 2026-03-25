from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    CandidateNotFound,
    DomainError,
    EnrollmentNotActive,
    InvalidSequenceData,
    InvalidStateTransition,
    SequenceNotFound,
)


def _domain_error_response(exc: DomainError, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": exc.message, "code": exc.code},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SequenceNotFound)
    async def sequence_not_found(
        _request: Request, exc: SequenceNotFound
    ) -> JSONResponse:
        return _domain_error_response(exc, 404)

    @app.exception_handler(CandidateNotFound)
    async def candidate_not_found(
        _request: Request, exc: CandidateNotFound
    ) -> JSONResponse:
        return _domain_error_response(exc, 404)

    @app.exception_handler(EnrollmentNotActive)
    async def enrollment_not_active(
        _request: Request, exc: EnrollmentNotActive
    ) -> JSONResponse:
        return _domain_error_response(exc, 409)

    @app.exception_handler(InvalidStateTransition)
    async def invalid_state_transition(
        _request: Request, exc: InvalidStateTransition
    ) -> JSONResponse:
        return _domain_error_response(exc, 409)

    @app.exception_handler(InvalidSequenceData)
    async def invalid_sequence_data(
        _request: Request, exc: InvalidSequenceData
    ) -> JSONResponse:
        return _domain_error_response(exc, 400)

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return _domain_error_response(exc, 400)
