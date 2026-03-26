import html
import re


def replace_placeholders(template: str, candidate_data: dict[str, str | None]) -> str:
    """Replace {{placeholder}} tokens with candidate data.

    Supported: {{first_name}}, {{last_name}}, {{company}}, {{title}}, {{email}}
    Keys are matched exactly as lowercase. Missing data falls back to empty string.
    """

    def replacer(match: re.Match) -> str:
        key = match.group(1)
        return candidate_data.get(key) or ""

    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


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
