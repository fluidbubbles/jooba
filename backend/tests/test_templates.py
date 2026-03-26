from app.utils.templates import append_unsubscribe_footer, replace_placeholders


class TestReplacePlaceholders:
    def test_replaces_known_placeholders(self):
        template = "Hi {{first_name}}, I saw your work at {{company}}"
        result = replace_placeholders(template, {"first_name": "Jane", "company": "Stripe"})
        assert result == "Hi Jane, I saw your work at Stripe"

    def test_missing_placeholder_becomes_empty(self):
        result = replace_placeholders("Hi {{first_name}}", {})
        assert result == "Hi "

    def test_multiple_occurrences_of_same_placeholder(self):
        result = replace_placeholders(
            "{{first_name}} and {{first_name}}",
            {"first_name": "Jane"},
        )
        assert result == "Jane and Jane"

    def test_preserves_text_without_placeholders(self):
        result = replace_placeholders("No placeholders here", {"first_name": "Jane"})
        assert result == "No placeholders here"

    def test_spaces_inside_braces_not_matched(self):
        """Only {{word}} syntax is supported, not {{ word }}."""
        result = replace_placeholders("Hi {{ first_name }}", {"first_name": "Jane"})
        assert result == "Hi {{ first_name }}"

    def test_all_supported_fields(self):
        data = {
            "first_name": "Jane",
            "last_name": "Chen",
            "company": "Stripe",
            "title": "Engineer",
            "email": "jane@stripe.com",
        }
        template = "{{first_name}} {{last_name}} at {{company}} ({{title}}) — {{email}}"
        result = replace_placeholders(template, data)
        assert result == "Jane Chen at Stripe (Engineer) — jane@stripe.com"

    def test_empty_string_value_treated_as_missing(self):
        result = replace_placeholders("Hi {{first_name}}", {"first_name": ""})
        assert result == "Hi "

    def test_none_value_treated_as_missing(self):
        result = replace_placeholders("Hi {{first_name}}", {"first_name": None})
        assert result == "Hi "


class TestAppendUnsubscribeFooter:
    def test_appends_footer_with_link(self):
        body = "<p>Hello</p>"
        result = append_unsubscribe_footer(body, "https://example.com/unsub/abc")
        assert "Unsubscribe" in result
        assert "https://example.com/unsub/abc" in result
        assert result.startswith(body)

    def test_footer_is_html_div(self):
        result = append_unsubscribe_footer("<p>Hi</p>", "https://example.com/unsub/xyz")
        assert "<div" in result
        assert "</div>" in result
        assert '<a href="https://example.com/unsub/xyz"' in result

    def test_preserves_original_body(self):
        body = "<p>Complex <b>HTML</b> content</p>"
        result = append_unsubscribe_footer(body, "https://example.com/unsub/123")
        assert body in result

    def test_escapes_url_with_quotes(self):
        """Unsubscribe URL is HTML-escaped to prevent attribute injection."""
        result = append_unsubscribe_footer("<p>Hi</p>", 'https://evil.com/x"onmouseover="alert(1)')
        assert '"onmouseover=' not in result
        assert "&quot;" in result or "&#x27;" in result
