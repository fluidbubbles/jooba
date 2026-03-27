"""Stateless helpers for parsing and formatting person names."""


def split_full_name(full_name: str | None) -> tuple[str | None, str | None]:
    if not full_name:
        return None, None
    parts = full_name.strip().split()
    if not parts:
        return None, None
    first = parts[0]
    last = " ".join(parts[1:]) if len(parts) > 1 else None
    return first, last


def format_display_name(first: str | None, last: str | None) -> str | None:
    combined = f"{first or ''} {last or ''}".strip()
    return combined if combined else None
