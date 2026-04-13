"""Tests for the compression engine internals (preservers + engine)."""

from __future__ import annotations

from ensemble_mcp.compress.engine import CompressResult, _compress_prose, compress
from ensemble_mcp.compress.preservers import find_preserve_spans


class TestPreservers:
    """Tests for find_preserve_spans."""

    def test_fenced_code_block(self):
        text = "before\n```python\nprint('hello')\n```\nafter"
        spans = find_preserve_spans(text)
        kinds = [s.kind for s in spans]
        assert "fenced_code" in kinds
        # Verify the code block content is captured
        code_span = next(s for s in spans if s.kind == "fenced_code")
        assert "print('hello')" in text[code_span.start : code_span.end]

    def test_inline_code(self):
        text = "Use the `VectorStore` class to query."
        spans = find_preserve_spans(text)
        kinds = [s.kind for s in spans]
        assert "inline_code" in kinds
        code_span = next(s for s in spans if s.kind == "inline_code")
        assert text[code_span.start : code_span.end] == "`VectorStore`"

    def test_url_detection(self):
        text = "Check https://docs.python.org/3/library/sqlite3.html for details."
        spans = find_preserve_spans(text)
        kinds = [s.kind for s in spans]
        assert "url" in kinds
        url_span = next(s for s in spans if s.kind == "url")
        assert "https://docs.python.org" in text[url_span.start : url_span.end]

    def test_file_path_detection(self):
        text = "Edit the file src/ensemble_mcp/config/defaults.py now."
        spans = find_preserve_spans(text)
        path_spans = [s for s in spans if s.kind in ("file_path", "relative_path")]
        assert len(path_spans) >= 1
        matched_text = text[path_spans[0].start : path_spans[0].end]
        assert "defaults.py" in matched_text

    def test_heading_detection(self):
        text = "# Installation Guide\n\nSome text here.\n\n## Prerequisites"
        spans = find_preserve_spans(text)
        heading_spans = [s for s in spans if s.kind == "heading"]
        assert len(heading_spans) == 2
        assert "Installation Guide" in text[heading_spans[0].start : heading_spans[0].end]
        assert "Prerequisites" in text[heading_spans[1].start : heading_spans[1].end]

    def test_table_row_detection(self):
        text = "| Name | Value |\n|------|-------|\n| foo | bar |"
        spans = find_preserve_spans(text)
        table_kinds = [s.kind for s in spans if s.kind.startswith("table")]
        assert len(table_kinds) >= 2  # At least data row + separator

    def test_version_number(self):
        text = "Upgrade to v2.0.0 today."
        spans = find_preserve_spans(text)
        version_spans = [s for s in spans if s.kind == "version"]
        assert len(version_spans) >= 1
        assert "v2.0.0" in text[version_spans[0].start : version_spans[0].end]

    def test_date_detection(self):
        text = "Released on 2024-01-15 with important fixes."
        spans = find_preserve_spans(text)
        date_spans = [s for s in spans if s.kind == "date"]
        assert len(date_spans) >= 1
        assert "2024-01-15" in text[date_spans[0].start : date_spans[0].end]

    def test_shell_command(self):
        text = "Run this:\n$ pip install ensemble-mcp\nDone."
        spans = find_preserve_spans(text)
        shell_spans = [s for s in spans if s.kind == "shell_command"]
        assert len(shell_spans) >= 1
        assert "pip install" in text[shell_spans[0].start : shell_spans[0].end]

    def test_no_overlap(self):
        text = "Use `https://example.com` in your config."
        spans = find_preserve_spans(text)
        # Verify spans don't overlap
        for i in range(len(spans) - 1):
            assert spans[i].end <= spans[i + 1].start

    def test_empty_text(self):
        assert find_preserve_spans("") == []

    def test_no_technical_content(self):
        text = "This is just plain text with nothing special."
        spans = find_preserve_spans(text)
        # May detect some words, but should be minimal
        assert isinstance(spans, list)

    def test_spans_are_sorted(self):
        text = "# Heading\n\n`code` and https://url.com\n\n```\nblock\n```"
        spans = find_preserve_spans(text)
        starts = [s.start for s in spans]
        assert starts == sorted(starts)


