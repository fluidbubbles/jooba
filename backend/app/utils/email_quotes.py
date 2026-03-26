import re

_WROTE_PATTERN = re.compile(r"\bOn .{10,250} wrote:\s*")


def strip_email_quotes(text: str) -> str:
    """Remove quoted reply content from plain-text email body.

    Strips:
    - Everything from the first "On ... wrote:" pattern onward (inline or own-line)
    - Lines starting with ">" (traditional quoting)
    """
    # Truncate at first "On ... wrote:" (Gmail/Outlook attribution)
    m = _WROTE_PATTERN.search(text)
    if m:
        text = text[: m.start()]

    # Remove traditional ">" quoted lines
    lines = [line for line in text.splitlines() if not line.strip().startswith(">")]
    return "\n".join(lines).strip()
