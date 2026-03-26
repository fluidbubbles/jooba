import hashlib
import hmac
import logging
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)

_SIG_LENGTH = 16


def _sign(payload: str) -> str:
    """Compute a truncated HMAC-SHA256 signature for *payload*."""
    return hmac.new(
        settings.secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:_SIG_LENGTH]


def generate_unsubscribe_token(candidate_id: UUID, sequence_id: UUID) -> str:
    """Generate an HMAC-signed token for unsubscribe links.

    Token format: {candidate_id}:{sequence_id}:{signature}
    No database lookup needed to verify -- just recompute the HMAC.
    """
    payload = f"{candidate_id}:{sequence_id}"
    return f"{payload}:{_sign(payload)}"


def verify_unsubscribe_token(token: str) -> tuple[UUID, UUID] | None:
    """Verify and extract candidate_id + sequence_id from token.

    Returns (candidate_id, sequence_id) if valid, None if malformed,
    signature-mismatched, or containing invalid UUID values.
    """
    try:
        candidate_str, sequence_str, provided_sig = token.split(":")
    except ValueError:
        logger.warning("Malformed unsubscribe token: expected 3 segments, got %d", len(token.split(":")))
        return None

    expected_sig = _sign(f"{candidate_str}:{sequence_str}")

    if not hmac.compare_digest(provided_sig, expected_sig):
        logger.warning("Unsubscribe token signature mismatch for candidate=%s", candidate_str)
        return None

    try:
        return UUID(candidate_str), UUID(sequence_str)
    except ValueError:
        logger.warning(
            "Unsubscribe token contains invalid UUIDs: candidate=%s sequence=%s",
            candidate_str, sequence_str,
        )
        return None
