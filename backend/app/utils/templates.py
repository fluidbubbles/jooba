import html
import re

SUPPORTED_PLACEHOLDERS = {"first_name", "last_name", "company", "title", "email"}
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def replace_placeholders(template: str, candidate_data: dict[str, str | None]) -> str:
    """Replace `{{name}}` tokens using keys in SUPPORTED_PLACEHOLDERS.

    Matching is case-insensitive. Missing or empty values become "". Unknown tokens
    are left unchanged.
    """

    def replacer(match: re.Match[str]) -> str:
        key = match.group(1).strip().lower()
        if key not in SUPPORTED_PLACEHOLDERS:
            return match.group(0)
        return candidate_data.get(key) or ""

    return _PLACEHOLDER_RE.sub(replacer, template)


def append_unsubscribe_footer(body_html: str, unsubscribe_url: str) -> str:
    """Append a small unsubscribe footer to the email body."""
    safe_url = html.escape(unsubscribe_url, quote=True)
    footer = (
        '<div style="margin-top:32px;padding-top:16px;border-top:1px solid #e5e7eb;'
        'font-size:11px;color:#9ca3af;">'
        f'<a href="{safe_url}" style="color:#9ca3af;">Unsubscribe</a>'
        "</div>"
    )
    return body_html + footer
