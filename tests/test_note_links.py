"""Tests for note linking features."""

from __future__ import annotations

from click.testing import CliRunner

from nb.cli import cli
from nb.index.scanner import index_note
from nb.utils.markdown import (
    MD_LINK_PATTERN,
    WIKI_LINK_PATTERN,
    extract_all_links,
    extract_frontmatter_links,
    extract_markdown_links,
    is_external_link,
)


class TestWikiLinkPattern:
    """Tests for wiki link regex pattern."""

    def test_simple_link(self):
        match = WIKI_LINK_PATTERN.search("See [[myproject]]")
        assert match is not None
        assert match.group(1) == "myproject"
        assert match.group(2) is None

    def test_link_with_display(self):
        match = WIKI_LINK_PATTERN.search("See [[myproject|My Project]]")
        assert match is not None
        assert match.group(1) == "myproject"
        assert match.group(2) == "My Project"

    def test_link_with_path(self):
        match = WIKI_LINK_PATTERN.search("See [[projects/myproject]]")
        assert match is not None
        assert match.group(1) == "projects/myproject"


class TestMarkdownLinkPattern:
    """Tests for markdown link regex pattern."""

    def test_simple_link(self):
        match = MD_LINK_PATTERN.search("See [My Project](myproject.md)")
        assert match is not None
        assert match.group(1) == "My Project"
        assert match.group(2) == "myproject.md"

    def test_external_link(self):
        match = MD_LINK_PATTERN.search("See [Google](https://google.com)")
        assert match is not None
        assert match.group(1) == "Google"
        assert match.group(2) == "https://google.com"

    def test_relative_link(self):
        match = MD_LINK_PATTERN.search("See [Sibling](./other.md)")
        assert match is not None
        assert match.group(1) == "Sibling"
        assert match.group(2) == "./other.md"

    def test_does_not_match_images(self):
        """Images ![alt](src) should not be matched."""
        match = MD_LINK_PATTERN.search("![My Image](image.png)")
        assert match is None

    def test_link_after_image(self):
        """Link following an image should still match."""
        text = "![img](a.png) and [link](b.md)"
        matches = list(MD_LINK_PATTERN.finditer(text))
        assert len(matches) == 1
        assert matches[0].group(1) == "link"
        assert matches[0].group(2) == "b.md"


class TestIsExternalLink:
    """Tests for external link detection."""

    def test_http(self):
        assert is_external_link("http://example.com")

    def test_https(self):
        assert is_external_link("https://example.com")

    def test_mailto(self):
        assert is_external_link("mailto:test@example.com")

    def test_ftp(self):
        assert is_external_link("ftp://files.example.com")

    def test_file_protocol(self):
        assert is_external_link("file:///path/to/file")

    def test_relative_path(self):
        assert not is_external_link("./sibling.md")

    def test_absolute_path(self):
        assert not is_external_link("/path/to/note.md")

    def test_note_name(self):
        assert not is_external_link("myproject")

    def test_case_insensitive(self):
        assert is_external_link("HTTPS://EXAMPLE.COM")


class TestExtractMarkdownLinks:
    """Tests for markdown link extraction."""

    def test_extract_single_link(self):
        body = "See [My Doc](docs/readme.md) for info."
        links = extract_markdown_links(body)
        assert len(links) == 1
        assert links[0] == ("docs/readme.md", "My Doc", False)

    def test_extract_external_link(self):
        body = "Visit [Google](https://google.com)"
        links = extract_markdown_links(body)
        assert len(links) == 1
        assert links[0] == ("https://google.com", "Google", True)

    def test_extract_multiple_links(self):
        body = "[A](a.md) and [B](https://b.com)"
        links = extract_markdown_links(body)
        assert len(links) == 2
        assert links[0] == ("a.md", "A", False)
        assert links[1] == ("https://b.com", "B", True)

    def test_no_links(self):
        body = "No links here"
        links = extract_markdown_links(body)
        assert len(links) == 0


class TestExtractAllLinks:
    """Tests for combined link extraction."""

    def test_wiki_links_only(self):
        body = "See [[project]] and [[other|Other Note]]"
        links = extract_all_links(body)
        assert len(links) == 2
        assert ("project", "project", "wiki", False) in links
        assert ("other", "Other Note", "wiki", False) in links

    def test_markdown_links_only(self):
        body = "See [Doc](doc.md) and [Site](https://site.com)"
        links = extract_all_links(body)
        assert len(links) == 2
        assert ("doc.md", "Doc", "markdown", False) in links
        assert ("https://site.com", "Site", "markdown", True) in links

    def test_mixed_links(self):
        body = "Wiki [[note]] and markdown [link](other.md)"
        links = extract_all_links(body)
        assert len(links) == 2
        wiki_links = [l for l in links if l[2] == "wiki"]
        md_links = [l for l in links if l[2] == "markdown"]
        assert len(wiki_links) == 1
        assert len(md_links) == 1


