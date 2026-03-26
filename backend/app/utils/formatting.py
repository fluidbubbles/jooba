def format_candidate_name(
    first_name: str | None, last_name: str | None, email: str
) -> str:
    """Build a display name from name parts, falling back to the email local part."""
    parts = [p for p in (first_name, last_name) if p]
    return " ".join(parts) if parts else email.split("@")[0]
