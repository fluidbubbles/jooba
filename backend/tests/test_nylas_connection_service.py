from unittest.mock import AsyncMock, MagicMock

import app.services.nylas_connection_service as service_module
from app.services.nylas_connection_service import NylasConnectionService


def _service() -> NylasConnectionService:
    return NylasConnectionService(AsyncMock(), client=MagicMock())


def test_oauth_state_round_trip_valid(monkeypatch) -> None:
    service = _service()
    now = 1_700_000_000
    monkeypatch.setattr(service_module.time, "time", lambda: now)

    state = service.generate_oauth_state()

    assert service.validate_oauth_state(state) is True


def test_oauth_state_rejects_tampered_signature(monkeypatch) -> None:
    service = _service()
    now = 1_700_000_000
    monkeypatch.setattr(service_module.time, "time", lambda: now)
    state = service.generate_oauth_state()
    tampered = state[:-1] + ("0" if state[-1] != "0" else "1")

    assert service.validate_oauth_state(tampered) is False


def test_oauth_state_rejects_expired_token(monkeypatch) -> None:
    service = _service()
    issued_at = 1_700_000_000
    monkeypatch.setattr(service_module.time, "time", lambda: issued_at)
    state = service.generate_oauth_state()

    monkeypatch.setattr(
        service_module.time,
        "time",
        lambda: issued_at + service_module._OAUTH_STATE_TTL_SECONDS + 1,
    )

    assert service.validate_oauth_state(state) is False


def test_oauth_state_rejects_malformed_value() -> None:
    service = _service()
    assert service.validate_oauth_state("not:a:valid:shape") is False