class TestExtractFrontmatterLinks:
    """Tests for frontmatter link extraction."""

    def test_note_protocol_link(self):
        """note:// protocol should be parsed as internal link."""
        meta = {"links": ["note://work/project-plan"]}
        links = extract_frontmatter_links(meta)
        assert len(links) == 1
        assert links[0] == ("work/project-plan", "project-plan", "frontmatter", False)

    def test_external_url_string(self):
        """External URLs as strings should be marked external."""
        meta = {"links": ["https://example.com", "http://test.com"]}
        links = extract_frontmatter_links(meta)
        assert len(links) == 2
        assert (
            "https://example.com",
            "https://example.com",
            "frontmatter",
            True,
        ) in links
        assert ("http://test.com", "http://test.com", "frontmatter", True) in links

    def test_object_format_url(self):
        """Object format with url should work."""
        meta = {"links": [{"title": "My Site", "url": "https://example.com"}]}
        links = extract_frontmatter_links(meta)
        assert len(links) == 1
        assert links[0] == ("https://example.com", "My Site", "frontmatter", True)

    def test_object_format_note(self):
        """Object format with note should work."""
        meta = {"links": [{"title": "Project Plan", "note": "2026-plan"}]}
        links = extract_frontmatter_links(meta)
        assert len(links) == 1
        assert links[0] == ("2026-plan", "Project Plan", "frontmatter", False)

    def test_object_format_note_with_notebook(self):
        """Object format with note and notebook should combine them."""
        meta = {
            "links": [{"title": "Work Plan", "note": "2026-plan", "notebook": "work"}]
        }
        links = extract_frontmatter_links(meta)
        assert len(links) == 1
        assert links[0] == ("work/2026-plan", "Work Plan", "frontmatter", False)

    def test_object_format_no_title(self):
        """Object format without title should use note/url as display."""
        meta = {"links": [{"note": "my-note"}, {"url": "https://example.com"}]}
        links = extract_frontmatter_links(meta)
        assert len(links) == 2
        assert ("my-note", "my-note", "frontmatter", False) in links
        assert (
            "https://example.com",
            "https://example.com",
            "frontmatter",
            True,
        ) in links

    def test_mixed_formats(self):
        """Mix of string and object formats should work."""
        meta = {
            "links": [
                "note://daily/today",
                "https://google.com",
                {"title": "Blog", "url": "https://blog.com"},
                {"title": "Plan", "note": "plan", "notebook": "work"},
            ]
        }
        links = extract_frontmatter_links(meta)
        assert len(links) == 4

    def test_no_links_field(self):
        meta = {"title": "My Note"}
        links = extract_frontmatter_links(meta)
        assert len(links) == 0

    def test_empty_links(self):
        meta = {"links": []}
        links = extract_frontmatter_links(meta)
        assert len(links) == 0

    def test_single_string_links(self):
        meta = {"links": "https://example.com"}
        links = extract_frontmatter_links(meta)
        assert len(links) == 1

    def test_plain_string_as_note_ref(self):
        """Plain strings without protocol should be treated as note references."""
        meta = {"links": ["my-note-name"]}
        links = extract_frontmatter_links(meta)
        assert len(links) == 1
        assert links[0][0] == "my-note-name"
        assert links[0][2] == "frontmatter"
        assert links[0][3] is False  # Not external


class TestLinksCommand:
    """Tests for nb links CLI command."""

    def test_links_help(self, mock_config):
        runner = CliRunner()
        result = runner.invoke(cli, ["links", "--help"])
        assert result.exit_code == 0
        assert "outgoing links" in result.output.lower()

    def test_links_no_note(self, mock_config):
        """Should require note_ref without --check."""
        runner = CliRunner()
        result = runner.invoke(cli, ["links"])
        assert result.exit_code == 1
        assert "specify a note" in result.output.lower()

    def test_links_check_all(self, mock_config, temp_notes_root):
        """--check without note should check all notes."""
        runner = CliRunner()
        result = runner.invoke(cli, ["links", "--check"])
        assert result.exit_code == 0


class TestBacklinksCommand:
    """Tests for nb backlinks CLI command."""

    def test_backlinks_help(self, mock_config):
        runner = CliRunner()
        result = runner.invoke(cli, ["backlinks", "--help"])
        assert result.exit_code == 0
        assert "link to" in result.output.lower()


