import hashlib
import hmac
from uuid import UUID

from app.core.config import settings


def generate_unsubscribe_token(candidate_id: UUID, sequence_id: UUID) -> str:
    """Generate an HMAC-signed token for unsubscribe links.

    Token format: {candidate_id}:{sequence_id}:{signature}
    No database lookup needed to verify -- just recompute the HMAC.
    """
    payload = f"{candidate_id}:{sequence_id}"
    signature = hmac.new(
        settings.secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    return f"{payload}:{signature}"


def verify_unsubscribe_token(token: str) -> tuple[UUID, UUID] | None:
    """Verify and extract candidate_id + sequence_id from token.

    Returns (candidate_id, sequence_id) if valid, None if tampered.
    """
    parts = token.split(":")
    if len(parts) != 3:
        return None

    candidate_str, sequence_str, provided_sig = parts
    payload = f"{candidate_str}:{sequence_str}"
    expected_sig = hmac.new(
        settings.secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]

    if not hmac.compare_digest(provided_sig, expected_sig):
        return None

    try:
        return UUID(candidate_str), UUID(sequence_str)
    except ValueError:
        return None
