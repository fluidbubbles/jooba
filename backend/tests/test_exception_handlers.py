from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.exception_handlers import register_exception_handlers
from app.services.exceptions import ProviderRateLimited, TransientError


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/rate-limited")
    async def raise_rate_limited() -> None:
        raise ProviderRateLimited(retry_after=42)

    @app.get("/transient")
    async def raise_transient() -> None:
        raise TransientError("Temporary provider issue")

    return app


def test_provider_rate_limited_maps_to_503() -> None:
    client = TestClient(_build_app())

    response = client.get("/rate-limited")

    assert response.status_code == 503
    assert response.json() == {
        "error": "Rate limited, retry after 42s",
        "code": "PROVIDER_RATE_LIMITED",
    }
    assert response.headers["retry-after"] == "42"


def test_transient_error_maps_to_503() -> None:
    client = TestClient(_build_app())

    response = client.get("/transient")

    assert response.status_code == 503
    assert response.json() == {
        "error": "Temporary provider issue",
        "code": "TRANSIENT_ERROR",
    }
