"""Tests for stateless utility functions."""

from app.utils.email_quotes import strip_email_quotes
from app.utils.name_parse import format_display_name, split_full_name


class TestStripEmailQuotes:
    def test_no_quotes_passes_through(self) -> None:
        assert strip_email_quotes("Just a plain reply.") == "Just a plain reply."

    def test_empty_string(self) -> None:
        assert strip_email_quotes("") == ""

    def test_strips_gmail_on_wrote_pattern(self) -> None:
        text = "Sounds good!\n\nOn Mon, Jan 1, 2026 at 10:00 AM John Doe wrote:\noriginal message"
        assert strip_email_quotes(text) == "Sounds good!"

    def test_strips_traditional_greater_than_quoting(self) -> None:
        text = "My reply\n> quoted line 1\n> quoted line 2"
        assert strip_email_quotes(text) == "My reply"

    def test_strips_both_patterns(self) -> None:
        text = "Reply here.\n\nOn Tue, Feb 2 at 3:00 PM Jane wrote:\n> old text\n> more old"
        assert strip_email_quotes(text) == "Reply here."

    def test_on_in_normal_sentence_not_stripped(self) -> None:
        text = "I'm working on a project right now."
        assert strip_email_quotes(text) == "I'm working on a project right now."

    def test_short_on_pattern_not_matched(self) -> None:
        """The regex requires 10-250 chars between 'On' and 'wrote:' to avoid false positives."""
        text = "On short wrote: nope"
        # "short" is only 5 chars, below the 10-char minimum
        assert "On short wrote:" in strip_email_quotes(text)

    def test_mixed_content_with_trailing_whitespace(self) -> None:
        text = "Thanks!\n\n> old quote\n  "
        assert strip_email_quotes(text) == "Thanks!"


class TestSplitFullName:
    def test_none_returns_none_tuple(self) -> None:
        assert split_full_name(None) == (None, None)

    def test_empty_string_returns_none_tuple(self) -> None:
        assert split_full_name("") == (None, None)

    def test_whitespace_only_returns_none_tuple(self) -> None:
        assert split_full_name("   ") == (None, None)

    def test_single_name(self) -> None:
        assert split_full_name("Alice") == ("Alice", None)

    def test_two_parts(self) -> None:
        assert split_full_name("Alice Smith") == ("Alice", "Smith")

    def test_three_parts_joins_last(self) -> None:
        assert split_full_name("Mary Jane Watson") == ("Mary", "Jane Watson")

    def test_leading_trailing_whitespace_stripped(self) -> None:
        assert split_full_name("  Bob Jones  ") == ("Bob", "Jones")


class TestFormatDisplayName:
    def test_both_none_returns_none(self) -> None:
        assert format_display_name(None, None) is None

    def test_first_only(self) -> None:
        assert format_display_name("Alice", None) == "Alice"

    def test_last_only(self) -> None:
        assert format_display_name(None, "Smith") == "Smith"

    def test_both_names(self) -> None:
        assert format_display_name("Alice", "Smith") == "Alice Smith"

    def test_empty_strings_return_none(self) -> None:
        assert format_display_name("", "") is None
