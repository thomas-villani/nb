"""Tests for nb.utils.markdown module."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from nb.utils.markdown import (
    H1_PATTERN,
    INLINE_TAG_PATTERN,
    WIKI_LINK_PATTERN,
    create_daily_note_template,
    create_note_template,
    extract_date,
    extract_tags,
    extract_title,
    extract_wiki_links,
    generate_frontmatter,
    parse_note_file,
)


class TestPatterns:
    """Test regex patterns used in markdown parsing."""

    def test_wiki_link_pattern_simple(self):
        match = WIKI_LINK_PATTERN.search("[[path/to/note]]")
        assert match is not None
        assert match.group(1) == "path/to/note"
        assert match.group(2) is None  # No display text

    def test_wiki_link_pattern_with_title(self):
        match = WIKI_LINK_PATTERN.search("[[path/to/note|Display Title]]")
        assert match is not None
        assert match.group(1) == "path/to/note"
        assert match.group(2) == "Display Title"

    def test_wiki_link_pattern_multiple(self):
        text = "See [[note1]] and [[note2|Second Note]]"
        matches = list(WIKI_LINK_PATTERN.finditer(text))
        assert len(matches) == 2
        assert matches[0].group(1) == "note1"
        assert matches[1].group(1) == "note2"
        assert matches[1].group(2) == "Second Note"

    def test_inline_tag_pattern_start_of_line(self):
        matches = list(INLINE_TAG_PATTERN.finditer("#tag"))
        assert len(matches) == 1
        assert matches[0].group(1) == "tag"

    def test_inline_tag_pattern_after_space(self):
        matches = list(INLINE_TAG_PATTERN.finditer("text #tag more"))
        assert len(matches) == 1
        assert matches[0].group(1) == "tag"

    def test_inline_tag_pattern_multiple(self):
        matches = list(INLINE_TAG_PATTERN.finditer("#tag1 #tag2 #tag3"))
        assert len(matches) == 3
        tags = [m.group(1) for m in matches]
        assert tags == ["tag1", "tag2", "tag3"]

    def test_inline_tag_pattern_in_parens(self):
        matches = list(INLINE_TAG_PATTERN.finditer("(#tag)"))
        assert len(matches) == 1
        assert matches[0].group(1) == "tag"

    def test_h1_pattern(self):
        match = H1_PATTERN.search("# My Title")
        assert match is not None
        assert match.group(1) == "My Title"

    def test_h1_pattern_multiline(self):
        text = "Some text\n# The Title\nMore text"
        match = H1_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "The Title"

    def test_h1_pattern_not_h2(self):
        match = H1_PATTERN.search("## Not H1")
        assert match is None


class TestParseNoteFile:
    """Tests for parse_note_file function."""

    def test_with_frontmatter(self, tmp_path: Path):
        note = tmp_path / "test.md"
        note.write_text(
            """\
---
title: Test Note
date: 2025-11-26
tags:
  - meeting
  - important
---

# Content