class TestNoteLinksCore:
    """Tests for core note_links functions."""

    def test_get_outgoing_links_empty(self, mock_config, temp_notes_root, create_note):
        """Note with no links should return empty list."""
        from nb.core.note_links import get_outgoing_links

        note_path = create_note("daily", "test.md", "No links here")
        index_note(note_path, temp_notes_root)

        links = get_outgoing_links(note_path)
        assert len(links) == 0

    def test_get_outgoing_links_wiki(self, mock_config, temp_notes_root, create_note):
        """Should extract wiki links."""
        from nb.core.note_links import get_outgoing_links

        note_path = create_note("daily", "test.md", "See [[other-note]] for info")
        index_note(note_path, temp_notes_root)

        links = get_outgoing_links(note_path)
        assert len(links) == 1
        assert links[0].target == "other-note"
        assert links[0].link_type == "wiki"
        assert not links[0].is_external

    def test_get_outgoing_links_markdown(
        self, mock_config, temp_notes_root, create_note
    ):
        """Should extract markdown links."""
        from nb.core.note_links import get_outgoing_links

        note_path = create_note("daily", "test.md", "See [Doc](docs/readme.md)")
        index_note(note_path, temp_notes_root)

        links = get_outgoing_links(note_path)
        assert len(links) == 1
        assert links[0].target == "docs/readme.md"
        assert links[0].link_type == "markdown"
        assert not links[0].is_external

    def test_get_outgoing_links_external(
        self, mock_config, temp_notes_root, create_note
    ):
        """Should mark external links correctly."""
        from nb.core.note_links import get_outgoing_links

        note_path = create_note(
            "daily", "test.md", "Visit [Google](https://google.com)"
        )
        index_note(note_path, temp_notes_root)

        links = get_outgoing_links(note_path)
        assert len(links) == 1
        assert links[0].is_external

    def test_get_outgoing_links_filter_internal(
        self, mock_config, temp_notes_root, create_note
    ):
        """internal_only should filter out external links."""
        from nb.core.note_links import get_outgoing_links

        note_path = create_note(
            "daily", "test.md", "[[internal]] and [ext](https://example.com)"
        )
        index_note(note_path, temp_notes_root)

        links = get_outgoing_links(note_path, internal_only=True)
        assert len(links) == 1
        assert links[0].target == "internal"

    def test_get_outgoing_links_filter_external(
        self, mock_config, temp_notes_root, create_note
    ):
        """external_only should filter out internal links."""
        from nb.core.note_links import get_outgoing_links

        note_path = create_note(
            "daily", "test.md", "[[internal]] and [ext](https://example.com)"
        )
        index_note(note_path, temp_notes_root)

        links = get_outgoing_links(note_path, external_only=True)
        assert len(links) == 1
        assert "example.com" in links[0].target

    def test_get_backlinks(self, mock_config, temp_notes_root, create_note):
        """Should find notes linking to target."""
        from nb.core.note_links import get_backlinks

        # Create target note
        target = create_note("daily", "target.md", "Target note")
        # Create note that links to target
        source = create_note("daily", "source.md", "See [[target]] for info")

        # Index both
        index_note(target, temp_notes_root)
        index_note(source, temp_notes_root)

        backlinks = get_backlinks(target)
        assert len(backlinks) == 1
        assert "source" in str(backlinks[0].source_path)

    def test_get_broken_links(self, mock_config, temp_notes_root, create_note):
        """Should identify broken links."""
        from nb.core.note_links import get_broken_links

        # Create note with link to non-existent note
        note_path = create_note("daily", "test.md", "See [[nonexistent-note]]")
        index_note(note_path, temp_notes_root)

        broken = get_broken_links(note_path)
        assert len(broken) == 1
        assert broken[0].target == "nonexistent-note"

    def test_resolve_link_target_relative(
        self, mock_config, temp_notes_root, create_note
    ):
        """Should resolve relative paths."""
        from nb.core.note_links import resolve_link_target

        # Create source and sibling notes in same folder
        source = create_note("projects", "source.md", "Source")
        create_note("projects", "sibling.md", "Sibling")

        resolved = resolve_link_target("./sibling.md", source, temp_notes_root)
        assert resolved is not None
        assert resolved.name == "sibling.md"

    def test_resolve_link_target_not_found(self, mock_config, temp_notes_root):
        """Should return None for non-existent targets."""

        from nb.core.note_links import resolve_link_target

        source = temp_notes_root / "test.md"
        resolved = resolve_link_target("nonexistent", source, temp_notes_root)
        assert resolved is None


class TestLinkStats:
    """Tests for link statistics."""

    def test_get_link_stats(self, mock_config, temp_notes_root, create_note):
        """Should return correct statistics."""
        from nb.core.note_links import get_link_stats

        # Create notes with various links
        note1 = create_note(
            "daily",
            "test1.md",
            "[[wiki]] and [md](other.md) and [ext](https://example.com)",
        )
        note2 = create_note("daily", "test2.md", "[[another-wiki]]")

        # Index
        index_note(note1, temp_notes_root)
        index_note(note2, temp_notes_root)

        stats = get_link_stats()
        assert "total" in stats
        assert "internal" in stats
        assert "external" in stats
        assert "wiki" in stats
        assert "markdown" in stats