class TestCompressProse:
    """Tests for the _compress_prose internal function."""

    def test_drops_articles(self):
        result = _compress_prose("This is a test of the system for an example.")
        assert " a " not in f" {result} ".replace("  ", " ")
        assert " the " not in f" {result} ".replace("  ", " ")
        assert " an " not in f" {result} ".replace("  ", " ")

    def test_drops_filler_words(self):
        result = _compress_prose("It just really basically works actually very well.")
        assert "just" not in result.lower()
        assert "really" not in result.lower()
        assert "basically" not in result.lower()
        assert "actually" not in result.lower()
        assert "very" not in result.lower()

    def test_drops_hedging(self):
        result = _compress_prose("I think this might be correct. It seems to work.")
        assert "i think" not in result.lower()
        assert "it seems" not in result.lower()
        assert "might be" not in result.lower()

    def test_drops_pleasantries(self):
        result = _compress_prose("Sure! Here is the answer.")
        assert "Sure!" not in result

    def test_simplifies_phrases(self):
        result = _compress_prose("In order to fix this, do it.")
        assert "in order to" not in result.lower()
        assert "to" in result.lower()

    def test_simplifies_due_to_fact(self):
        result = _compress_prose("Due to the fact that it failed, we stopped.")
        assert "due to the fact that" not in result.lower()
        assert "because" in result.lower()

    def test_simplifies_at_this_point(self):
        result = _compress_prose("At this point in time, it works.")
        assert "at this point in time" not in result.lower()

    def test_simplifies_as_well_as(self):
        result = _compress_prose("Python as well as JavaScript.")
        assert "as well as" not in result.lower()
        assert "and" in result.lower()

    def test_normalizes_whitespace(self):
        result = _compress_prose("Too   many   spaces   here.")
        assert "   " not in result
        assert "  " not in result

    def test_empty_input(self):
        assert _compress_prose("") == ""

    def test_preserves_meaningful_words(self):
        result = _compress_prose("The database connection was established successfully.")
        assert "database" in result.lower()
        assert "connection" in result.lower()


class TestCompressEngine:
    """Tests for the main compress() function."""

    def test_returns_compress_result(self):
        result = compress("I think this is basically a really good test of the system.")
        assert isinstance(result, CompressResult)
        assert isinstance(result.compressed_text, str)
        assert isinstance(result.original_tokens, int)
        assert isinstance(result.compressed_tokens, int)
        assert isinstance(result.savings_pct, float)
        assert isinstance(result.preserved_count, int)

    def test_reduces_tokens(self):
        verbose = (
            "Sure! I'd be happy to help. I think this is basically a really good "
            "approach. It's actually very simple. Perhaps you might also want to "
            "consider doing it in order to make things work as well as improve."
        )
        result = compress(verbose)
        assert result.compressed_tokens <= result.original_tokens
        assert result.savings_pct >= 0

    def test_preserves_code_blocks(self):
        text = (
            "I think you should do this:\n\n"
            "```python\ndef hello():\n    print('world')\n```\n\n"
            "It's basically simple."
        )
        result = compress(text)
        assert "```python" in result.compressed_text
        assert "def hello():" in result.compressed_text
        assert "print('world')" in result.compressed_text

    def test_preserves_urls(self):
        text = "I think you should really check https://example.com/docs for details."
        result = compress(text)
        assert "https://example.com/docs" in result.compressed_text

    def test_preserves_inline_code(self):
        text = "Just use `VectorStore` to query, it's really simple."
        result = compress(text)
        assert "`VectorStore`" in result.compressed_text

    def test_preserves_headings(self):
        text = "# Main Title\n\nI think this is basically important.\n\n## Sub Title"
        result = compress(text)
        assert "# Main Title" in result.compressed_text
        assert "## Sub Title" in result.compressed_text

    def test_pure_code_unchanged(self):
        code = "```python\nimport sys\nprint(sys.argv)\n```"
        result = compress(code)
        assert result.compressed_text == code
        assert result.savings_pct == 0.0

    def test_empty_input(self):
        result = compress("")
        assert result.compressed_text == ""
        assert result.original_tokens == 0
        assert result.compressed_tokens == 0
        assert result.savings_pct == 0.0
        assert result.preserved_count == 0

    def test_whitespace_only(self):
        result = compress("   \n\n   ")
        assert result.original_tokens == 0
        assert result.savings_pct == 0.0

    def test_preserves_file_paths(self):
        text = "Edit src/ensemble_mcp/server.py to add the new tool."
        result = compress(text)
        assert "src/ensemble_mcp/server.py" in result.compressed_text

    def test_preserves_version_numbers(self):
        text = "I think you should really upgrade from v1.2.3 to v2.0.0-beta.1 soon."
        result = compress(text)
        assert "v1.2.3" in result.compressed_text
        assert "v2.0.0-beta.1" in result.compressed_text

    def test_preserves_tables(self):
        text = (
            "Here's basically a table:\n\n"
            "| Name | Value |\n"
            "|------|-------|\n"
            "| foo  | bar   |\n\n"
            "I think it's really good."
        )
        result = compress(text)
        assert "| Name | Value |" in result.compressed_text
        assert "| foo  | bar   |" in result.compressed_text

    def test_savings_pct_non_negative(self):
        # Short technical text might not compress well
        result = compress("Use `pip install package` now.")
        assert result.savings_pct >= 0.0

    def test_preserved_count_accuracy(self):
        text = "Check `code1` and `code2` at https://example.com.\n\n# Heading\n\nMore text."
        result = compress(text)
        assert result.preserved_count > 0
