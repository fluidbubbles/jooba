from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    CandidateNotFound,
    DomainError,
    EnrollmentNotActive,
    InvalidStateTransition,
    ProviderRateLimited,
    SequenceNotFound,
    TransientError,
)


def _domain_error_response(
    exc: DomainError,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": exc.message, "code": exc.code},
        headers=headers,
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

    @app.exception_handler(ProviderRateLimited)
    async def rate_limited(
        _request: Request, exc: ProviderRateLimited
    ) -> JSONResponse:
        return _domain_error_response(exc, 503, headers={"Retry-After": str(exc.retry_after)})

    @app.exception_handler(TransientError)
    async def transient_error(
        _request: Request, exc: TransientError
    ) -> JSONResponse:
        return _domain_error_response(exc, 503)

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return _domain_error_response(exc, 400)