Body text here.
""",
            encoding="utf-8",
        )

        meta, body = parse_note_file(note)

        assert meta["title"] == "Test Note"
        # frontmatter library parses dates as date objects
        assert meta["date"] == date(2025, 11, 26)
        assert meta["tags"] == ["meeting", "important"]
        assert "# Content" in body
        assert "Body text here." in body

    def test_without_frontmatter(self, tmp_path: Path):
        note = tmp_path / "test.md"
        note.write_text("# Just a heading\n\nNo frontmatter here.", encoding="utf-8")

        meta, body = parse_note_file(note)

        assert meta == {}
        assert "# Just a heading" in body

    def test_empty_frontmatter(self, tmp_path: Path):
        note = tmp_path / "test.md"
        note.write_text("---\n---\n\nBody only.", encoding="utf-8")

        meta, body = parse_note_file(note)

        assert meta == {}
        assert "Body only." in body


class TestExtractTitle:
    """Tests for extract_title function."""

    def test_from_frontmatter(self, tmp_path: Path):
        meta = {"title": "From Frontmatter"}
        body = "# H1 Title\n\nBody"
        path = tmp_path / "note.md"

        result = extract_title(meta, body, path)
        assert result == "From Frontmatter"

    def test_from_h1(self, tmp_path: Path):
        meta = {}
        body = "# H1 Title\n\nBody text"
        path = tmp_path / "note.md"

        result = extract_title(meta, body, path)
        assert result == "H1 Title"

    def test_from_filename(self, tmp_path: Path):
        meta = {}
        body = "No heading here, just text."
        path = tmp_path / "my-note-file.md"

        result = extract_title(meta, body, path)
        assert result == "my-note-file"

    def test_h1_with_extra_spaces(self, tmp_path: Path):
        meta = {}
        body = "#   Spaced Title   \n\nBody"
        path = tmp_path / "note.md"

        result = extract_title(meta, body, path)
        assert result == "Spaced Title"


class TestExtractDate:
    """Tests for extract_date function."""

    def test_from_frontmatter_string(self, tmp_path: Path):
        meta = {"date": "2025-11-26"}
        path = tmp_path / "note.md"

        result = extract_date(meta, path)
        assert result == date(2025, 11, 26)

    def test_from_frontmatter_date_object(self, tmp_path: Path):
        meta = {"date": date(2025, 11, 26)}
        path = tmp_path / "note.md"

        result = extract_date(meta, path)
        assert result == date(2025, 11, 26)

    def test_from_filename(self, tmp_path: Path):
        meta = {}
        path = tmp_path / "2025-11-26.md"

        result = extract_date(meta, path)
        assert result == date(2025, 11, 26)

    def test_no_date(self, tmp_path: Path):
        meta = {}
        path = tmp_path / "random-note.md"

        result = extract_date(meta, path)
        assert result is None


class TestExtractTags:
    """Tests for extract_tags function."""

    def test_from_frontmatter_list(self):
        meta = {"tags": ["tag1", "tag2", "tag3"]}
        body = "No inline tags"

        result = extract_tags(meta, body)
        assert result == ["tag1", "tag2", "tag3"]

    def test_from_frontmatter_string(self):
        meta = {"tags": "tag1, tag2, tag3"}
        body = "No inline tags"

        result = extract_tags(meta, body)
        assert sorted(result) == ["tag1", "tag2", "tag3"]

    def test_from_inline(self):
        meta = {}
        body = "Some text #important and #urgent stuff #followup"

        result = extract_tags(meta, body)
        assert sorted(result) == ["followup", "important", "urgent"]

    def test_combined(self):
        meta = {"tags": ["meeting"]}
        body = "Discussion #important about #planning"

        result = extract_tags(meta, body)
        assert sorted(result) == ["important", "meeting", "planning"]

    def test_deduplication(self):
        meta = {"tags": ["tag1"]}
        body = "Text #tag1 repeated"

        result = extract_tags(meta, body)
        assert result == ["tag1"]

    def test_case_normalization(self):
        meta = {}
        body = "#TAG1 and #Tag2"

        result = extract_tags(meta, body)
        # Inline tags are lowercased
        assert sorted(result) == ["tag1", "tag2"]


class TestExtractWikiLinks:
    """Tests for extract_wiki_links function."""

    def test_simple_link(self):
        body = "See [[path/to/note]]"

        result = extract_wiki_links(body)
        assert result == [("path/to/note", "path/to/note")]

    def test_link_with_display(self):
        body = "See [[path/to/note|Display Text]]"

        result = extract_wiki_links(body)
        assert result == [("path/to/note", "Display Text")]

    def test_multiple_links(self):
        body = "See [[note1]] and [[note2|Second]] also [[note3]]"

        result = extract_wiki_links(body)
        assert len(result) == 3
        assert result[0] == ("note1", "note1")
        assert result[1] == ("note2", "Second")
        assert result[2] == ("note3", "note3")

    def test_no_links(self):
        body = "No wiki links here"

        result = extract_wiki_links(body)
        assert result == []

    def test_whitespace_handling(self):
        body = "[[  path/note  |  Display  ]]"

        result = extract_wiki_links(body)
        assert result == [("path/note", "Display")]


class TestGenerateFrontmatter:
    """Tests for generate_frontmatter function."""

    def test_simple_dict(self):
        meta = {"title": "My Note", "date": "2025-11-26"}

        result = generate_frontmatter(meta)

        assert result.startswith("---\n")
        assert result.endswith("---\n\n")
        assert "title: My Note" in result
        assert "date: '2025-11-26'" in result or "date: 2025-11-26" in result

    def test_with_list(self):
        meta = {"tags": ["a", "b", "c"]}

        result = generate_frontmatter(meta)

        assert "tags:" in result
        assert "- a" in result

    def test_empty_dict(self):
        result = generate_frontmatter({})
        assert result == ""


class TestCreateNoteTemplate:
    """Tests for create_note_template function."""

    def test_with_title(self):
        result = create_note_template(title="My Note", dt=date(2025, 11, 26))

        assert "---" in result
        assert "date: '2025-11-26'" in result or "date: 2025-11-26" in result
        assert "# My Note" in result

    def test_with_tags(self):
        result = create_note_template(
            title="Tagged Note", dt=date(2025, 11, 26), tags=["important", "meeting"]
        )

        assert "tags:" in result
        assert "- important" in result
        assert "- meeting" in result

    def test_default_title(self):
        result = create_note_template(dt=date(2025, 11, 26))

        # Default format includes day of week from config.daily_title_format
        assert "# Notes - Wednesday, November 26, 2025" in result


class TestCreateDailyNoteTemplate:
    """Tests for create_daily_note_template function."""

    def test_daily_template(self):
        result = create_daily_note_template(date(2025, 11, 26))

        assert "---" in result
        assert "date:" in result
        # Default format includes day of week from config.daily_title_format
        assert "# Wednesday, November 26, 2025" in result
